"""Composable research pipeline stage framework."""

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

class ResearchPipeline:
    """Runs a list of stages in order, passing a shared ResearchContext."""

    def __init__(self, stages: list[PipelineStage]) -> None:
        self.stages = stages

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
        yield {"type": "status", "message": f"管道启动: {len(self.stages)} 个阶段"}
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
# Built-in concrete stages
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


