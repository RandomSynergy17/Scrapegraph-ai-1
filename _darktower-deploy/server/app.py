import asyncio
import contextlib

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from . import scraper
from .models import MarkdownifyRequest, ScrapeRequest, ScrapeResponse, SearchRequest

mcp_server = FastMCP("scrapegraph", stateless_http=True)


@mcp_server.tool()
async def smart_scrape(
    url: str,
    prompt: str,
    llm_provider: str = "",
    llm_model: str = "",
    api_key: str = "",
    base_url: str = "",
) -> str:
    """Scrape a URL and extract structured information based on a prompt.

    Leave llm_provider/llm_model empty to use the project default
    (gemma4:12b via the DarkTower LiteLLM gateway)."""
    from .models import LLMConfig

    req = ScrapeRequest(
        url=url,
        prompt=prompt,
        llm=LLMConfig(
            provider=llm_provider or None,
            model=llm_model or None,
            api_key=api_key or None,
            base_url=base_url or None,
        ),
    )
    result = await asyncio.to_thread(scraper.run_smart_scraper, req)
    return str(result)


@mcp_server.tool()
async def search_web(
    prompt: str,
    llm_provider: str = "",
    llm_model: str = "",
    max_results: int = 5,
    api_key: str = "",
    base_url: str = "",
) -> str:
    """Search the web for information and summarise the results using an LLM.

    Leave llm_provider/llm_model empty to use the project default
    (gemma4:12b via the DarkTower LiteLLM gateway)."""
    from .models import LLMConfig

    req = SearchRequest(
        prompt=prompt,
        llm=LLMConfig(
            provider=llm_provider or None,
            model=llm_model or None,
            api_key=api_key or None,
            base_url=base_url or None,
        ),
        max_results=max_results,
    )
    result = await asyncio.to_thread(scraper.run_search, req)
    return str(result)


@mcp_server.tool()
async def markdownify(url: str) -> str:
    """Fetch a URL and return its content as clean Markdown (no LLM required)."""
    result = await asyncio.to_thread(scraper.run_markdownify, MarkdownifyRequest(url=url))
    return result


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title="ScrapeGraphAI Server", version="1.0.0", lifespan=lifespan)

# REST endpoints under /api/ — defined first so they take priority over the MCP mount
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/scrape", response_model=ScrapeResponse)
async def scrape(req: ScrapeRequest):
    result = await asyncio.to_thread(scraper.run_smart_scraper, req)
    return ScrapeResponse(result=result, graph="SmartScraperGraph")


@app.post("/api/search", response_model=ScrapeResponse)
async def search(req: SearchRequest):
    result = await asyncio.to_thread(scraper.run_search, req)
    return ScrapeResponse(result=result, graph="SearchGraph")


@app.post("/api/markdownify", response_model=ScrapeResponse)
async def markdownify_endpoint(req: MarkdownifyRequest):
    result = await asyncio.to_thread(scraper.run_markdownify, req)
    return ScrapeResponse(result=result, graph="MarkdownifyGraph")


# MCP transport mounted at / — inner app serves /mcp, so client URL is just /mcp
app.mount("/", mcp_server.streamable_http_app())
