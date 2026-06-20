"""
research_agent.py — Week 3, Task 1
A ReAct-loop agent that uses Groq (llama-3.3-70b-versatile) to reason and
Playwright to search the live web via DuckDuckGo HTML.

Loop:
  1. User asks a question.
  2. Groq decides whether to call search_the_web().
  3. If yes → Playwright scrapes DuckDuckGo → results sent back to Groq.
  4. Steps 2-3 repeat until Groq produces a final answer (no tool call).
  5. Print TOOL CALL and FINAL ANSWER blocks.
"""

import os
import json
import time
from dotenv import load_dotenv
from groq import Groq
from ddgs import DDGS  # pip: ddgs — wraps DuckDuckGo API, no bot-detection issues

# Load environment variables from .env file
load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise EnvironmentError("GROQ_API_KEY not found. Please set it in your .env file.")

client = Groq(api_key=api_key)

# Primary model — kept per assignment spec.
# Fallback used if primary generates malformed tool calls (Groq-side bug).
MODEL_PRIMARY = "llama-3.3-70b-versatile"
MODEL_FALLBACK = "llama-3.1-8b-instant"  # confirmed working for tool calls
MODEL = MODEL_PRIMARY  # default used in single-call scripts


def groq_chat_with_tools(messages: list, tools: list, tool_choice: str = "auto"):
    """
    Call Groq with automatic fallback on tool_use_failed.

    llama-3.3-70b-versatile occasionally emits malformed tool-call XML
    which Groq rejects with HTTP 400 / tool_use_failed. When that happens
    we transparently retry with llama-3.1-8b-instant.

    Returns the response object, and sets a module-level ACTIVE_MODEL
    so callers know which model was used.
    """
    global ACTIVE_MODEL
    for model in (MODEL_PRIMARY, MODEL_FALLBACK):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
            )
            ACTIVE_MODEL = model
            if model != MODEL_PRIMARY:
                print(f"[Note] Using fallback model {model} (primary had tool_use_failed)")
            return resp
        except Exception as exc:
            err = str(exc)
            if "tool_use_failed" in err and model == MODEL_PRIMARY:
                # Primary generated malformed tool call — try fallback
                print(f"[Warning] {MODEL_PRIMARY} tool_use_failed, retrying with {MODEL_FALLBACK}...")
                continue
            raise  # Any other error (network, auth, etc.) → propagate
    raise RuntimeError("Both models failed.")


ACTIVE_MODEL = MODEL_PRIMARY

# ---------------------------------------------------------------------------
# Tool implementation — Playwright + DuckDuckGo HTML (no JS required)
# ---------------------------------------------------------------------------

def search_the_web(query: str) -> str:
    """
    Search the web via DuckDuckGo and return the top 5 results as plain text.

    Uses the `ddgs` package (DuckDuckGo official API) which bypasses
    bot-detection that blocks headless Playwright scraping.

    Args:
        query: The search query string.

    Returns:
        A formatted string with titles, URLs, and snippets.
    """
    print(f"\nTOOL CALL: search_the_web(query={query!r})\n")
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=5))

        if not raw:
            return "No results found for this query."

        results = []
        for r in raw:
            title = r.get("title", "").strip()
            snippet = r.get("body", "").strip()
            url = r.get("href", "").strip()
            results.append(f"Title: {title}\nURL: {url}\nSnippet: {snippet}")

        return "\n\n".join(results)

    except Exception as exc:
        return f"Error during web search: {exc}"


# ---------------------------------------------------------------------------
# Tool schema for Groq
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_the_web",
            "description": (
                "Search the live web for current information. "
                "Use it whenever the question needs recent or factual data "
                "that a language model might not know."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    }
                },
                "required": ["query"],
            },
        },
    }
]

AVAILABLE_TOOLS = {"search_the_web": search_the_web}

SYSTEM = (
    "You are a research assistant with a live web search tool. "
    "When a question needs current or real-world facts, call search_the_web "
    "before answering. Base your answer on the search results, and say so "
    "if they don't contain the answer. "
    "When you have enough information, provide your FINAL ANSWER directly."
)


def run_research_agent(user_question: str) -> str:
    """
    Run the ReAct loop until Groq produces a final answer.

    Args:
        user_question: The user's question.

    Returns:
        The final answer string.
    """
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_question},
    ]

    max_iterations = 6  # Safety cap — prevent infinite loops
    for _ in range(max_iterations):
        try:
            response = groq_chat_with_tools(messages, TOOLS)
        except Exception as exc:
            return f"Error calling Groq API: {exc}"

        msg = response.choices[0].message

        # No tool call → model has produced its final answer
        if not msg.tool_calls:
            return msg.content or "(empty response)"

        # Convert Pydantic object → clean dict to avoid HTTP 400.
        # The SDK object contains extra fields (annotations, executed_tools,
        # function_call, reasoning) that Groq rejects when sent back.
        messages.append({
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
                for tc in msg.tool_calls
            ],
        })

        # Execute each tool and add results
        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            if fn_name in AVAILABLE_TOOLS:
                result = AVAILABLE_TOOLS[fn_name](**fn_args)
            else:
                result = f"Error: unknown tool '{fn_name}'"

            print(f"\nTOOL RESULT:\n{result[:500]}\n")  # Print first 500 chars

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fn_name,
                    "content": result,
                }
            )

        # Small delay to respect rate limits between loop iterations
        time.sleep(1)

    return "Max iterations reached without a final answer."


def main():
    question = "What are the latest developments in field of IPL  likely trades happening?"
    print(f"User Question: {question}\n")
    answer = run_research_agent(question)
    print(f"\nFINAL ANSWER:\n{answer}")


if __name__ == "__main__":
    main()
