# ScrapeGraphAI — Integration Guide

A shared web-scraping and search service running on Darktower. Any project on the network
can call it via REST or wire Claude Code agents to it via MCP.

Interactive API docs (Swagger UI): **https://scrapegraph.randomsynergy.xyz/docs**

---

## Service Details

| | |
|---|---|
| **Public URL** | `https://scrapegraph.randomsynergy.xyz` |
| **Internal URL** | `http://192.168.2.125:3277` (Darktower LAN only) |
| **Health check** | `GET /api/health` → `{"status":"ok"}` |
| **MCP endpoint** | `https://scrapegraph.randomsynergy.xyz/mcp` |
| **OpenAPI / Swagger** | `https://scrapegraph.randomsynergy.xyz/docs` |
| **Portainer stack** | `https://portainer.randomsynergy.xyz/#!/2/docker/stacks/scrapegraph` |
| **Container** | `scrapegraph-server` on Darktower |

---

## What It Exposes

Three capabilities from the ScrapeGraphAI library, each backed by a different graph:

| Endpoint | Graph | LLM required | Description |
|---|---|---|---|
| `POST /api/scrape` | SmartScraperGraph | yes | Fetch a URL with Playwright, extract structured data using an LLM prompt |
| `POST /api/search` | SearchGraph | yes | Web search across N pages, synthesised into an answer by an LLM |
| `POST /api/markdownify` | MarkdownifyGraph | **no** | Fetch a URL and return its content as clean Markdown |

### Graphs NOT exposed by this service

The ScrapeGraphAI library has additional graphs that are not available through this API:

| Graph | Why not exposed |
|---|---|
| SmartScraperMultiGraph | Scrapes multiple URLs in parallel — future addition |
| ScriptCreatorGraph | Generates Python scraping scripts |
| DepthSearchGraph | Recursive site crawling |
| SpeechGraph | Text-to-audio pipeline |
| CodeGeneratorGraph | Code generation from web content |
| JSONScraperGraph | Scrapes JSON/XML sources |

If you need any of these, open a request or extend the server source in `_darktower-deploy/server/`.

---

## LLM Configuration

All scrape/search requests include an `llm` object. Keys travel in the request body — nothing
is stored server-side except the fallback keys configured in Portainer.

```json
{
  "provider": "anthropic",
  "model": "claude-haiku-4-5-20251001",
  "api_key": "sk-ant-..."
}
```

### Supported Providers

| `provider` | `model` examples | Notes |
|---|---|---|
| `anthropic` | `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-opus-4-7` | Omit `api_key` to use server fallback |
| `openai` | `gpt-4o-mini`, `gpt-4o`, `o1-mini` | Omit `api_key` to use server fallback |
| `ollama` | `llama3.2:3b-instruct-q5_K_M`, `qwen2.5:14b`, `mistral` | Free — Darktower's Ollama used by default |
| `groq` | `llama3-8b-8192`, `mixtral-8x7b-32768` | Pass your Groq key in `api_key` |
| `gemini` | `gemini/gemini-pro`, `gemini/gemini-flash` | Pass your Google key in `api_key` |
| `mistral` | `mistral/mistral-small` | Pass your Mistral key in `api_key` |

**Server fallback keys** (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) are set in Portainer. Omit
`api_key` to use them. Pass your own key per-request to bill to a different account.

**Ollama** runs on Darktower at `http://192.168.2.125:11434`. Omit `base_url` to route there
automatically. Pass an explicit `base_url` to use a different Ollama instance.

To see which Ollama models are available on Darktower:
```bash
ssh randolph@darktower.lynx-alpha.ts.net "docker exec ollama ollama list"
```

### Model Selection Guide

| Model | Cost | Speed | Best for |
|---|---|---|---|
| `anthropic/claude-haiku-4-5-20251001` | Low | Fast | Default choice for most scraping |
| `anthropic/claude-sonnet-4-6` | Medium | Medium | Complex extraction, multi-step reasoning |
| `openai/gpt-4o-mini` | Low | Fast | OpenAI alternative to Haiku |
| `openai/gpt-4o` | High | Medium | When cheaper models miss structured output |
| `ollama/llama3.2:3b-instruct-q5_K_M` | Free | Fast | High-volume, zero API cost, lower accuracy |
| `groq/llama3-8b-8192` | Low | Very fast | Speed-critical pipelines with Groq API |

---

## REST API Reference

### `GET /api/health`

