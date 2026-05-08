from typing import Any

from pydantic import BaseModel


class LLMConfig(BaseModel):
    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None


class ScrapeRequest(BaseModel):
    url: str
    prompt: str
    llm: LLMConfig
    headless: bool = True
    schema: dict | None = None


class SearchRequest(BaseModel):
    prompt: str
    llm: LLMConfig
    max_results: int = 5
    schema: dict | None = None


class MarkdownifyRequest(BaseModel):
    url: str


class ScrapeResponse(BaseModel):
    result: Any
    graph: str
