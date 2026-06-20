# Cognition Loop SOC — AI Agent Project

A Groq-powered autonomous agent project built across three weeks, covering API basics, tool calling, browser automation, and multi-turn ReAct agents.

## Tech Stack

- **LLM**: Groq API — `llama-3.3-70b-versatile`
- **Browser Automation**: Playwright (Chromium)
- **Package Manager**: `uv`
- **Environment**: Python 3.11+

---

## Setup

### 1. Install Dependencies

```bash
uv sync
```

### 2. Install Chromium for Playwright

```bash
uv run playwright install chromium
```

### 3. Environment Variables

Create a `.env` file in the project root (never commit this):

```
GROQ_API_KEY=YOUR_KEY_HERE
```

> `.env` is already listed in `.gitignore`.

---

## Running the Scripts

### Week 1 — Infrastructure and Control

```bash
# Task 2 — Simple Groq API call
uv run python basic_call.py

# Task 3 — Rate limit handling with exponential backoff (15 calls)
uv run python rate_limit_handler.py

# Task 4 — Victorian butler persona
uv run python persona_call.py

# Task 5 — JSON extraction from unstructured text
uv run python json_extractor.py
```

**Expected outputs:**

| Script | Expected output |
|---|---|
| `basic_call.py` | One-sentence answer about Newton's Second Law |
| `rate_limit_handler.py` | `Request 1 successful`, ..., `Rate limit hit, retrying...` (if limit hit) |
| `persona_call.py` | Victorian butler response to a weather question |
| `json_extractor.py` | `['Python', 'SQL', 'Tableau']` |

---

### Week 2 — Tool Calling and Browser Automation

```bash
# Task 1 — Groq tool-calling agent (live crypto prices via CoinGecko)
uv run python basic_tool.py

# Task 2 — Hacker News headline scraper (Playwright)
uv run python browser_test.py

# Task 3 — YouTube search + autoplay (Playwright, headless=False)
uv run python youtube_autoplay.py
```

---

### Week 3 — ReAct Agents with Web Search

```bash
# Task 1 — One-shot research agent (DuckDuckGo + Groq ReAct loop)
uv run python research_agent.py

# Task 2 — Persistent memory chat agent with two tools + tool chaining
uv run python chat_agent.py
```

`chat_agent.py` supports multi-turn conversation with memory. Type `quit` to exit.

---

## File Reference

| File | Week | Description |
|---|---|---|
| `basic_call.py` | 1 | Simple Groq API call |
| `rate_limit_handler.py` | 1 | 15-call loop with retry + exponential backoff |
| `persona_call.py` | 1 | System-instruction persona (Victorian butler) |
| `json_extractor.py` | 1 | Structured JSON extraction from raw text |
| `basic_tool.py` | 2 | Groq tool-calling agent with CoinGecko |
| `browser_test.py` | 2 | Playwright Hacker News scraper |
| `youtube_autoplay.py` | 2 | Playwright YouTube search + autoplay |
| `research_agent.py` | 3 | ReAct loop with `search_the_web` tool |
| `chat_agent.py` | 3 | Multi-turn chat agent with memory + 2 tools |

---

## Notes

- All LLM calls use Groq — no Gemini, no OpenAI.
- API keys are loaded via `python-dotenv` from `.env`.
- No secrets are hardcoded.
