"""
chat_agent.py — Week 3, Task 2
A persistent multi-turn chat agent with:
  - Persistent memory (messages list kept across turns)
  - Tool 1: search_the_web(query)  — DuckDuckGo HTML via Playwright
  - Tool 2: open_page(url)         — Opens a URL and returns visible text
  - Tool chaining: the agent can search, pick a link, then open it
  - Quit with: quit / exit / q

The agent remembers the full conversation, so follow-up questions like
"Who founded it?" work correctly after "What is OpenAI?".
"""

import os
import json
import time
from dotenv import load_dotenv
from groq import Groq
from ddgs import DDGS  # wraps DuckDuckGo API, no bot-detection issues
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

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
    """
    for model in (MODEL_PRIMARY, MODEL_FALLBACK):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
            )
            if model != MODEL_PRIMARY:
                print(f"  [Note] Using fallback model {model} (primary had tool_use_failed)")
            return resp
        except Exception as exc:
            err = str(exc)
            if "tool_use_failed" in err and model == MODEL_PRIMARY:
                print(f"  [Warning] {MODEL_PRIMARY} tool_use_failed, retrying with {MODEL_FALLBACK}...")
                continue
            raise
    raise RuntimeError("Both models failed.")

# ---------------------------------------------------------------------------
# Tool 1 — search_the_web
# ---------------------------------------------------------------------------

def search_the_web(query: str) -> str:
    """
    Search the web via DuckDuckGo (ddgs) and return the top 5 results.

    Uses the ddgs package which calls DuckDuckGo's API without triggering
    bot-detection that blocks headless Playwright scraping.

    Args:
        query: The search query.

    Returns:
        A formatted string with titles, URLs, and snippets.
    """
    print(f"  [Tool] search_the_web({query!r})")
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
# Tool 2 — open_page
# ---------------------------------------------------------------------------

def open_page(url: str) -> str:
    """
    Open a URL and return its visible body text (trimmed to 3000 chars).

    Args:
        url: The URL to open.

    Returns:
        The visible text of the page (up to 3000 characters), or an error message.
    """
    print(f"  [Tool] open_page({url!r})")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=15000)
            text = page.locator("body").inner_text(timeout=10000)
            browser.close()
        return text[:3000]  # Trim to avoid blowing the context window
    except PlaywrightTimeoutError:
        return f"Error: Timed out opening {url}."
    except Exception as exc:
        return f"Error opening page {url}: {exc}"


# ---------------------------------------------------------------------------
# Tool schemas for Groq
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_the_web",
            "description": (
                "Search the live web via DuckDuckGo for current information. "
                "Use this when the user asks about recent events, facts, or "
                "anything a language model might not know."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_page",
            "description": (
                "Open a specific URL and return its full visible text. "
                "Use this to read the content of a webpage, for example "
                "after finding a relevant link with search_the_web."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full URL to open (must start with http:// or https://).",
                    }
                },
                "required": ["url"],
            },
        },
    },
]

AVAILABLE_TOOLS = {
    "search_the_web": search_the_web,
    "open_page": open_page,
}

SYSTEM = (
    "You are a helpful research assistant with two tools: search_the_web and open_page. "
    "Use search_the_web to find current information, and open_page to read a specific URL. "
    "You can chain these tools — for example, search for a topic, then open a result for details. "
    "Always base your answer on the tool results. Remember the full conversation history "
    "so you can answer follow-up questions correctly."
)


# ---------------------------------------------------------------------------
# Inner ReAct loop — runs for a single user turn
# ---------------------------------------------------------------------------

def react_loop(messages: list) -> str:
    """
    Run the ReAct tool-calling loop for one conversation turn.

    Mutates `messages` in place (appends assistant and tool messages).

    Args:
        messages: The full conversation history so far.

    Returns:
        The model's final text answer for this turn.
    """
    max_iterations = 8  # Prevent runaway loops
    for _ in range(max_iterations):
        try:
            response = groq_chat_with_tools(messages, TOOLS)
        except Exception as exc:
            err = f"Error calling Groq API: {exc}"
            messages.append({"role": "assistant", "content": err})
            return err

        msg = response.choices[0].message

        # No tool call → final answer
        if not msg.tool_calls:
            final = msg.content or "(empty response)"
            messages.append({"role": "assistant", "content": final})
            return final

        # Convert Pydantic object → clean dict so extra SDK fields
        # (annotations, executed_tools, reasoning, function_call) are NOT
        # sent back to Groq, which would cause HTTP 400 tool_use_failed.
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

        # Execute each tool and log clearly
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

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fn_name,
                    "content": result,
                }
            )

        # Brief pause to respect API rate limits
        time.sleep(0.5)

    return "Max tool iterations reached. Please rephrase your question."


# ---------------------------------------------------------------------------
# Main chat loop
# ---------------------------------------------------------------------------

def main():
    """Run the persistent multi-turn chat agent."""
    print("=" * 60)
    print("Chat Agent — powered by Groq + Playwright")
    print("Type 'quit', 'exit', or 'q' to stop.")
    print("=" * 60)

    # This list persists across ALL turns — this is the memory
    messages = [{"role": "system", "content": SYSTEM}]

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting. Goodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in {"quit", "exit", "q"}:
            print("Exiting. Goodbye!")
            break

        # Append user turn to the persistent conversation
        messages.append({"role": "user", "content": user_input})

        # Run the ReAct loop for this turn
        answer = react_loop(messages)
        print(f"\nAgent: {answer}")


if __name__ == "__main__":
    main()
