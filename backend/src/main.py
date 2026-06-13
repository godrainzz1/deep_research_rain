"""FastAPI entrypoint exposing the DeepResearchAgent via HTTP."""

from __future__ import annotations

import json
import os
import sys

# 修复 Windows 下 hello_agents 打印 emoji 时的 GBK 编码错误
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from typing import Any, Dict, Iterator, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from config import Configuration, SearchAPI
from agent import DeepResearchAgent
from services.skill_engine import SkillEngine
from memory.store import get_memory_store, check_similar_topic

# 添加控制台日志处理程序
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>using_function:{function}</cyan> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)


# 添加错误日志文件处理程序
logger.add(
    sink=sys.stderr,
    level="ERROR",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <4}</level> | <cyan>using_function:{function}</cyan> | <cyan>{file}:{line}</cyan> | <level>{message}</level>",
    colorize=True,
)


class ResearchRequest(BaseModel):
    """Payload for triggering a research run."""

    topic: str = Field(..., description="Research topic supplied by the user")
    search_api: SearchAPI | None = Field(
        default=None,
        description="Override the default search backend configured via env",
    )


class ResearchResponse(BaseModel):
    """HTTP response containing the generated report and structured tasks."""

    report_markdown: str = Field(
        ..., description="Markdown-formatted research report including sections"
    )
    todo_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured TODO items with summaries and sources",
    )


def _mask_secret(value: Optional[str], visible: int = 4) -> str:
    """Mask sensitive tokens while keeping leading and trailing characters."""
    if not value:
        return "unset"

    if len(value) <= visible * 2:
        return "*" * len(value)

    return f"{value[:visible]}...{value[-visible:]}"


def _build_config(payload: ResearchRequest) -> Configuration:
    overrides: Dict[str, Any] = {}

    if payload.search_api is not None:
        overrides["search_api"] = payload.search_api

    return Configuration.from_env(overrides=overrides)


def create_app() -> FastAPI:
    app = FastAPI(title="HelloAgents Deep Researcher")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    skill_engine = SkillEngine(skills_dir="skills")

    @app.on_event("startup")
    def log_startup_configuration() -> None:
        config = Configuration.from_env()

        if config.llm_provider == "ollama":
            base_url = config.sanitized_ollama_url()
        elif config.llm_provider == "lmstudio":
            base_url = config.lmstudio_base_url
        else:
            base_url = config.llm_base_url or "unset"

        logger.info(
            "DeepResearch configuration loaded: provider=%s model=%s base_url=%s search_api=%s "
            "max_loops=%s fetch_full_page=%s tool_calling=%s strip_thinking=%s api_key=%s",
            config.llm_provider,
            config.resolved_model() or "unset",
            base_url,
            (config.search_api.value if isinstance(config.search_api, SearchAPI) else config.search_api),
            config.max_web_research_loops,
            config.fetch_full_page,
            config.use_tool_calling,
            config.strip_thinking_tokens,
            _mask_secret(config.llm_api_key),
        )

        count = skill_engine.load_all()
        logger.info("SkillEngine loaded %d skill(s)", count)

    @app.get("/healthz")
    def health_check() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/skills")
    def list_skills() -> list[dict[str, Any]]:
        """Return all loaded skill definitions (metadata only, no body)."""
        return [s.to_dict() for s in skill_engine.registry.list_all()]

    @app.post("/skills/reload")
    def reload_skills() -> Dict[str, Any]:
        """Hot-reload skills from the skills directory."""
        count = skill_engine.reload()
        return {"status": "ok", "count": count}

    # -- Knowledge Base API ------------------------------------------------

    @app.post("/knowledge/upload")
    async def upload_knowledge(file: UploadFile = File(...)) -> dict[str, Any]:
        """Upload a file (PDF/DOCX/MD/TXT) to the RAG knowledge base."""
        import tempfile, os
        suffix = os.path.splitext(file.filename or "")[1] or ".txt"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            from rag.ingest import ingest_file
            count = ingest_file(tmp_path, collection="knowledge_base")
            return {"status": "ok", "filename": file.filename, "chunks": count}
        except Exception as e:
            logger.exception("Knowledge upload failed")
            return {"status": "error", "message": str(e)}
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    @app.get("/knowledge/stats")
    def knowledge_stats() -> dict[str, Any]:
        """Get knowledge base statistics."""
        try:
            from rag.store import get_vector_store
            store = get_vector_store()
            return {
                "total_chunks": store.count("knowledge_base"),
                "collections": store.list_collections(),
            }
        except Exception as e:
            return {"error": str(e)}

    # -- Memory API --------------------------------------------------------

    @app.get("/memory/history")
    def list_history(limit: int = 20) -> list[dict[str, Any]]:
        """List past research sessions."""
        store = get_memory_store()
        return store.list_sessions(limit=limit)

    @app.get("/memory/history/{session_id}")
    def get_history(session_id: str) -> dict[str, Any] | None:
        """Get a specific session by ID."""
        store = get_memory_store()
        session = store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return session

    @app.delete("/memory/history/{session_id}")
    def delete_history(session_id: str) -> dict[str, str]:
        """Delete a session from history."""
        store = get_memory_store()
        store.delete_session(session_id)
        return {"status": "ok"}

    @app.get("/memory/preferences")
    def list_preferences() -> dict[str, str]:
        """Get all user preferences."""
        store = get_memory_store()
        return store.list_preferences()

    @app.post("/memory/preferences")
    def set_preference(payload: dict[str, str]) -> dict[str, str]:
        """Set a user preference."""
        store = get_memory_store()
        for key, value in payload.items():
            store.set_preference(key, value)
        return {"status": "ok"}

    @app.get("/memory/faqs")
    def list_faqs(limit: int = 20) -> list[dict[str, Any]]:
        """List frequently asked questions."""
        store = get_memory_store()
        return store.list_faqs(limit=limit)

    @app.post("/memory/check-topic")
    def check_topic_similarity(payload: dict[str, str]) -> dict[str, Any]:
        """Check if similar topics exist in memory."""
        topic = payload.get("topic", "")
        if not topic:
            raise HTTPException(status_code=400, detail="topic is required")
        similar = check_similar_topic(topic)
        return {"topic": topic, "similar_count": len(similar), "similar": similar}

    @app.post("/research", response_model=ResearchResponse)
    def run_research(payload: ResearchRequest) -> ResearchResponse:
        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config)
            result = agent.run(payload.topic)
        except ValueError as exc:  # Likely due to unsupported configuration
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive guardrail
            raise HTTPException(status_code=500, detail="Research failed") from exc

        todo_payload = [
            {
                "id": item.id,
                "title": item.title,
                "intent": item.intent,
                "query": item.query,
                "status": item.status,
                "summary": item.summary,
                "sources_summary": item.sources_summary,
                "note_id": item.note_id,
                "note_path": item.note_path,
            }
            for item in result.todo_items
        ]

        return ResearchResponse(
            report_markdown=(result.report_markdown or result.running_summary or ""),
            todo_items=todo_payload,
        )

    @app.post("/research/stream")
    def stream_research(payload: ResearchRequest) -> StreamingResponse:
        try:
            config = _build_config(payload)
            agent = DeepResearchAgent(config=config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        def event_iterator() -> Iterator[str]:
            try:
                for event in agent.run_stream(payload.topic):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:  # pragma: no cover - defensive guardrail
                logger.exception("Streaming research failed")
                error_payload = {"type": "error", "detail": str(exc)}
                yield f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_iterator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