```bash
curl https://scrapegraph.randomsynergy.xyz/api/health
# → {"status":"ok"}
```

---

### `POST /api/scrape`

Scrapes a single URL with Playwright and extracts information matching your prompt.

**Request body**

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `url` | string | yes | — | Full URL including scheme |
| `prompt` | string | yes | — | Natural language extraction instruction |
| `llm` | LLMConfig | yes | — | See LLM Configuration |
| `headless` | bool | no | `true` | Browser visibility — always `true` server-side |
| `schema` | object | no | `null` | JSON Schema for guaranteed output structure (see below) |

**Minimal request**
```json
{
  "url": "https://example.com",
  "prompt": "What is the page title and main content summary?",
  "llm": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}
}
```

**With structured schema**
```json
{
  "url": "https://github.com/trending",
  "prompt": "List the top 5 trending repositories",
  "llm": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
  "schema": {
    "properties": {
      "repositories": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name":        {"type": "string"},
            "description": {"type": "string"},
            "stars":       {"type": "integer"},
            "language":    {"type": "string"}
          },
          "required": ["name", "stars"]
        }
      }
    },
    "required": ["repositories"]
  }
}
```

**Response**
```json
{
  "result": {
    "repositories": [
      {"name": "anthropics/claude-code", "description": "...", "stars": 12400, "language": "TypeScript"},
      ...
    ]
  },
  "graph": "SmartScraperGraph"
}
```

`result` shape matches your schema when one is provided. Without a schema, it's whatever the
LLM returns — dict, list, or string.

---

### `POST /api/search`

Searches the web, fetches the top N result pages, and synthesises an answer with an LLM.

**Request body**

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `prompt` | string | yes | — | Search query or question to answer |
| `llm` | LLMConfig | yes | — | |
| `max_results` | int | no | `5` | Number of pages to fetch and synthesise |
| `schema` | object | no | `null` | JSON Schema for structured output |

**Request**
```json
{
  "prompt": "What are the main new features in Python 3.13?",
  "llm": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
  "max_results": 5
}
```

**With structured schema**
```json
{
  "prompt": "List the top Python web frameworks with their GitHub star counts",
  "llm": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
  "max_results": 5,
  "schema": {
    "properties": {
      "frameworks": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name":  {"type": "string"},
            "stars": {"type": "integer"},
            "url":   {"type": "string"}
          },
          "required": ["name"]
        }
      }
    }
  }
}
```

**Response**
```json
{
  "result": "Python 3.13 introduces a new interactive interpreter (REPL), ...",
  "graph": "SearchGraph"
}
```

---

### `POST /api/markdownify`

Fetches a URL and returns its content as clean Markdown. No LLM — fast and free.
Use this for RAG ingestion, content diffing, or feeding text to your own pipeline.

**Request**
```json
{
  "url": "https://docs.python.org/3/library/asyncio.html"
}
```

**Response**
```json
{
  "result": "# asyncio — Asynchronous I/O\n\nSource code: Lib/asyncio/\n\n...",
  "graph": "MarkdownifyGraph"
}
```

---

## Structured Output (Schema)

The `schema` field is the most reliable way to get consistent output from `scrape` and `search`.
It converts your JSON Schema definition into a Pydantic model that ScrapeGraphAI passes directly
to the LLM, which constrains the response format at the model level — not just via prompt text.

### JSON Schema quick reference

```json
{
  "properties": {
    "field_name": {"type": "string"},
    "count":      {"type": "integer"},
    "price":      {"type": "number"},
    "active":     {"type": "boolean"},
    "tags":       {"type": "array", "items": {"type": "string"}},
    "address": {
      "type": "object",
      "properties": {
        "street": {"type": "string"},
        "city":   {"type": "string"}
      },
      "required": ["city"]
    }
  },
  "required": ["field_name"]
}
```

Supported types: `string`, `integer`, `number`, `boolean`, `array`, `object`.
Fields not listed in `required` are optional (returned as `null` if not found).

### When to use schema vs prompt-only

| Approach | When to use |
|---|---|
| Schema | You need a predictable dict/list structure your code will access by key |
| Prompt-only | Free-form text answer, or one-off exploration |
| Both together | Schema defines structure; prompt describes what to fill in |

---

## Code Examples

### Python — basic scrape

```python
import requests

BASE = "https://scrapegraph.randomsynergy.xyz"

# Simple extraction
r = requests.post(f"{BASE}/api/scrape", json={
    "url": "https://news.ycombinator.com",
    "prompt": "List the top 5 story titles and their point counts",
    "llm": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
}, timeout=120)

print(r.json()["result"])
# {"stories": [{"title": "...", "points": 312}, ...]}
```

