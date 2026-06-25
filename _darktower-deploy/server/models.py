from typing import Any

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """LLM selection. Every field is optional — any unset field falls back to the
    server's env defaults (LLM_PROVIDER / LLM_MODEL / OPENAI_BASE_URL / OPENAI_API_KEY,
    resolved in scraper.build_graph_config). Omit `llm` entirely to use the project
    default: gemma4:12b via the DarkTower LiteLLM gateway."""

    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None


class ScrapeRequest(BaseModel):
    url: str
    prompt: str
    llm: LLMConfig = Field(default_factory=LLMConfig)
    headless: bool = True
    schema: dict | None = None


class SearchRequest(BaseModel):
    prompt: str
    llm: LLMConfig = Field(default_factory=LLMConfig)
    max_results: int = 5
    schema: dict | None = None


class MarkdownifyRequest(BaseModel):
    url: str


class ScrapeResponse(BaseModel):
    result: Any
    graph: str
