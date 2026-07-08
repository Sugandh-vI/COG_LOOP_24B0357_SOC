#!/usr/bin/env python3
"""
capstone.py — State-driven Planner Agent using Groq API.

Usage:
    python capstone.py                  # prompts for a goal
    python capstone.py "My big goal"    # pass goal as CLI arg

The agent writes all progress to plan.json.  Kill it at any point and
rerun — it will resume from the first unfinished step automatically.
"""

import json
import os
import re
import sys
import time
import textwrap

from dotenv import load_dotenv
from groq import Groq, RateLimitError, BadRequestError

from tools import TOOLS, dispatch_tool

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

_api_key = os.environ.get("GROQ_API_KEY")
if not _api_key:
    sys.exit(
        "ERROR: GROQ_API_KEY not found.  "
        "Copy .env.example → .env and add your key."
    )

client = Groq(api_key=_api_key)
MODEL = "llama-3.3-70b-versatile"
PLAN_FILE = "plan.json"

# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------

PLANNER_PERSONA = textwrap.dedent("""\
    You are AXIS — an autonomous project-manager agent.
    Style: terse, precise, zero fluff.  No hedging.  No pleasantries.
    When you produce text, produce only what was asked for.
    When you call a tool, call exactly one tool per turn.
    When a step is complete, write a tight, factual result summary — no padding.
    """)

# ---------------------------------------------------------------------------
# Groq reliability wrapper — exponential back-off on 429
# ---------------------------------------------------------------------------

def call_llm(messages: list, tools: list | None = None, max_retries: int = 5):
    """
    One Groq call, hardened against HTTP 429 with exponential backoff.
    Every LLM call in the project goes through here — no exceptions.
    """
    delay = 2
    for attempt in range(max_retries):
        try:
            # Build kwargs conditionally — Groq rejects tool_choice=None;
            # only omit or pass the string "auto" / "required" / "none".
            kwargs: dict = {"model": MODEL, "messages": messages}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            return client.chat.completions.create(**kwargs)
        except RateLimitError:
            if attempt == max_retries - 1:
                raise
            print(f"    ⏳  rate-limited (429) — backing off {delay}s …")
            time.sleep(delay)
            delay *= 2   # 2 → 4 → 8 → 16 → 32 s
    raise RuntimeError("exhausted retries without success")


# ---------------------------------------------------------------------------
# plan.json helpers
# ---------------------------------------------------------------------------

def load_plan() -> dict:
    """Read plan.json; return {} if the file is empty / missing / invalid."""
    if not os.path.exists(PLAN_FILE):
        return {}
    try:
        with open(PLAN_FILE, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
        if not text:
            return {}
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"⚠  {PLAN_FILE} is corrupt — resetting to empty plan.")
        return {}


def save_plan(plan: dict) -> None:
    """Atomically write plan to disk (temp-file → rename for crash safety)."""
    tmp = PLAN_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, PLAN_FILE)   # atomic on POSIX; best-effort on Windows


def get_step(plan: dict, step_id: int) -> dict | None:
    """Return the step dict with the given id, or None."""
    for s in plan.get("steps", []):
        if s["id"] == step_id:
            return s
    return None


# ---------------------------------------------------------------------------
# Planning — decompose the goal into ordered steps
# ---------------------------------------------------------------------------

