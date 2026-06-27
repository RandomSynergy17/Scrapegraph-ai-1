# Use the DarkTower ScrapeGraphAI service (for LLM agents)

> **Drop this file into any project.** It tells an AI coding agent (Claude Code, etc.) how to
> call the shared **ScrapeGraphAI** web-scraping service running on DarkTower — turn any URL or
> web question into **structured JSON**. **No LLM key required:** by default it uses the local
> **gemma4:12b** model via the DarkTower LiteLLM gateway (free, on-box, private). Override to a
> cloud model per-request only when you need to.

---

## The endpoint (not a secret)

| | |
|---|---|
| **Public (anywhere)** | `https://scrapegraph.randomsynergy.xyz` |
| **Tailscale (off-box)** | `http://darktower.lynx-alpha.ts.net:3277` |
| **LAN / on-box** | `http://192.168.2.125:3277` (or `http://localhost:3277` on DarkTower) |
| **Auth** | none — internal service |
| **Protocol** | REST (JSON) + an MCP streamable-HTTP endpoint at `/mcp` (remote-enabled — see [MCP](#mcp-model-context-protocol)) |
| **Health** | `GET /api/health` → `{"status":"ok"}` |

REST works from **all three** base URLs. Use the public URL unless you're on the Tailnet/LAN.

---

## What it does — three capabilities

| Endpoint | Graph | Use it for |
|---|---|---|
| `POST /api/scrape` | SmartScraperGraph | Fetch **one URL** with a real browser (Playwright) and extract structured data from a prompt |
| `POST /api/search` | SearchGraph | Answer a **web question** — searches, fetches several pages, synthesises a cited answer |
| `POST /api/markdownify` | MarkdownifyGraph | Fetch a URL → **clean Markdown**, no LLM (fast, free; good for RAG ingestion) |

All requests render JavaScript (headless Chromium), so SPAs and dynamic pages work.

---

## 🤖 AGENT INSTRUCTIONS — how to use this service

1. **Default to the simplest call.** For "get X off this page", `POST /api/scrape` with just `url` +
   `prompt`. **Omit `llm`** — it uses gemma4:12b automatically. Add a `schema` whenever you need a
   guaranteed shape (you almost always do — parse the `result` object directly).
2. **Pick the endpoint by task shape:** one known URL → `/api/scrape`; an open web question → `/api/search`;
   just need the page text → `/api/markdownify`.
3. **Set a generous client timeout.** Local gemma is ~48 tok/s. Budget **120 s** for scrape, **300 s** for
   search (see [Latency](#latency--limits)). The browser fetch alone can take a few seconds.
4. **Override the model only when it pays off** — see [Choosing the LLM](#choosing-the-llm). Reach for
   `anthropic`/cloud when you need speed or the page is genuinely hard.
5. **Read `result`**: scrape/search return `{"result": <your data or {...schema}>, "graph": "..."}`.

---

## Quickest start (curl)

```bash
BASE=https://scrapegraph.randomsynergy.xyz

# Scrape one page (default gemma4:12b — no llm needed)
curl -sS --max-time 120 "$BASE/api/scrape" -H "Content-Type: application/json" -d '{
  "url": "https://example.com",
  "prompt": "What is the page title and a one-line summary?"
}'
# → {"result":{"content":"..."},"graph":"SmartScraperGraph"}
```

## Scrape with a schema (recommended — guaranteed structure)

```bash
curl -sS --max-time 180 "$BASE/api/scrape" -H "Content-Type: application/json" -d '{
  "url": "https://news.ycombinator.com",
  "prompt": "Extract the top 5 stories on the front page.",
  "schema": {
    "type": "object",
    "properties": {
      "stories": { "type": "array", "items": {
        "type": "object",
        "properties": {
          "rank":  {"type": "integer"},
          "title": {"type": "string"},
          "points":{"type": "integer"}
        }
      }}
    }
  }
}'
# → {"result":{"stories":[{"rank":1,"title":"...","points":719}, ...]},"graph":"SmartScraperGraph"}
```

## Web research + synthesis

```bash
curl -sS --max-time 300 "$BASE/api/search" -H "Content-Type: application/json" -d '{
  "prompt": "What is the James Webb Space Telescope and name three notable discoveries?",
  "max_results": 3,
  "schema": {"type":"object","properties":{
    "summary":{"type":"string"},
    "discoveries":{"type":"array","items":{"type":"string"}}
  }}
}'
# → {"result":{"summary":"...","discoveries":["...","...","..."],"sources":[...]},"graph":"SearchGraph"}
```

## Markdown (no LLM)

```bash
curl -sS --max-time 60 "$BASE/api/markdownify" -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
# → {"result":"# Example Domain\n...","graph":"MarkdownifyGraph"}
```

---

## REST reference

### `POST /api/scrape`
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `url` | string | yes | — | Full URL incl. scheme |
| `prompt` | string | yes | — | Natural-language extraction instruction |
| `schema` | object | no | `null` | JSON Schema → guaranteed output shape |
| `llm` | object | no | gemma4:12b via LiteLLM | Override; see below |
| `headless` | bool | no | `true` | Always headless server-side |

### `POST /api/search`
Same as scrape but **no `url`**; add `max_results` (int, default `5`) — pages fetched + synthesised.

### `POST /api/markdownify`
`{ "url": "..." }` only. No LLM, no cost.

---

## Choosing the LLM

**Default (omit `llm`)** → `gemma4:12b` (LiteLLM alias `ocr`, `think:false`, 128K context) — free,
on-box, private. Good for the large majority of extraction/synthesis. Override per request:

```jsonc
// Cloud Claude (faster, for hard pages) — uses the server's Anthropic key:
"llm": { "provider": "anthropic", "model": "claude-haiku-4-5-20251001" }

// Any LiteLLM gateway model (e.g. reasoning alias, or a cloud model):
"llm": { "provider": "openai", "model": "chat-smart",
         "base_url": "http://192.168.2.125:51366/v1", "api_key": "<litellm-key>" }

// Direct Ollama on DarkTower (bypass the gateway):
"llm": { "provider": "ollama", "model": "gemma4:12b" }
```

`provider` ∈ `openai` · `anthropic` · `ollama` · `groq` · `gemini` · `mistral` · … Pass `api_key`
per-request to bill a different account, or omit to use the server fallback.

**Rule of thumb:** default gemma for cost/privacy; `anthropic` (or `openai/ds-v4-pro` via the gateway)
when latency matters or extraction is failing. In tests gemma matched Claude-Haiku on structured
extraction quality, ~2–3× slower.

---

## MCP (Model Context Protocol)

The service exposes an MCP **streamable-HTTP** endpoint at `/mcp` with tools `smart_scrape`,
`search_web`, `markdownify` (same `llm_provider`/`llm_model` optional args — leave empty for the
gemma default). It is **reachable remotely** over the public and Tailscale URLs.

**Add it to Claude Code** (native tools, no key needed):
```bash
claude mcp add --transport http scrapegraph https://scrapegraph.randomsynergy.xyz/mcp
```
…or add to `~/.claude.json` → top-level `mcpServers`:
```json
"scrapegraph": { "type": "http", "url": "https://scrapegraph.randomsynergy.xyz/mcp" }
```

Smoke test (works from anywhere):
```bash
curl -sS https://scrapegraph.randomsynergy.xyz/mcp -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
# → tools: smart_scrape, search_web, markdownify
```

> The MCP SDK's DNS-rebinding Host allowlist (localhost-only by default) is intentionally disabled
> for this server-side service, so remote `Host` headers are accepted — matching the open REST API.
> The endpoint is unauthenticated; add auth at NPM if you need to lock it down.

---

## Latency & limits

- **Simple page** (default gemma): ~5–10 s · **schema-heavy page** (e.g. HN front page): ~30 s ·
  **web-research synthesis** (`/api/search`, 3 sources): ~3 min. Cloud override (`anthropic`) is ~2–3× faster.
- Stateless, **no queue** — concurrent requests compete for the single container + the shared local GPU
  (`OLLAMA_NUM_PARALLEL=1`), so heavy local-model concurrency serialises. Batch politely.
- One Playwright/Chromium container; very heavy pages may need a higher client timeout.

---

## Python / Node one-liners

```python
import requests
BASE = "https://scrapegraph.randomsynergy.xyz"
r = requests.post(f"{BASE}/api/scrape", timeout=180, json={
    "url": "https://arxiv.org/abs/1706.03762",
    "prompt": "Extract title, authors, year.",
    "schema": {"type":"object","properties":{
        "title":{"type":"string"},
        "authors":{"type":"array","items":{"type":"string"}},
        "year":{"type":"integer"}}},
})
print(r.json()["result"])
```

```js
const BASE = "https://scrapegraph.randomsynergy.xyz";
const res = await fetch(`${BASE}/api/scrape`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ url: "https://example.com", prompt: "One-line summary?" }),
});
console.log((await res.json()).result);
```

---

Service source + full integration guide: this repo's `_darktower-deploy/` (`INTEGRATION.md`). LLM
default is controlled by env on Portainer stack 182; swapping the default model is an `.env` change or
a central LiteLLM alias swap (see `_darktower-deploy/INTEGRATION.md`).
