"""Composable research pipeline — quick / standard / deep."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from models import SummaryState, SummaryStateOutput, TodoItem


# ---------------------------------------------------------------------------
# Context — mutable state bag that flows through every stage
# ---------------------------------------------------------------------------

@dataclass
class ResearchContext:
    """Shared state passed from stage to stage during a research run."""

    topic: str
    state: SummaryState = field(default_factory=lambda: SummaryState(research_topic=""))

    # pipeline control
    max_loop: int = 3
    abort: bool = False

    # final output
    output: SummaryStateOutput | None = None

    def __post_init__(self) -> None:
        if not self.state.research_topic:
            self.state.research_topic = self.topic


# ---------------------------------------------------------------------------
# Stage protocol
# ---------------------------------------------------------------------------

class StageStatus(Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class StageResult:
    status: StageStatus
    message: str = ""
    data: Any = None


class PipelineStage(ABC):
    """One step in a research pipeline."""

    name: str = "base"

    @abstractmethod
    def execute(self, ctx: ResearchContext) -> StageResult:
        """Run synchronously."""

    def stream(self, ctx: ResearchContext) -> Iterator[dict[str, Any]]:
        """Run with streaming events. Default: delegate to execute()."""
        result = self.execute(ctx)
        yield {"type": "stage_done", "stage": self.name, "status": result.status.value}


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

class ResearchMode(Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class ResearchPipeline:
    """Runs a list of stages in order, passing a shared ResearchContext."""

    def __init__(self, stages: list[PipelineStage], mode: ResearchMode = ResearchMode.STANDARD) -> None:
        self.stages = stages
        self.mode = mode

    def run(self, topic: str) -> ResearchContext:
        """Synchronous execution."""
        ctx = ResearchContext(topic=topic)
        for stage in self.stages:
            if ctx.abort:
                break
            result = stage.execute(ctx)
            if result.status == StageStatus.FAILED:
                ctx.abort = True
        return ctx

    def run_stream(self, topic: str) -> Iterator[dict[str, Any]]:
        """Streaming execution — each stage yields SSE events."""
        ctx = ResearchContext(topic=topic)
        yield {"type": "status", "message": f"研究模式: {self.mode.value} · {len(self.stages)} 个阶段"}
        for stage in self.stages:
            if ctx.abort:
                break
            yield {"type": "status", "message": f"阶段: {stage.name}"}
            try:
                for event in stage.stream(ctx):
                    yield event
            except Exception as exc:
                yield {"type": "error", "detail": f"阶段 {stage.name} 失败: {exc}"}
                ctx.abort = True
        yield {"type": "status", "message": "研究流程完成"}


# ---------------------------------------------------------------------------
# Preset factories
# ---------------------------------------------------------------------------

def build_quick_pipeline(
    search_fn: Callable,
    summarizer_fn: Callable,
    report_fn: Callable,
) -> ResearchPipeline:
    """Single-round search → summarise → report (fast, ~30 s)."""
    return ResearchPipeline(
        stages=[
            _QuickSearchStage(search_fn),
            _QuickSummarizeStage(summarizer_fn),
            _QuickReportStage(report_fn),
        ],
        mode=ResearchMode.QUICK,
    )


def build_standard_pipeline(
    planner_fn: Callable,
    executor_fn: Callable,
    report_fn: Callable,
) -> ResearchPipeline:
    """Plan → per-task search+summarise → report (current default, ~2-5 min)."""
    return ResearchPipeline(
        stages=[
            _PlanStage(planner_fn),
            _ExecuteTasksStage(executor_fn),
            _ReportStage(report_fn),
        ],
        mode=ResearchMode.STANDARD,
    )


def build_deep_pipeline(
    planner_fn: Callable,
    executor_fn: Callable,
    verifier_fn: Callable,
    report_fn: Callable,
) -> ResearchPipeline:
    """Plan → execute → cross-verify → report (thorough, ~5-10 min)."""
    return ResearchPipeline(
        stages=[
            _PlanStage(planner_fn),
            _ExecuteTasksStage(executor_fn),
            _VerifyStage(verifier_fn),
            _ReportStage(report_fn),
        ],
        mode=ResearchMode.DEEP,
    )


# ---------------------------------------------------------------------------
# Built-in concrete stages (thin wrappers that delegate to the agent's methods)
# ---------------------------------------------------------------------------

class _PlanStage(PipelineStage):
    name = "plan"

    def __init__(self, plan_fn: Callable) -> None:
        self._plan = plan_fn

    def execute(self, ctx: ResearchContext) -> StageResult:
        try:
            items = self._plan(ctx.state)
            ctx.state.todo_items = items
            return StageResult(StageStatus.SUCCESS, f"生成了 {len(items)} 个任务")
        except Exception as exc:
            return StageResult(StageStatus.FAILED, str(exc))

    def stream(self, ctx: ResearchContext) -> Iterator[dict[str, Any]]:
        result = self.execute(ctx)
        if result.status == StageStatus.SUCCESS:
            yield {
                "type": "todo_list",
                "tasks": [t.model_dump() for t in ctx.state.todo_items],
                "step": 0,
            }


class _ExecuteTasksStage(PipelineStage):
    name = "execute_tasks"

    def __init__(self, executor_fn: Callable) -> None:
        self._executor = executor_fn

    def execute(self, ctx: ResearchContext) -> StageResult:
        for task in ctx.state.todo_items:
            try:
                self._executor(ctx.state, task, emit_stream=False)
            except Exception:
                task.status = "failed"
        return StageResult(StageStatus.SUCCESS)

    def stream(self, ctx: ResearchContext) -> Iterator[dict[str, Any]]:
        for i, task in enumerate(ctx.state.todo_items, start=1):
            yield {
                "type": "task_status",
                "task_id": task.id,
                "status": "in_progress",
                "title": task.title,
                "intent": task.intent,
                "note_id": task.note_id,
                "note_path": task.note_path,
                "step": i,
            }
            try:
                # _execute_task yields its own in_progress / summary_chunk / sources / completed
                for event in self._executor(ctx.state, task, emit_stream=True, step=i):
                    yield event
            except Exception:
                task.status = "failed"
                yield {
                    "type": "task_status",
                    "task_id": task.id,
                    "status": "failed",
                    "summary": f"任务执行异常",
                    "title": task.title,
                    "step": i,
                }


class _ReportStage(PipelineStage):
    name = "report"

    def __init__(self, report_fn: Callable) -> None:
        self._report = report_fn

    def execute(self, ctx: ResearchContext) -> StageResult:
        try:
            report = self._report(ctx.state)
            ctx.state.running_summary = report
            ctx.state.structured_report = report
            ctx.output = SummaryStateOutput(
                running_summary=report,
                report_markdown=report,
                todo_items=ctx.state.todo_items,
            )
            return StageResult(StageStatus.SUCCESS, data=report)
        except Exception as exc:
            return StageResult(StageStatus.FAILED, str(exc))

    def stream(self, ctx: ResearchContext) -> Iterator[dict[str, Any]]:
        try:
            result = self.execute(ctx)
        except Exception as exc:
            yield {"type": "final_report", "report": f"报告生成失败：{exc}"}
            return
        if result.status == StageStatus.SUCCESS and result.data:
            yield {"type": "final_report", "report": result.data}
        else:
            yield {"type": "final_report", "report": f"报告生成失败：{result.message}"}


class _VerifyStage(PipelineStage):
    """Cross-verify key claims across multiple sources (deep mode only)."""
    name = "verify"

    def __init__(self, verify_fn: Callable) -> None:
        self._verify = verify_fn

    def execute(self, ctx: ResearchContext) -> StageResult:
        try:
            self._verify(ctx.state)
            return StageResult(StageStatus.SUCCESS, "交叉验证完成")
        except Exception as exc:
            return StageResult(StageStatus.FAILED, str(exc))

    def stream(self, ctx: ResearchContext) -> Iterator[dict[str, Any]]:
        result = self.execute(ctx)
        yield {"type": "status", "message": f"交叉验证: {result.message}"}


class _QuickSearchStage(PipelineStage):
    name = "quick_search"

    def __init__(self, search_fn: Callable) -> None:
        self._search = search_fn

    def execute(self, ctx: ResearchContext) -> StageResult:
        try:
            self._search(ctx)
            return StageResult(StageStatus.SUCCESS)
        except Exception as exc:
            return StageResult(StageStatus.FAILED, str(exc))


class _QuickSummarizeStage(PipelineStage):
    name = "quick_summarize"

    def __init__(self, summarize_fn: Callable) -> None:
        self._summarize = summarize_fn

    def execute(self, ctx: ResearchContext) -> StageResult:
        try:
            self._summarize(ctx)
            return StageResult(StageStatus.SUCCESS)
        except Exception as exc:
            return StageResult(StageStatus.FAILED, str(exc))


class _QuickReportStage(PipelineStage):
    name = "quick_report"

    def __init__(self, report_fn: Callable) -> None:
        self._report_fn = report_fn

    def execute(self, ctx: ResearchContext) -> StageResult:
        try:
            report = self._report_fn(ctx)
            ctx.output = SummaryStateOutput(
                running_summary=report,
                report_markdown=report,
                todo_items=[],
            )
            return StageResult(StageStatus.SUCCESS, data=report)
        except Exception as exc:
            return StageResult(StageStatus.FAILED, str(exc))