def make_plan(goal: str) -> dict:
    """
    Ask the LLM to decompose *goal* into an ordered list of tasks.
    Returns a fully-formed plan dict ready to save.
    """
    print(f"\n🧠  Decomposing goal into steps …\n    Goal: {goal}\n")

    messages = [
        {"role": "system", "content": PLANNER_PERSONA},
        {
            "role": "user",
            "content": (
                f"Goal: {goal}\n\n"
                "Break this goal into 4–7 clear, ordered, self-contained steps.\n"
                "Respond with ONLY raw JSON — no markdown fences, no preamble, no trailing text.\n"
                "Schema:\n"
                '{"steps": [{"id": 1, "task": "..."}, {"id": 2, "task": "..."}, ...]}'
            ),
        },
    ]

    resp = call_llm(messages)   # no tools here — pure reasoning
    raw = resp.choices[0].message.content.strip()

    # Strip accidental markdown fences if the model disobeyed
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    parsed = json.loads(raw)   # let it raise — bad JSON = hard stop with clear error

    steps = []
    for item in parsed["steps"]:
        steps.append(
            {
                "id": item["id"],
                "task": item["task"],
                "status": "pending",
                "result": None,
            }
        )

    plan = {
        "goal": goal,
        "status": "in_progress",
        "current_step": steps[0]["id"],
        "steps": steps,
    }

    print(f"📋  Plan created — {len(steps)} steps:")
    for s in steps:
        print(f"    Step {s['id']}: {s['task']}")
    print()
    return plan


# ---------------------------------------------------------------------------
# Context builder — bounded token cost
# ---------------------------------------------------------------------------

def build_step_context(plan: dict, step: dict) -> list:
    """
    Build the minimal message list for executing one step.
    Token cost is O(1) — we never send the full steps array.
    """
    messages = [
        {"role": "system", "content": PLANNER_PERSONA},
        {"role": "user", "content": f"Overall goal: {plan['goal']}"},
    ]

    prev = get_step(plan, step["id"] - 1)
    if prev and prev.get("result"):
        summary = prev["result"][:300]   # hard cap — one step back only
        messages.append(
            {
                "role": "user",
                "content": f"Result of the previous step: {summary}",
            }
        )

    messages.append(
        {
            "role": "user",
            "content": (
                f"Now do exactly this step, nothing else:\n{step['task']}\n\n"
                "Use a tool if it helps.  When you are finished, "
                "write a concise factual result summary as plain text."
            ),
        }
    )
    return messages


# ---------------------------------------------------------------------------
# Reason → Act → Observe loop (tool-use inner loop for one step)
# ---------------------------------------------------------------------------

def execute_step(plan: dict, step: dict) -> str:
    """
    Run one step to completion using a reason-act-observe loop.
    Returns the final result text for that step.
    """
    print(f"▶  Step {step['id']}: {step['task']}")

    messages = build_step_context(plan, step)
    MAX_TOOL_TURNS = 6   # safeguard against infinite tool loops

    for turn in range(MAX_TOOL_TURNS):
        try:
            resp = call_llm(messages, tools=TOOLS)
        except BadRequestError as exc:
            # Groq rejected the accumulated message history (e.g. malformed
            # tool-call args from the model).  Fall back: rebuild a clean
            # context and ask for a plain-text answer with no tools.
            print(f"   ⚠  BadRequest on turn {turn} ({exc}) — retrying without tools.")
            clean = build_step_context(plan, step)
            clean.append({"role": "user",
                          "content": "Provide a concise plain-text answer without calling any tools."})
            resp = call_llm(clean)   # no tools kwarg → no tool_choice
            result = (resp.choices[0].message.content or "").strip()
            print(f"   ✅  Done (fallback) — result ({len(result)} chars)")
            return result

        choice = resp.choices[0]
        msg = choice.message

        # — Reason phase: model returned a final text answer —
        if not msg.tool_calls:
            result = (msg.content or "").strip()
            print(f"   ✅  Done — result ({len(result)} chars)")
            return result

        # Validate that every tool_call has parseable arguments before
        # appending to history — a malformed call would poison the next turn.
        valid_calls = []
        for tc in msg.tool_calls:
            try:
                json.loads(tc.function.arguments)
                valid_calls.append(tc)
            except json.JSONDecodeError:
                print(f"   ⚠  Skipping unparseable tool call: {tc.function.name}")

        if not valid_calls:
            # Model tried to call tools but all were malformed — treat
            # the model's content (if any) as the result.
            result = (msg.content or "Step complete (tool args were malformed).").strip()
            print(f"   ✅  Done (no valid tool calls) — result ({len(result)} chars)")
            return result

        # — Act phase: append valid assistant tool_calls to history —
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in valid_calls
                ],
            }
        )

        # — Observe phase: execute every valid tool call in this turn —
        for tc in valid_calls:
            tool_name = tc.function.name
            tool_args = json.loads(tc.function.arguments)  # safe — already validated above

            print(f"   🔧  Tool call: {tool_name}({list(tool_args.keys())})")
            observation = dispatch_tool(tool_name, tool_args)
            print(f"   👁  Observation: {observation[:120]}{'…' if len(observation) > 120 else ''}")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": observation,
                }
            )

    # If we exhaust tool turns without a final text answer, ask one last time
    # without tools so we always get a usable string back.
    print(f"   ⚠  Max tool turns reached — collecting final answer.")
    clean = build_step_context(plan, step)
    clean.append({"role": "user",
                  "content": "Summarise what you have found so far in plain text."})
    resp = call_llm(clean)
    return (resp.choices[0].message.content or "Step complete.").strip()


