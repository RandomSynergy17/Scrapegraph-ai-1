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


def build_graph_config(llm: LLMConfig, headless: bool = True) -> dict:
    llm_cfg: dict[str, Any]

    if llm.provider == "ollama":
        base = llm.base_url or os.getenv("DEFAULT_OLLAMA_BASE_URL") or ""
        llm_cfg = {"model": f"ollama/{llm.model}"}
        if base:
            llm_cfg["base_url"] = base
    elif llm.provider == "openai":
        key = llm.api_key or os.getenv("OPENAI_API_KEY") or ""
        llm_cfg = {"model": f"openai/{llm.model}", "openai_api_key": key}
    elif llm.provider == "anthropic":
        key = llm.api_key or os.getenv("ANTHROPIC_API_KEY") or ""
        llm_cfg = {"model": f"anthropic/{llm.model}", "anthropic_api_key": key}
    else:
        # Generic passthrough for any provider langchain supports (e.g. "groq", "mistral")
        llm_cfg = {"model": f"{llm.provider}/{llm.model}"}
        if llm.api_key:
            llm_cfg["api_key"] = llm.api_key
        if llm.base_url:
            llm_cfg["base_url"] = llm.base_url

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