### Python — structured schema extraction

```python
import requests, json

BASE = "https://scrapegraph.randomsynergy.xyz"

schema = {
    "properties": {
        "company":   {"type": "string"},
        "founded":   {"type": "integer"},
        "employees": {"type": "integer"},
        "products": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name":        {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["name"]
            }
        }
    },
    "required": ["company"]
}

r = requests.post(f"{BASE}/api/scrape", json={
    "url": "https://stripe.com/about",
    "prompt": "Extract company information and their main products",
    "llm": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    "schema": schema,
}, timeout=120)

data = r.json()["result"]
# data is now a reliable dict — no need to parse LLM text
print(data["company"])      # "Stripe"
print(data["products"])     # [{"name": "Payments", "description": "..."}, ...]
```

### Python — web search

```python
import requests

BASE = "https://scrapegraph.randomsynergy.xyz"

r = requests.post(f"{BASE}/api/search", json={
    "prompt": "What are the latest developments in AI coding assistants in 2025?",
    "llm": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    "max_results": 5,
}, timeout=120)

print(r.json()["result"])
```

### Python — markdownify for RAG ingestion

```python
import requests

BASE = "https://scrapegraph.randomsynergy.xyz"

urls = [
    "https://docs.example.com/guide",
    "https://docs.example.com/api-reference",
    "https://docs.example.com/quickstart",
]

documents = []
for url in urls:
    r = requests.post(f"{BASE}/api/markdownify", json={"url": url}, timeout=60)
    if r.ok:
        documents.append({
            "url": url,
            "content": r.json()["result"],
        })

# Now chunk and embed documents[*]["content"] into your vector store
```

### Python — httpx (async-friendly)

```python
import httpx

BASE = "https://scrapegraph.randomsynergy.xyz"

with httpx.Client(timeout=120) as client:
    r = client.post(f"{BASE}/api/scrape", json={
        "url": "https://example.com",
        "prompt": "Extract the main heading and paragraph text",
        "llm": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    })
    r.raise_for_status()
    print(r.json()["result"])
```

```python
# Async version
import httpx
import asyncio

async def scrape(url: str, prompt: str) -> dict:
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post("https://scrapegraph.randomsynergy.xyz/api/scrape", json={
            "url": url,
            "prompt": prompt,
            "llm": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        })
        r.raise_for_status()
        return r.json()["result"]
```

### JavaScript / Node.js

```javascript
const BASE = "https://scrapegraph.randomsynergy.xyz";

// Scrape with schema
const schema = {
  properties: {
    title:       { type: "string" },
    author:      { type: "string" },
    publishDate: { type: "string" },
    tags:        { type: "array", items: { type: "string" } },
  },
  required: ["title"],
};

const res = await fetch(`${BASE}/api/scrape`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    url: "https://example.com/article",
    prompt: "Extract article metadata",
    llm: { provider: "anthropic", model: "claude-haiku-4-5-20251001" },
    schema,
  }),
  signal: AbortSignal.timeout(120_000),
});

const { result } = await res.json();
console.log(result.title);   // guaranteed to exist (in required)
console.log(result.author);  // may be null (not required)

// Markdownify
const md = await fetch(`${BASE}/api/markdownify`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ url: "https://example.com" }),
  signal: AbortSignal.timeout(60_000),
});
const { result: markdown } = await md.json();
```

### TypeScript — typed client

```typescript
const BASE = "https://scrapegraph.randomsynergy.xyz";

interface LLMConfig {
  provider: "anthropic" | "openai" | "ollama" | "groq" | "gemini" | string;
  model: string;
  api_key?: string;
  base_url?: string;
}

interface JSONSchema {
  type?: string;
  properties?: Record<string, JSONSchema>;
  items?: JSONSchema;
  required?: string[];
}

interface ScrapeRequest {
  url: string;
  prompt: string;
  llm: LLMConfig;
  headless?: boolean;
  schema?: JSONSchema;
}

interface SearchRequest {
  prompt: string;
  llm: LLMConfig;
  max_results?: number;
  schema?: JSONSchema;
}

interface ScrapeResponse<T = unknown> {
  result: T;
  graph: string;
}

async function scrape<T = unknown>(req: ScrapeRequest): Promise<T> {
  const r = await fetch(`${BASE}/api/scrape`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal: AbortSignal.timeout(120_000),
  });
  if (!r.ok) throw new Error(`scrape ${r.status}: ${await r.text()}`);
  const data: ScrapeResponse<T> = await r.json();
  return data.result;
}

async function searchWeb<T = unknown>(req: SearchRequest): Promise<T> {
  const r = await fetch(`${BASE}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal: AbortSignal.timeout(120_000),
  });
  if (!r.ok) throw new Error(`search ${r.status}: ${await r.text()}`);
  const data: ScrapeResponse<T> = await r.json();
  return data.result;
}

