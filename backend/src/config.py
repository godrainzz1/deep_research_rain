import os
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 加载 .env 文件中的环境变量（优先级低于系统环境变量）
_dotenv_path = Path(".env")
if _dotenv_path.exists():
    load_dotenv(dotenv_path=_dotenv_path, override=False)
else:
    import sys
    print("[WARN] .env not found, using system env vars only.", file=sys.stderr)


class SearchAPI(Enum):
    PERPLEXITY = "perplexity"
    TAVILY = "tavily"
    DUCKDUCKGO = "duckduckgo"
    SEARXNG = "searxng"
    HYBRID = "hybrid"
    ADVANCED = "advanced"


class Configuration(BaseModel):
    """Configuration options for the deep research assistant."""

    max_web_research_loops: int = Field(
        default=3,
        title="Research Depth",
        description="Number of research iterations to perform",
    )
    local_llm: str = Field(
        default="llama3.2",
        title="Local Model Name",
        description="Name of the locally hosted LLM (Ollama/LMStudio)",
    )
    llm_provider: str = Field(
        default="",
        title="LLM Provider",
        description="Provider identifier (ollama, lmstudio, or custom). Leave empty to use LLM_BASE_URL/LLM_API_KEY/LLM_MODEL_ID directly.",
    )
    search_api: SearchAPI = Field(
        default=SearchAPI.HYBRID,
        title="Search API",
        description="Web search API to use (hybrid tries multiple backends)",
    )
    enable_notes: bool = Field(
        default=True,
        title="Enable Notes",
        description="Whether to store task progress in NoteTool",
    )
    notes_workspace: str = Field(
        default="./notes",
        title="Notes Workspace",
        description="Directory for NoteTool to persist task notes",
    )
    fetch_full_page: bool = Field(
        default=True,
        title="Fetch Full Page",
        description="Include the full page content in the search results",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        title="Ollama Base URL",
        description="Base URL for Ollama API (without /v1 suffix)",
    )
    lmstudio_base_url: str = Field(
        default="http://localhost:1234/v1",
        title="LMStudio Base URL",
        description="Base URL for LMStudio OpenAI-compatible API",
    )
    strip_thinking_tokens: bool = Field(
        default=True,
        title="Strip Thinking Tokens",
        description="Whether to strip <think> tokens from model responses",
    )
    use_tool_calling: bool = Field(
        default=False,
        title="Use Tool Calling",
        description="Use tool calling instead of JSON mode for structured output",
    )
    llm_api_key: Optional[str] = Field(
        default=None,
        title="LLM API Key",
        description="Optional API key when using custom OpenAI-compatible services",
    )
    llm_base_url: Optional[str] = Field(
        default=None,
        title="LLM Base URL",
        description="Optional base URL when using custom OpenAI-compatible services",
    )
    llm_model_id: Optional[str] = Field(
        default=None,
        title="LLM Model ID",
        description="Optional model identifier for custom OpenAI-compatible services",
    )
    llm_timeout: int = Field(
        default=120,
        title="LLM Timeout",
        description="Timeout in seconds for LLM API calls",
    )
    llm_max_tokens: Optional[int] = Field(
        default=4096,
        title="LLM Max Tokens",
        description="Maximum output tokens per LLM call. Thinking models (plus/turbo) need 4096+ to leave room after CoT.",
    )
    llm_fallback_provider: str = Field(
        default="",
        title="Fallback LLM Provider",
        description="Provider for automatic fallback when primary LLM fails (e.g. ollama)",
    )
    llm_fallback_model_id: Optional[str] = Field(
        default=None,
        title="Fallback LLM Model ID",
        description="Model ID for automatic fallback LLM",
    )
    llm_fallback_base_url: Optional[str] = Field(
        default=None,
        title="Fallback LLM Base URL",
        description="Base URL for automatic fallback LLM",
    )

    @classmethod
    def from_env(cls, overrides: Optional[dict[str, Any]] = None) -> "Configuration":
        """Create a configuration object using environment variables and overrides."""

        raw_values: dict[str, Any] = {}

        # Load values from environment variables based on field names
        for field_name in cls.model_fields.keys():
            env_key = field_name.upper()
            if env_key in os.environ:
                raw_values[field_name] = os.environ[env_key]

        # Additional mappings for explicit env names & provider-specific aliases
        env_aliases = {
            "local_llm": os.getenv("LOCAL_LLM"),
            "llm_provider": os.getenv("LLM_PROVIDER"),
            "llm_api_key": os.getenv("LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY"),
            "llm_model_id": os.getenv("LLM_MODEL_ID"),
            "llm_base_url": os.getenv("LLM_BASE_URL"),
            "lmstudio_base_url": os.getenv("LMSTUDIO_BASE_URL"),
            "ollama_base_url": os.getenv("OLLAMA_BASE_URL"),
            "max_web_research_loops": os.getenv("MAX_WEB_RESEARCH_LOOPS"),
            "fetch_full_page": os.getenv("FETCH_FULL_PAGE"),
            "strip_thinking_tokens": os.getenv("STRIP_THINKING_TOKENS"),
            "use_tool_calling": os.getenv("USE_TOOL_CALLING"),
            "search_api": os.getenv("SEARCH_API"),
            "enable_notes": os.getenv("ENABLE_NOTES"),
            "notes_workspace": os.getenv("NOTES_WORKSPACE"),
            "llm_timeout": os.getenv("LLM_TIMEOUT"),
            "llm_max_tokens": os.getenv("LLM_MAX_TOKENS"),
            "llm_fallback_provider": os.getenv("LLM_FALLBACK_PROVIDER"),
            "llm_fallback_model_id": os.getenv("LLM_FALLBACK_MODEL_ID"),
            "llm_fallback_base_url": os.getenv("LLM_FALLBACK_BASE_URL"),
        }

        for key, value in env_aliases.items():
            if value is not None:
                raw_values.setdefault(key, value)

        # Auto-detect DashScope when DASHSCOPE_API_KEY is present
        if os.getenv("DASHSCOPE_API_KEY") and not raw_values.get("llm_base_url"):
            raw_values.setdefault("llm_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            raw_values.setdefault("llm_model_id", "qwen3.6-plus")

        if overrides:
            for key, value in overrides.items():
                if value is not None:
                    raw_values[key] = value

        return cls(**raw_values)

    def sanitized_ollama_url(self) -> str:
        """Ensure Ollama base URL includes the /v1 suffix required by OpenAI clients."""

        base = self.ollama_base_url.rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        return base

    def resolved_model(self) -> Optional[str]:
        """Best-effort resolution of the model identifier to use."""

        return self.llm_model_id or self.local_llm

