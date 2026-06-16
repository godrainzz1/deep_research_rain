"""Orchestrator coordinating the deep research workflow."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Any, Callable, Iterator

from hello_agents import HelloAgentsLLM, ToolAwareSimpleAgent
from hello_agents.tools import ToolRegistry
from hello_agents.tools import NoteTool

from config import Configuration
from prompts import (
    report_writer_instructions,
    task_summarizer_instructions,
    todo_planner_system_prompt,
)
from models import SummaryState, SummaryStateOutput, TodoItem
from services.planner import PlanningService
from services.reporter import ReportingService
from services.search import dispatch_search, prepare_research_context
from services.summarizer import SummarizationService
from services.tool_events import ToolCallTracker

logger = logging.getLogger(__name__)


class FallbackLLM:
    """Transparent LLM wrapper that auto-falls-back when the primary LLM fails.

    Once the primary fails, a circuit-breaker trips so every subsequent call
    goes straight to the fallback — no more wasted 403 round-trips.

    Delegates all attribute access to the primary so that downstream code
    (ToolAwareSimpleAgent, summarizer, planner, reporter) doesn't know about
    the fallback at all.
    """

    def __init__(self, primary: HelloAgentsLLM, fallback: HelloAgentsLLM) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_dead = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._primary, name)

    # -- streaming -------------------------------------------------------

    def stream_invoke(self, messages: list[dict[str, str]], **kwargs) -> Any:
        if self._primary_dead:
            yield from self._fallback.stream_invoke(messages, **kwargs)
            return

        try:
            yield from self._primary.stream_invoke(messages, **kwargs)
        except Exception as exc:
            self._primary_dead = True
            logger.warning(
                "Primary LLM (%s) stream failed, switching to fallback %s "
                "for ALL remaining calls this session: %s",
                getattr(self._primary, "model", "?"),
                getattr(self._fallback, "model", "?"),
                exc,
            )
            try:
                yield from self._fallback.stream_invoke(messages, **kwargs)
            except Exception:
                logger.exception("Fallback LLM also failed — giving up.")

    # -- non-streaming ---------------------------------------------------

    def invoke(self, messages: list[dict[str, str]], **kwargs) -> str:
        if self._primary_dead:
            return self._fallback.invoke(messages, **kwargs)

        try:
            return self._primary.invoke(messages, **kwargs)
        except Exception as exc:
            self._primary_dead = True
            logger.warning(
                "Primary LLM (%s) invoke failed, switching to fallback %s "
                "for ALL remaining calls this session: %s",
                getattr(self._primary, "model", "?"),
                getattr(self._fallback, "model", "?"),
                exc,
            )
            try:
                return self._fallback.invoke(messages, **kwargs)
            except Exception:
                logger.exception("Fallback LLM also failed — giving up.")
                return ""


class DeepResearchAgent:
    """Coordinator orchestrating TODO-based research workflow using HelloAgents."""

    def __init__(self, config: Configuration | None = None) -> None:
        """Initialise the coordinator with configuration and shared tools."""
        self.config = config or Configuration.from_env()
        self.llm = self._init_llm()

        self.note_tool = (
            NoteTool(workspace=self.config.notes_workspace)
            if self.config.enable_notes
            else None
        )
        self.tools_registry: ToolRegistry | None = None
        if self.note_tool:
            registry = ToolRegistry()
            registry.register_tool(self.note_tool)
            self.tools_registry = registry

        self._tool_tracker = ToolCallTracker(
            self.config.notes_workspace if self.config.enable_notes else None
        )
        self._tool_event_sink_enabled = False
        self._state_lock = Lock()

        # 规划专家只需要 JSON 输出，不需要 tool calling
        self.todo_agent = self._create_tool_aware_agent(
            name="研究规划专家",
            system_prompt=todo_planner_system_prompt.strip(),
            enable_tool_calling=False,
        )
        # 报告专家需要 note 工具来读取任务笔记
        self.report_agent = self._create_tool_aware_agent(
            name="报告撰写专家",
            system_prompt=report_writer_instructions.strip(),
            enable_tool_calling=self.tools_registry is not None,
        )

        # 总结专家需要 note 工具来读写任务笔记
        self._summarizer_factory: Callable[[], ToolAwareSimpleAgent] = lambda: self._create_tool_aware_agent(  # noqa: E501
            name="任务总结专家",
            system_prompt=task_summarizer_instructions.strip(),
            enable_tool_calling=self.tools_registry is not None,
        )

        self.planner = PlanningService(self.todo_agent, self.config)
        self.summarizer = SummarizationService(self._summarizer_factory, self.config)
        self.reporting = ReportingService(self.report_agent, self.config)
        self._last_search_notices: list[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def _init_llm(self) -> HelloAgentsLLM | FallbackLLM:
        """Instantiate primary + optional fallback LLM.

        Priority: explicitly set LLM_BASE_URL > provider-specific URL > Ollama default.
        When *llm_fallback_provider* is configured a ``FallbackLLM`` is returned
        that transparently retries with the fallback on any exception.
        """

        def _build_llm(
            model_id: str | None,
            base_url: str | None,
            provider: str,
            api_key: str | None,
        ) -> HelloAgentsLLM:
            kwargs: dict[str, Any] = {"temperature": 0.0, "timeout": self.config.llm_timeout}
            if self.config.llm_max_tokens is not None:
                kwargs["max_tokens"] = self.config.llm_max_tokens
            if model_id:
                kwargs["model"] = model_id
            if base_url:
                kwargs["base_url"] = base_url
            if api_key:
                kwargs["api_key"] = api_key
            if provider:
                kwargs["provider"] = provider
            return HelloAgentsLLM(**kwargs)

        # --- Primary LLM ---
        primary_model = self.config.llm_model_id or self.config.local_llm
        primary_provider = (self.config.llm_provider or "").strip()
        primary_base_url = self.config.llm_base_url
        if not primary_base_url:
            if primary_provider == "ollama":
                primary_base_url = self.config.sanitized_ollama_url()
            elif primary_provider == "lmstudio":
                primary_base_url = self.config.lmstudio_base_url
            else:
                primary_base_url = self.config.sanitized_ollama_url()
        primary_api_key = self.config.llm_api_key
        if not primary_api_key and primary_provider == "ollama":
            primary_api_key = "ollama"

        primary = _build_llm(
            primary_model, primary_base_url, primary_provider, primary_api_key
        )
        logger.info(
            "Primary LLM: model=%s base_url=%s provider=%s",
            primary.model,
            primary.base_url,
            primary.provider,
        )

        # --- Fallback LLM (optional) ---
        fallback_provider = (self.config.llm_fallback_provider or "").strip()
        if not fallback_provider:
            logger.info("No fallback LLM configured.")
            return primary

        fallback_model = self.config.llm_fallback_model_id or self.config.local_llm
        fallback_base_url = self.config.llm_fallback_base_url
        if not fallback_base_url:
            if fallback_provider == "ollama":
                fallback_base_url = self.config.sanitized_ollama_url()
            elif fallback_provider == "lmstudio":
                fallback_base_url = self.config.lmstudio_base_url

        fallback_api_key = "ollama" if fallback_provider == "ollama" else None

        fallback = _build_llm(
            fallback_model, fallback_base_url, fallback_provider, fallback_api_key
        )
        logger.info(
            "Fallback LLM: model=%s base_url=%s provider=%s",
            fallback.model,
            fallback.base_url,
            fallback.provider,
        )

        return FallbackLLM(primary, fallback)

    def _create_tool_aware_agent(
        self,
        *,
        name: str,
        system_prompt: str,
        enable_tool_calling: bool | None = None,
    ) -> ToolAwareSimpleAgent:
        """Instantiate a ToolAwareSimpleAgent sharing tool registry and tracker.

        When *enable_tool_calling* is None, tool calling is enabled only when
        a tool registry is available AND the config enables it.
        """
        if enable_tool_calling is None:
            enable_tool_calling = (
                self.tools_registry is not None and self.config.use_tool_calling
            )
        return ToolAwareSimpleAgent(
            name=name,
            llm=self.llm,
            system_prompt=system_prompt,
            enable_tool_calling=enable_tool_calling,
            tool_registry=self.tools_registry if enable_tool_calling else None,
            tool_call_listener=self._tool_tracker.record if enable_tool_calling else None,
        )

    def _set_tool_event_sink(self, sink: Callable[[dict[str, Any]], None] | None) -> None:
        """Enable or disable immediate tool event callbacks."""
        self._tool_event_sink_enabled = sink is not None
        self._tool_tracker.set_event_sink(sink)

    def run(self, topic: str) -> SummaryStateOutput:
        """Execute the research workflow and return the final report."""
        state = SummaryState(research_topic=topic)

        try:
            state.todo_items = self.planner.plan_todo_list(state)
        except Exception as exc:
            logger.exception("Planner failed, using fallback task: %s", exc)
            state.todo_items = [self.planner.create_fallback_task(state)]

        self._drain_tool_events(state)

        if not state.todo_items:
            logger.info("No TODO items generated; falling back to single task")
            state.todo_items = [self.planner.create_fallback_task(state)]

        for task in state.todo_items:
            try:
                self._execute_task(state, task, emit_stream=False)
            except Exception as exc:
                logger.exception("Task %d execution failed: %s", task.id, exc)
                task.status = "failed"
                task.summary = f"任务执行失败：{exc}"

        report = self.reporting.generate_report(state)
        self._drain_tool_events(state)
        state.structured_report = report
        state.running_summary = report
        self._persist_final_report(state, report)

        # 持久化到记忆（情景 + 语义）
        try:
            from memory.store import get_memory_store, SemanticMemory
            import uuid
            sid = f"session_{uuid.uuid4().hex[:12]}"
            get_memory_store().save_session(sid, topic, report or "")
            # 语义记忆：将研究报告嵌入为知识卡片，供未来相似话题召回
            SemanticMemory().store_knowledge_card(
                topic, report or "", metadata={"session_id": sid}
            )
        except Exception:
            logger.debug("Memory save skipped (store unavailable)")

        return SummaryStateOutput(
            running_summary=report,
            report_markdown=report,
            todo_items=state.todo_items,
        )

    def run_stream(self, topic: str) -> Iterator[dict[str, Any]]:
        """Execute the workflow yielding incremental progress events."""
        state = SummaryState(research_topic=topic)
        logger.info("Starting streaming research: topic=%s", topic)

        # 匹配 Skill
        try:
            from services.skill_engine import SkillEngine
            se = SkillEngine(skills_dir="skills")
            se.load_all()
            matched = se.match(topic)
            skill_name = matched.name if matched else "deep-research"
        except Exception:
            skill_name = "deep-research"

        logger.info("Matched skill: %s", skill_name)
        yield {"type": "status", "message": "初始化研究流程"}
        yield {"type": "skill", "name": skill_name}

        # 语义记忆召回：检查是否有相似历史研究
        try:
            from memory.store import check_similar_topic as _check
            similar = _check(topic)
            if similar:
                cards = []
                for s in similar[:3]:
                    doc = s.get("document", "")
                    meta = s.get("metadata", {})
                    # 提取干净标题：优先用 metadata，否则从文档开头取（跳过工具噪音）
                    card_topic = meta.get("topic") or doc.split(":")[0].lstrip("# ")[:60]
                    # 预览：取文档的前 200 字符，跳过开头可能存在的工具响应
                    preview = doc.split("\n\n", 1)[-1] if "\n\n" in doc else doc
                    preview = preview[:200]
                    # 相似度映射：distance 0-1.15 → 高/中/低
                    raw_dist = s.get("distance", 1.0)
                    if raw_dist < 0.95:
                        level = "high"
                    elif raw_dist < 1.1:
                        level = "medium"
                    else:
                        level = "low"
                    cards.append({
                        "topic": card_topic,
                        "preview": preview.strip(),
                        "level": level,
                        "session_id": meta.get("session_id", ""),
                    })
                yield {"type": "memory_recall", "topic": topic, "similar": cards}
                logger.info("Semantic memory recall: %d similar topics found", len(similar))
        except Exception:
            logger.debug("Semantic recall skipped")

        # 规划阶段 — 失败时使用兜底任务
        try:
            state.todo_items = self.planner.plan_todo_list(state)
        except Exception as exc:
            logger.exception("Planner failed, using fallback task: %s", exc)
            yield {"type": "status", "message": f"任务规划失败（{exc}），使用默认任务继续"}
            state.todo_items = [self.planner.create_fallback_task(state)]

        for event in self._drain_tool_events(state, step=0):
            yield event
        if not state.todo_items:
            state.todo_items = [self.planner.create_fallback_task(state)]

        channel_map: dict[int, dict[str, Any]] = {}
        for index, task in enumerate(state.todo_items, start=1):
            token = f"task_{task.id}"
            task.stream_token = token
            channel_map[task.id] = {"step": index, "token": token}

        yield {
            "type": "todo_list",
            "tasks": [self._serialize_task(t) for t in state.todo_items],
            "step": 0,
        }

        event_queue: Queue[dict[str, Any]] = Queue()

        def enqueue(event, *, task=None, step_override=None):
            payload = dict(event)
            target_task_id = payload.get("task_id")
            if task is not None:
                target_task_id = task.id
                payload["task_id"] = task.id
            channel = channel_map.get(target_task_id) if target_task_id is not None else None
            if channel:
                payload.setdefault("step", channel["step"])
                payload["stream_token"] = channel["token"]
            if step_override is not None:
                payload["step"] = step_override
            event_queue.put(payload)

        def tool_event_sink(event):
            enqueue(event)

        self._set_tool_event_sink(tool_event_sink)

        threads: list[Thread] = []

        def worker(task, step):
            try:
                # _execute_task already yields in_progress / completed
                for event in self._execute_task(state, task, emit_stream=True, step=step):
                    enqueue(event, task=task, step_override=step)
            except Exception as exc:
                logger.exception("Task %d execution failed", task.id)
                enqueue({
                    "type": "task_status", "task_id": task.id,
                    "status": "failed", "summary": f"任务执行失败：{exc}",
                    "step": step,
                }, step_override=step)

        for index, task in enumerate(state.todo_items, start=1):
            t = Thread(target=worker, args=(task, index), daemon=True)
            threads.append(t)
            t.start()

        # Drain events WHILE threads run — don't wait for all to finish
        alive = len(threads)
        while alive > 0:
            try:
                event = event_queue.get(timeout=0.2)
                yield event
            except Empty:
                pass
            alive = sum(1 for t in threads if t.is_alive())

        # Drain any remaining events
        self._set_tool_event_sink(None)
        while True:
            try:
                event = event_queue.get_nowait()
                yield event
            except Empty:
                break

        # Generate final report
        yield {"type": "status", "message": "正在生成最终报告..."}
        try:
            report = self.reporting.generate_report(state)
        except Exception as exc:
            logger.exception("Report generation failed")
            report = f"报告生成失败：{exc}"

        self._drain_tool_events(state)
        yield {"type": "final_report", "report": report or "报告生成失败，未获得有效内容"}

        # Persist final report to notes
        self._persist_final_report(state, report)

        # Save to memory (persistent across sessions) — 情景 + 语义
        try:
            from memory.store import get_memory_store, SemanticMemory
            import uuid, json
            sid = f"session_{uuid.uuid4().hex[:12]}"
            meta = {"skill": skill_name, "tasks": [t.title for t in state.todo_items]}
            get_memory_store().save_session(sid, topic, report or "", metadata=meta)
            # 语义记忆：嵌入研究报告供未来相似话题召回
            SemanticMemory().store_knowledge_card(
                topic, report or "", metadata={"session_id": sid, "skill": skill_name}
            )
            logger.info("Memory saved: session=%s skill=%s", sid, skill_name)
        except Exception:
            logger.debug("Memory save skipped")

    # ------------------------------------------------------------------
    # Task execution (search + summarise)
    # ------------------------------------------------------------------

    def _execute_task(self, state, task, *, emit_stream=False, step=None):
        """Run search -> summarise for a single task."""
        query = task.query or state.research_topic
        search_result, notices, answer_text, backend = dispatch_search(query, self.config, state.research_loop_count)
        task.notices = notices

        if emit_stream:
            yield {"type": "task_status", "task_id": task.id, "status": "in_progress",
                   "title": task.title, "intent": task.intent,
                   "note_id": task.note_id, "note_path": task.note_path, "step": step}

        if not search_result or not search_result.get("results"):
            task.status = "skipped"
            if emit_stream:
                for event in self._drain_tool_events(state, step=step): yield event
                yield {"type": "task_status", "task_id": task.id, "status": "skipped",
                       "title": task.title, "intent": task.intent,
                       "note_id": task.note_id, "note_path": task.note_path, "step": step}
            else:
                self._drain_tool_events(state)
            return

        if not emit_stream:
            self._drain_tool_events(state)

        # --- 程序化创建笔记（不再依赖 LLM 自行调用 create tool）---
        self._ensure_task_note(task)

        sources_summary, context = prepare_research_context(search_result, answer_text, self.config, rag_query=query)
        task.sources_summary = sources_summary
        with self._state_lock:
            state.web_research_results.append(context)
            state.sources_gathered.append(sources_summary)
            state.research_loop_count += 1

        summary_text = None
        if emit_stream:
            for event in self._drain_tool_events(state, step=step): yield event
            yield {"type": "sources", "task_id": task.id, "latest_sources": sources_summary,
                   "raw_context": context, "step": step, "backend": backend,
                   "note_id": task.note_id, "note_path": task.note_path}
            # 流式推送 — 每个 chunk 即时清理工具调用语法后发送，保留实时反馈
            from services.text_processing import strip_tool_calls as _strip
            summary_stream, summary_getter = self.summarizer.stream_task_summary(state, task, context)
            try:
                for event in self._drain_tool_events(state, step=step): yield event
                for chunk in summary_stream:
                    if chunk:
                        clean = _strip(chunk)
                        if clean.strip():
                            yield {"type": "task_summary_chunk", "task_id": task.id,
                                   "content": clean, "note_id": task.note_id, "step": step}
                    for event in self._drain_tool_events(state, step=step): yield event
            finally:
                # 流结束 — 用最终去重版本替换前端累积的流式内容
                summary_text = summary_getter()
                if summary_text and summary_text.strip():
                    yield {"type": "task_summary_reset", "task_id": task.id,
                           "content": summary_text.strip(), "step": step}
        else:
            summary_text = self.summarizer.summarize_task(state, task, context)
            self._drain_tool_events(state)

        task.summary = summary_text.strip() if summary_text else "暂无可用信息"
        task.status = "completed"

        # --- 程序化更新笔记（不再依赖 LLM 自行调用 update tool）---
        self._update_task_note(task)

        if emit_stream:
            for event in self._drain_tool_events(state, step=step): yield event
            yield {"type": "task_status", "task_id": task.id, "status": "completed",
                   "summary": task.summary, "sources_summary": task.sources_summary,
                   "note_id": task.note_id, "note_path": task.note_path, "step": step}
        else:
            self._drain_tool_events(state)

    def _ensure_task_note(self, task: TodoItem) -> None:
        """程序化创建笔记 — 不依赖 LLM 自行调用 create tool。

        确保每个任务在进入总结阶段前都有一个真实笔记 ID，
        且该 ID 不会被 LLM 幻觉覆盖（_attach_note_to_task 保护）。
        """
        if task.note_id:
            return  # 已有笔记，无需创建

        if not self.note_tool:
            return

        with self._state_lock:
            # 双重检查：锁内再次确认 note_id 未被其他线程设置
            if task.note_id:
                return

            title = f"任务 {task.id}: {task.title}"
            tags = ["deep_research", f"task_{task.id}"]
            content = (
                f"任务目标：{task.intent}\n"
                f"检索查询：{task.query}\n"
                f"请记录任务概览、来源概览、任务总结"
            )

            response = self.note_tool.run({
                "action": "create",
                "task_id": task.id,
                "title": title,
                "note_type": "task_state",
                "tags": tags,
                "content": content,
            })

            note_id = self._extract_note_id_from_text(response)
            if note_id:
                task.note_id = note_id
                if self.config.notes_workspace:
                    workspace = self.config.notes_workspace
                    task.note_path = str(Path(workspace) / f"{note_id}.md")
                logger.info("Programmatic note created: task_id=%d note_id=%s", task.id, note_id)
            else:
                logger.warning("Failed to extract note_id from create response: %s", response[:200])

    def _update_task_note(self, task: TodoItem) -> None:
        """程序化更新笔记 — 将最终任务总结写入已有笔记。"""
        if not task.note_id or not self.note_tool:
            return
        if not task.summary or task.summary == "暂无可用信息":
            return

        with self._state_lock:
            content = (
                f"## 任务状态：已完成\n\n"
                f"### 任务总结\n\n{task.summary}\n\n"
                f"### 来源概览\n\n{task.sources_summary or '暂无来源'}"
            )
            try:
                self.note_tool.run({
                    "action": "update",
                    "note_id": task.note_id,
                    "task_id": task.id,
                    "title": f"任务 {task.id}: {task.title}",
                    "note_type": "task_state",
                    "tags": ["deep_research", f"task_{task.id}"],
                    "content": content,
                })
                logger.info("Programmatic note updated: task_id=%d note_id=%s", task.id, task.note_id)
            except Exception as exc:
                logger.warning("Failed to update note %s: %s", task.note_id, exc)

    def _drain_tool_events(
        self,
        state: SummaryState,
        *,
        step: int | None = None,
    ) -> list[dict[str, Any]]:
        """Proxy to the shared tool call tracker."""
        events = self._tool_tracker.drain(state, step=step)
        if self._tool_event_sink_enabled:
            return []
        return events

    @property
    def _tool_call_events(self) -> list[dict[str, Any]]:
        """Expose recorded tool events for legacy integrations."""
        return self._tool_tracker.as_dicts()

    def _serialize_task(self, task: TodoItem) -> dict[str, Any]:
        """Convert task dataclass to serializable dict for frontend."""
        return {
            "id": task.id,
            "title": task.title,
            "intent": task.intent,
            "query": task.query,
            "status": task.status,
            "summary": task.summary,
            "sources_summary": task.sources_summary,
            "note_id": task.note_id,
            "note_path": task.note_path,
            "stream_token": task.stream_token,
        }

    def _persist_final_report(self, state: SummaryState, report: str) -> dict[str, Any] | None:
        if not self.note_tool or not report or not report.strip():
            return None

        note_title = f"研究报告：{state.research_topic}".strip() or "研究报告"
        tags = ["deep_research", "report"]
        content = report.strip()

        note_id = self._find_existing_report_note_id(state)
        response = ""

        if note_id:
            response = self.note_tool.run(
                {
                    "action": "update",
                    "note_id": note_id,
                    "title": note_title,
                    "note_type": "conclusion",
                    "tags": tags,
                    "content": content,
                }
            )
            if response.startswith("❌"):
                note_id = None

        if not note_id:
            response = self.note_tool.run(
                {
                    "action": "create",
                    "title": note_title,
                    "note_type": "conclusion",
                    "tags": tags,
                    "content": content,
                }
            )
            note_id = self._extract_note_id_from_text(response)

        if not note_id:
            return None

        state.report_note_id = note_id
        if self.config.notes_workspace:
            note_path = Path(self.config.notes_workspace) / f"{note_id}.md"
            state.report_note_path = str(note_path)
        else:
            note_path = None

        payload = {
            "type": "report_note",
            "note_id": note_id,
            "title": note_title,
            "content": content,
        }
        if note_path:
            payload["note_path"] = str(note_path)

        return payload

    def _find_existing_report_note_id(self, state: SummaryState) -> str | None:
        if state.report_note_id:
            return state.report_note_id

        for event in reversed(self._tool_tracker.as_dicts()):
            if event.get("tool") != "note":
                continue

            parameters = event.get("parsed_parameters") or {}
            if not isinstance(parameters, dict):
                continue

            action = parameters.get("action")
            if action not in {"create", "update"}:
                continue

            note_type = parameters.get("note_type")
            if note_type != "conclusion":
                title = parameters.get("title")
                if not (isinstance(title, str) and title.startswith("研究报告")):
                    continue

            note_id = parameters.get("note_id")
            if not note_id:
                note_id = self._tool_tracker._extract_note_id(event.get("result", ""))  # type: ignore[attr-defined]

            if note_id:
                return note_id

        return None

    @staticmethod
    def _extract_note_id_from_text(response: str) -> str | None:
        if not response:
            return None

        match = re.search(r"ID:\s*([^\n]+)", response)
        if not match:
            return None

        return match.group(1).strip()


def run_deep_research(topic: str, config: Configuration | None = None) -> SummaryStateOutput:
    """Convenience function mirroring the class-based API."""
    agent = DeepResearchAgent(config=config)
    return agent.run(topic)