async function markdownify(url: string): Promise<string> {
  const r = await fetch(`${BASE}/api/markdownify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
    signal: AbortSignal.timeout(60_000),
  });
  if (!r.ok) throw new Error(`markdownify ${r.status}: ${await r.text()}`);
  const data: ScrapeResponse<string> = await r.json();
  return data.result;
}

// Usage
interface Repo { name: string; stars: number; language?: string }
interface TrendingResult { repositories: Repo[] }

const trending = await scrape<TrendingResult>({
  url: "https://github.com/trending",
  prompt: "List the top 10 trending repositories",
  llm: { provider: "anthropic", model: "claude-haiku-4-5-20251001" },
  schema: {
    properties: {
      repositories: {
        type: "array",
        items: {
          type: "object",
          properties: {
            name:     { type: "string" },
            stars:    { type: "integer" },
            language: { type: "string" },
          },
          required: ["name", "stars"],
        },
      },
    },
    required: ["repositories"],
  },
});

trending.repositories.forEach(r => console.log(`${r.name}: ${r.stars}★`));
```

### cURL

```bash
# Scrape with schema
curl -s -X POST https://scrapegraph.randomsynergy.xyz/api/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "prompt": "Extract page title and description",
    "llm": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    "schema": {
      "properties": {
        "title":       {"type": "string"},
        "description": {"type": "string"}
      },
      "required": ["title"]
    }
  }' | jq .

# Search
curl -s -X POST https://scrapegraph.randomsynergy.xyz/api/search \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Latest AI news","llm":{"provider":"anthropic","model":"claude-haiku-4-5-20251001"},"max_results":3}' \
  | jq .

# Markdownify (no LLM, fast)
curl -s -X POST https://scrapegraph.randomsynergy.xyz/api/markdownify \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}' | jq -r .result

# Ollama — no API key, routes to Darktower's Ollama
curl -s -X POST https://scrapegraph.randomsynergy.xyz/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","prompt":"Summarise this page","llm":{"provider":"ollama","model":"llama3.2:3b-instruct-q5_K_M"}}' \
  | jq .
```

---

## MCP Integration (Claude Code)

### Add to a project

Create or edit `.claude/mcp.json` in the project root:

```json
{
  "mcpServers": {
    "scrapegraph": {
      "type": "http",
      "url": "https://scrapegraph.randomsynergy.xyz/mcp"
    }
  }
}
```

Or add globally (available to all projects):

```bash
claude mcp add scrapegraph --transport http https://scrapegraph.randomsynergy.xyz/mcp
```

Verify it's registered:
```bash
claude mcp list
```

### Available MCP Tools

**`smart_scrape`** — Scrape a URL and extract information

```
smart_scrape(
  url:          str,       # Full URL to scrape
  prompt:       str,       # What to extract
  llm_provider: str,       # "anthropic" | "openai" | "ollama"
  llm_model:    str,       # Model name
  api_key:      str = "",  # Optional — uses server fallback if omitted
  base_url:     str = "",  # Optional — Ollama base URL
) -> str
```

**`search_web`** — Search the web and synthesise an answer

```
search_web(
  prompt:       str,
  llm_provider: str,
  llm_model:    str,
  max_results:  int = 5,
  api_key:      str = "",
  base_url:     str = "",
) -> str
```

**`markdownify`** — Fetch a URL and return clean Markdown (no LLM)

```
markdownify(url: str) -> str
```

### Example agent interactions

```
User: Scrape the GitHub trending page and summarise the top 5 repos

Claude: [calls smart_scrape(
  url="https://github.com/trending",
  prompt="List the top 5 trending repositories with name, description, and star count",
  llm_provider="anthropic",
  llm_model="claude-haiku-4-5-20251001"
)]
```

```
User: Fetch the FastAPI docs intro page and give me a markdown version I can paste

Claude: [calls markdownify(url="https://fastapi.tiangolo.com")]
```

```
User: What's the current state of Rust async ecosystem?

Claude: [calls search_web(
  prompt="Current state of Rust async ecosystem 2025: main libraries, patterns, and maturity",
  llm_provider="anthropic",
  llm_model="claude-sonnet-4-6",
  max_results=5
)]
```

---

## Best Practices

### Picking the right endpoint

| Goal | Endpoint | Why |
|---|---|---|
| Extract data from a specific URL | `/api/scrape` | Targets one page directly |
| Answer a question needing web research | `/api/search` | Finds and reads multiple sources |
| Feed page content into your own pipeline | `/api/markdownify` | No LLM cost, fast, predictable output |
| RAG document ingestion | `/api/markdownify` | Cheapest way to get clean text from URLs |
| Monitor a page for changes | `/api/scrape` with a fixed prompt | Same URL + prompt → comparable results over time |
| Competitive intelligence | `/api/search` or `/api/scrape` | Search for broad picture; scrape specific pages |

### Writing effective prompts

```python
# Too vague — LLM returns whatever it thinks is relevant
"Tell me about this page"

# Better — specific extraction with expected shape
"Extract the page title, author name, publication date, and a 2-sentence summary"

# Best with schema — the schema enforces structure, the prompt describes what to fill in
prompt  = "Extract article metadata"
schema  = {"properties": {"title": {"type": "string"}, "author": {"type": "string"}}, "required": ["title"]}

# Lists — always specify count and fields
"Return a JSON array of up to 10 products. Each item must have: name (string), price (number, USD), url (string), in_stock (boolean)"

# Search — frame as a question to synthesise, not a raw query
"What are the main differences between Redis and Valkey? Summarise pros and cons."
```

### Timeout configuration

Playwright must render the full page before the LLM sees it. Set client timeouts generously.

| Endpoint | Typical | Worst case |
|---|---|---|
| `/api/markdownify` | 3–10s | 25s |
| `/api/scrape` | 15–45s | 90s |
| `/api/search` | 20–60s | 120s |

Use **120s minimum** for scrape and search. For concurrent batch jobs, stagger requests.

### Error handling

```python
import requests

def safe_scrape(url: str, prompt: str, llm: dict) -> dict | None:
    try:
        r = requests.post(
            "https://scrapegraph.randomsynergy.xyz/api/scrape",
            json={"url": url, "prompt": prompt, "llm": llm},
            timeout=120,
        )
        if r.status_code == 422:
            raise ValueError(f"Bad request: {r.json()}")
        if r.status_code == 500:
            # Page blocked scraping, LLM failure, or JS timeout
            print(f"Scrape failed for {url}: {r.text}")
            return None
        r.raise_for_status()
        return r.json()["result"]
    except requests.Timeout:
        print(f"Timeout scraping {url}")
        return None
```

### Result handling

Without a schema, `result` may be a `dict`, `list`, or `str`:

```python
result = r.json()["result"]

if isinstance(result, dict):
    value = result.get("field")
elif isinstance(result, list):
    for item in result:
        process(item)
else:
    # Plain text
    print(result)
```

With a schema, `result` is always a `dict` matching your schema:

```python
result = r.json()["result"]
print(result["title"])      # always present — it's in required
print(result.get("author")) # may be None — not in required
```

### Shared service considerations

This is a single container with one Playwright instance. Keep in mind:

- **No queue** — concurrent heavy scrapes compete for CPU/browser. Stagger batch jobs.
- **Stateless** — each request is fully independent. No sessions, no cookies carried between requests.
- **Not authenticated** — accessible to anything that can reach Darktower. Don't log sensitive data in prompts.
- **Ollama shares Darktower resources** — during model inference, the server may be slower for other containers. Use Anthropic/OpenAI for latency-sensitive paths.

---

## Usage Patterns

### Pattern: RAG ingestion pipeline

```python
import requests

BASE = "https://scrapegraph.randomsynergy.xyz"

def ingest_urls(urls: list[str]) -> list[dict]:
    docs = []
    for url in urls:
        r = requests.post(f"{BASE}/api/markdownify", json={"url": url}, timeout=60)
        if r.ok:
            docs.append({"url": url, "content": r.json()["result"]})
        else:
            print(f"Failed to fetch {url}: {r.status_code}")
    return docs

# Then chunk and embed docs[*]["content"] into your vector store
pages = ingest_urls([
    "https://docs.myapp.com/intro",
    "https://docs.myapp.com/api",
    "https://docs.myapp.com/faq",
])
```

### Pattern: Guaranteed structured extraction

```python
import requests

def scrape_product(url: str) -> dict | None:
    r = requests.post("https://scrapegraph.randomsynergy.xyz/api/scrape", json={
        "url": url,
        "prompt": "Extract product information",
        "llm": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        "schema": {
            "properties": {
                "name":          {"type": "string"},
                "price":         {"type": "number"},
                "currency":      {"type": "string"},
                "in_stock":      {"type": "boolean"},
                "rating":        {"type": "number"},
                "review_count":  {"type": "integer"},
                "images":        {"type": "array", "items": {"type": "string"}},
            },
            "required": ["name"],
        },
    }, timeout=120)
    return r.json()["result"] if r.ok else None
```

### Pattern: Competitive pricing monitor

```python
import requests, datetime

def check_pricing(url: str) -> dict:
    r = requests.post("https://scrapegraph.randomsynergy.xyz/api/scrape", json={
        "url": url,
        "prompt": "Extract all pricing plans",
        "llm": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        "schema": {
            "properties": {
                "plans": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":           {"type": "string"},
                            "price":          {"type": "number"},
                            "currency":       {"type": "string"},
                            "billing_period": {"type": "string"},
                            "features":       {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["name"],
                    },
                }
            }
        },
    }, timeout=120)
    return {
        "url": url,
        "checked_at": datetime.datetime.utcnow().isoformat() + "Z",
        "pricing": r.json().get("result") if r.ok else None,
    }
```

### Pattern: Research digest

```python
import requests

def research(topic: str, num_sources: int = 5) -> str:
    r = requests.post("https://scrapegraph.randomsynergy.xyz/api/search", json={
        "prompt": (
            f"Summarise the latest developments in: {topic}. "
            "Include key facts, dates, and cite your sources."
        ),
        "llm": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
        "max_results": num_sources,
    }, timeout=120)
    return r.json()["result"] if r.ok else ""
```

### Pattern: Batch scrape with retry

```python
import requests, time

BASE = "https://scrapegraph.randomsynergy.xyz"
LLM  = {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}

def batch_scrape(jobs: list[dict], delay_s: float = 2.0) -> list[dict]:
    """jobs = [{"url": ..., "prompt": ..., "schema": ...}, ...]"""
    results = []
    for job in jobs:
        for attempt in range(3):
            r = requests.post(f"{BASE}/api/scrape",
                              json={**job, "llm": LLM}, timeout=120)
            if r.ok:
                results.append({"url": job["url"], "result": r.json()["result"]})
                break
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
        else:
            results.append({"url": job["url"], "result": None, "error": r.text})
        time.sleep(delay_s)  # be polite to target sites
    return results
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `500 Internal Server Error` | Site blocks scraping, LLM error, or JS timeout | Simplify prompt; try markdownify first to verify the page loads; try a different model |
| `result` is `null` or `{}` | LLM couldn't match content to your schema/prompt | Make prompt more specific; check the page actually has the content you're requesting |
| Slow response (>60s) | Heavy JS page, large page, slow model | Use Haiku or Ollama; try markdownify to check raw content first |
| Schema fields all `null` | Field names don't match page content | Verify content is on the page; relax `required` constraints; adjust field names in schema |
| Ollama model not found | Model tag mismatch | Run `docker exec ollama ollama list` on Darktower to see exact model tags |
| `422 Unprocessable Entity` | Missing required field | `scrape` needs `url`+`prompt`+`llm`; `search` needs `prompt`+`llm`; `markdownify` needs `url` |
| MCP tools not appearing | Config not loaded | Run `claude mcp list`; restart Claude Code after editing mcp.json |
| `result` is a string not a dict | LLM returned JSON as text, not parsed | Parse with `json.loads(result)` or add a schema to force object output |

---

## Resources

- **ScrapeGraphAI library docs** — https://docs.scrapegraphai.com
- **Interactive API docs (Swagger)** — https://scrapegraph.randomsynergy.xyz/docs
- **Portainer stack** — https://portainer.randomsynergy.xyz/#!/2/docker/stacks/scrapegraph
- **Server source** — `_darktower-deploy/server/` in the ScrapeGraphAI repo
- **Ollama models on Darktower** — `ssh randolph@darktower.lynx-alpha.ts.net "docker exec ollama ollama list"`
- **ScrapeGraphAI GitHub** — https://github.com/ScrapeGraphAI/Scrapegraph-ai