# ---------------------------------------------------------------------------
# Main orchestration loop (stateless / crash-safe)
# ---------------------------------------------------------------------------

def run_agent(goal: str | None = None) -> None:
    """
    The main agentic loop.  Entirely driven by plan.json — the Python
    process itself holds no in-RAM state that matters.
    """

    while True:
        # 1. Load state from disk ─────────────────────────────────────────
        plan = load_plan()

        # 2. No plan yet → create one ─────────────────────────────────────
        if not plan:
            if goal is None:
                print("No existing plan found.")
                goal = input("Enter your goal: ").strip()
                if not goal:
                    sys.exit("No goal provided — exiting.")
            plan = make_plan(goal)
            save_plan(plan)
            print(f"💾  plan.json written.\n")
            continue   # loop back to reload from disk (validates the save)

        # ── Goal mismatch handling ─────────────────────────────────────────
        existing_goal = plan.get("goal", "")

        if goal and existing_goal != goal:
            # Explicit new goal provided — always start fresh.
            print(f"🔄  New goal detected — replacing old plan.")
            print(f"    Old: \"{existing_goal}\"")
            print(f"    New: \"{goal}\"\n")
            save_plan({})
            plan = make_plan(goal)
            save_plan(plan)
            print(f"💾  plan.json written.\n")
            continue   # reload from disk

        # 3. Find the first non-done step ─────────────────────────────────
        pending = [s for s in plan["steps"] if s["status"] != "done"]

        # 4. All done → print summary and exit ────────────────────────────
        if not pending:
            plan["status"] = "done"
            save_plan(plan)
            print("\n" + "═" * 60)
            print("🎉  ALL STEPS COMPLETE")
            print("═" * 60)
            print(f"Goal: {plan['goal']}\n")
            for s in plan["steps"]:
                print(f"  Step {s['id']}: {s['task']}")
                snippet = (s["result"] or "")[:200]
                print(f"    → {snippet}")
            print("═" * 60)
            break

        # 5. Execute the next step ─────────────────────────────────────────
        step = pending[0]
        step["status"] = "in_progress"
        plan["current_step"] = step["id"]
        save_plan(plan)   # mark in_progress before doing the work

        result = execute_step(plan, step)

        # 6. Save result, mark done ────────────────────────────────────────
        step["status"] = "done"
        step["result"] = result

        # Advance current_step pointer to the next pending step (or keep last)
        remaining = [s for s in plan["steps"] if s["status"] != "done"]
        if remaining:
            plan["current_step"] = remaining[0]["id"]
        else:
            plan["current_step"] = step["id"]  # last step just finished

        save_plan(plan)
        print(f"💾  Step {step['id']} saved.\n")
        # loop back to step 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    goal_arg = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else None
    try:
        run_agent(goal_arg)
    except KeyboardInterrupt:
        print("\n\n⛔  Interrupted.  Progress saved to plan.json — rerun to resume.")
        sys.exit(0)


if __name__ == "__main__":
    main()
