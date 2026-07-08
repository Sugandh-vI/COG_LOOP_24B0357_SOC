# Planner Agent — AXIS

A **state-driven autonomous agent** that breaks a large goal into ordered steps and executes them one at a time using the Groq API (`llama-3.3-70b-versatile`).  Progress is flushed to `plan.json` after every single step, making the agent fully crash-safe and resumable.

---

## What it does

1. **Takes one big goal** from the user (CLI arg or interactive prompt).
2. **Decomposes it** into 4–7 ordered, self-contained steps via an LLM call.
3. **Works through the steps one at a time**, calling real tools (web search, file writer) when useful.
4. **Writes every result to `plan.json` immediately** — kill the process at any point and rerun; it resumes from the first unfinished step.

### Core components

| Component | What it does |
|-----------|-------------|
| **Voice** | `PLANNER_PERSONA` system prompt — AXIS is a terse, precise project-manager agent |
| **Hands** | Two real tools: `web_search` (DuckDuckGo) and `write_file` (local disk) |
| **Brain** | Reason → Act → Observe loop inside each step — up to 6 tool-call turns |
| **Self** | `plan.json` on disk; the Python process is fully disposable |

---

## Setup

### 1. Install dependencies

```bash
pip install groq python-dotenv
```

### 2. Create your `.env` file

```bash
cp .env.example .env
# now open .env and paste your Groq API key
```

Your `.env` must contain:

```
GROQ_API_KEY=gsk_your_key_here
```

> **The `.env` file is gitignored and must never be committed.**

### 3. Run

```bash
# Interactive — agent will prompt you for a goal
python capstone.py

# Or pass the goal directly on the command line
python capstone.py "Plan my week of study for final exams"
```

---

## Example run

```
$ python capstone.py "Research the top 3 Python web frameworks for 2024 and write a comparison"

🧠  Decomposing goal into steps …
    Goal: Research the top 3 Python web frameworks for 2024 and write a comparison

📋  Plan created — 5 steps:
    Step 1: Search the web for "top Python web frameworks 2024" and identify the top 3
    Step 2: Gather key facts about framework #1 (features, performance, use cases)
    Step 3: Gather key facts about framework #2 (features, performance, use cases)
    Step 4: Gather key facts about framework #3 (features, performance, use cases)
    Step 5: Write a structured comparison of all three frameworks to comparison.md

💾  plan.json written.

▶  Step 1: Search the web for "top Python web frameworks 2024" and identify the top 3
   🔧  Tool call: web_search(['query'])
   👁  Observation: Search results for 'top Python web frameworks 2024':

1. Best Python Web Frameworks in 2024 — FastAPI, Django, Flask...
   FastAPI leads in async performance; Django remains the full-featured…
   ✅  Done — result (312 chars)
💾  Step 1 saved.

▶  Step 2: Gather key facts about framework #1 — FastAPI
   🔧  Tool call: web_search(['query'])
   👁  Observation: Search results for 'FastAPI features performance 2024'…
   ✅  Done — result (428 chars)
💾  Step 2 saved.

^C   ← USER PRESSES Ctrl-C HERE

⛔  Interrupted.  Progress saved to plan.json — rerun to resume.

$ python capstone.py   # ← RESTART

▶  Step 3: Gather key facts about framework #2 — Django
   🔧  Tool call: web_search(['query'])
   👁  Observation: …
   ✅  Done — result (381 chars)
💾  Step 3 saved.

▶  Step 4: Gather key facts about framework #3 — Flask
   🔧  Tool call: web_search(['query'])
   👁  Observation: …
   ✅  Done — result (290 chars)
💾  Step 4 saved.

▶  Step 5: Write a structured comparison to comparison.md
   🔧  Tool call: write_file(['filename', 'content'])
   👁  Observation: Wrote 1842 characters to 'comparison.md'.
   ✅  Done — result (52 chars)
💾  Step 5 saved.

════════════════════════════════════════════════════════════
🎉  ALL STEPS COMPLETE
════════════════════════════════════════════════════════════
Goal: Research the top 3 Python web frameworks for 2024 and write a comparison

  Step 1: Search the web … → Top 3: FastAPI, Django, Flask
  Step 2: FastAPI facts   → Async-first, OpenAPI auto-docs, Pydantic…
  Step 3: Django facts    → Batteries-included, ORM, admin panel…
  Step 4: Flask facts     → Micro-framework, flexible, WSGI…
  Step 5: Write file      → Wrote 1842 characters to 'comparison.md'.
════════════════════════════════════════════════════════════
```

Notice: **Steps 1 and 2 were NOT re-executed** after the restart.  The agent read `plan.json`, saw they were `"done"`, and jumped straight to Step 3.

---

## Resume behaviour

`plan.json` after Ctrl-C (mid-run):

```json
{
  "goal": "Research the top 3 Python web frameworks...",
  "status": "in_progress",
  "current_step": 3,
  "steps": [
    { "id": 1, "task": "...", "status": "done",        "result": "Top 3: FastAPI, Django, Flask" },
    { "id": 2, "task": "...", "status": "done",        "result": "FastAPI: async-first…" },
    { "id": 3, "task": "...", "status": "in_progress", "result": null },
    { "id": 4, "task": "...", "status": "pending",     "result": null },
    { "id": 5, "task": "...", "status": "pending",     "result": null }
  ]
}
```

On restart, the agent scans `steps` for the first entry where `status != "done"` — that's Step 3 — and picks up there.

---

## Starting fresh

```bash
echo '{}' > plan.json     # reset plan
python capstone.py "New goal here"
```

---

## File structure

```
.
├── capstone.py      ← main agent (run this)
├── tools.py         ← web_search + write_file implementations + Groq schemas
├── plan.json        ← agent's persistent brain (committed as {})
├── .env.example     ← template — copy to .env and add your key
├── .env             ← YOUR KEY — gitignored, never commit
├── .gitignore
└── README.md
```

---

## Rate limits (free tier)

Every Groq call goes through `call_llm()`, which retries with exponential backoff on HTTP 429:  
`2s → 4s → 8s → 16s → 32s` (5 attempts).  
Token cost per step is bounded — only the goal, the current task, and a 300-char snippet of the previous step's result are sent.  The full `steps` array and all past results are never injected into the prompt.
