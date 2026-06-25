import os
from typing import Any, List, Optional

from pydantic import create_model

from .models import LLMConfig, MarkdownifyRequest, ScrapeRequest, SearchRequest

# Required in Docker: chromium won't launch without --no-sandbox inside a container
_DOCKER_BROWSER_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]

_JSON_SCHEMA_TYPES: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _schema_to_pydantic(name: str, schema: dict) -> type | None:
    """Recursively convert a JSON Schema object definition to a Pydantic model class.

    Handles flat schemas, nested objects, and arrays of primitives or objects.
    Returns None if the schema has no properties (can't create a meaningful model).
    """
    props = schema.get("properties", {})
    if not props:
        return None

    required = set(schema.get("required", []))
    fields: dict[str, Any] = {}

    for field_name, field_schema in props.items():
        field_type_str = field_schema.get("type", "string")

        if field_type_str == "object" and "properties" in field_schema:
            py_type: Any = _schema_to_pydantic(field_name.capitalize(), field_schema) or dict
        elif field_type_str == "array":
            items = field_schema.get("items", {})
            item_type_str = items.get("type", "string")
            if item_type_str == "object" and "properties" in items:
                item_py = _schema_to_pydantic(field_name.capitalize() + "Item", items) or dict
            else:
                item_py = _JSON_SCHEMA_TYPES.get(item_type_str, Any)
            py_type = List[item_py]
        else:
            py_type = _JSON_SCHEMA_TYPES.get(field_type_str, Any)

        if field_name in required:
            fields[field_name] = (py_type, ...)
        else:
            fields[field_name] = (Optional[py_type], None)

    return create_model(name, **fields)


def _openai_compatible_instance(model: str, base_url: str, api_key: str, model_tokens: int) -> dict:
    """Build a ScrapeGraphAI llm config that targets an OpenAI-compatible endpoint
    (e.g. the DarkTower LiteLLM gateway) via a pre-constructed client.

    Passing the client as `model_instance` (rather than a "openai/<model>" string)
    bypasses ScrapeGraphAI's token-table lookup, which has no entry for gateway model
    names like "ocr"/gemma — letting us declare the true context window instead.
    """
    from langchain_openai import ChatOpenAI

    instance = ChatOpenAI(model=model, base_url=base_url, api_key=api_key, temperature=0)
    return {"model_instance": instance, "model_tokens": model_tokens}


def build_graph_config(llm: LLMConfig, headless: bool = True) -> dict:
    # Resolve provider/model from the request, falling back to the project's env
    # defaults. With nothing set, this defaults to gemma4:12b via the LiteLLM gateway
    # (provider=openai, model=ocr, OPENAI_BASE_URL pointing at the gateway).
    provider = (llm.provider or os.getenv("LLM_PROVIDER") or "openai").lower()
    model = llm.model or os.getenv("LLM_MODEL") or "ocr"
    model_tokens = int(os.getenv("LLM_MODEL_TOKENS", "128000"))
    llm_cfg: dict[str, Any]

    if provider == "ollama":
        base = llm.base_url or os.getenv("DEFAULT_OLLAMA_BASE_URL") or ""
        llm_cfg = {"model": f"ollama/{model}"}
        if base:
            llm_cfg["base_url"] = base
    elif provider == "openai":
        key = llm.api_key or os.getenv("OPENAI_API_KEY") or ""
        base = llm.base_url or os.getenv("OPENAI_BASE_URL") or ""
        if base:
            # Custom OpenAI-compatible endpoint (the DarkTower LiteLLM gateway).
            # Build the client ourselves and pass it as `model_instance` so
            # ScrapeGraphAI skips its built-in token-table lookup (which has no
            # entry for "ocr"/gemma) and we can declare the real 128K context.
            llm_cfg = _openai_compatible_instance(model, base, key, model_tokens)
        else:
            llm_cfg = {"model": f"openai/{model}", "openai_api_key": key}
    elif provider == "anthropic":
        key = llm.api_key or os.getenv("ANTHROPIC_API_KEY") or ""
        llm_cfg = {"model": f"anthropic/{model}", "anthropic_api_key": key}
    else:
        # Generic passthrough for any provider langchain supports (e.g. "groq", "mistral")
        base = llm.base_url or os.getenv("OPENAI_BASE_URL") or ""
        if base:
            llm_cfg = _openai_compatible_instance(model, base, llm.api_key or "", model_tokens)
        else:
            llm_cfg = {"model": f"{provider}/{model}"}
            if llm.api_key:
                llm_cfg["api_key"] = llm.api_key

    return {
        "llm": llm_cfg,
        "headless": headless,
        "loader_kwargs": {"args": _DOCKER_BROWSER_ARGS},
    }


def run_smart_scraper(req: ScrapeRequest) -> Any:
    from scrapegraphai.graphs import SmartScraperGraph

    cfg = build_graph_config(req.llm, headless=req.headless)
    pydantic_schema = _schema_to_pydantic("ScrapeSchema", req.schema) if req.schema else None
    graph = SmartScraperGraph(
        prompt=req.prompt, source=req.url, config=cfg, schema=pydantic_schema
    )
    return graph.run()


def run_search(req: SearchRequest) -> Any:
    from scrapegraphai.graphs import SearchGraph

    cfg = build_graph_config(req.llm)
    cfg["max_results"] = req.max_results
    pydantic_schema = _schema_to_pydantic("SearchSchema", req.schema) if req.schema else None
    graph = SearchGraph(prompt=req.prompt, config=cfg, schema=pydantic_schema)
    return graph.run()


def run_markdownify(req: MarkdownifyRequest) -> str:
    from scrapegraphai.graphs import MarkdownifyGraph

    # MarkdownifyGraph extends BaseGraph directly — no LLM needed, just fetch + convert
    node_config = {
        "headless": True,
        "loader_kwargs": {"args": _DOCKER_BROWSER_ARGS},
    }
    graph = MarkdownifyGraph(llm_model=None, node_config=node_config)
    result, _ = graph.execute({"url": req.url})
    return result.get("markdown", "")
