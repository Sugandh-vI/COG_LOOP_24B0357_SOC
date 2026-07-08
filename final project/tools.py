
"""
tools.py — Real tool implementations for the Planner Agent.

Two tools are available:
  1. web_search   – Fetches a DuckDuckGo search results page and returns the
                    first N result snippets as plain text. No API key needed.
  2. write_file   – Writes arbitrary text content to a local file.

The TOOLS list holds the Groq-compatible JSON schema for each tool so it can
be passed directly as the `tools` argument to the Groq client.
"""

import ssl
import urllib.parse
import urllib.request
import re
import json
import os

# macOS ships Python without the system CA bundle linked, so HTTPS requests
# via urllib fail with SSL_CERTIFICATE_VERIFY_FAILED.  Create an unverified
# context for this internal scraper tool (no auth data is sent).
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


# ---------------------------------------------------------------------------
# Tool schemas (Groq / OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for information on a topic and return a "
                "plain-text summary of the top results. Use this whenever "
                "you need current data, facts, or research you don't have."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to run.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 5).",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write text content to a local file. Use this to save "
                "step outputs, timetables, summaries, or any artifact that "
                "should persist after the agent finishes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "The file name (or relative path) to write to.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The text content to write into the file.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["overwrite", "append"],
                        "description": "Whether to overwrite or append. Default is overwrite.",
                        "default": "overwrite",
                    },
                },
                "required": ["filename", "content"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def web_search(query: str, max_results: int = 5) -> str:
    """
    Perform a DuckDuckGo HTML search and extract result titles + snippets.
    Returns a plain-text string with numbered results.
    No external dependencies beyond the stdlib.
    """
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return f"[web_search error: {exc}]"

    # Extract result titles and snippets with simple regex (no external parsers)
    titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</span>', html, re.DOTALL)

    def strip_tags(s: str) -> str:
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"&amp;", "&", s)
        s = re.sub(r"&lt;", "<", s)
        s = re.sub(r"&gt;", ">", s)
        s = re.sub(r"&quot;", '"', s)
        s = re.sub(r"&#x27;", "'", s)
        s = re.sub(r"&nbsp;", " ", s)
        return s.strip()

    titles = [strip_tags(t) for t in titles]
    snippets = [strip_tags(s) for s in snippets]

    results = []
    for i, (title, snippet) in enumerate(zip(titles, snippets), start=1):
        if i > max_results:
            break
        results.append(f"{i}. {title}\n   {snippet}")

    if not results:
        return f"No results found for query: {query!r}"

    return f"Search results for '{query}':\n\n" + "\n\n".join(results)


def write_file(filename: str, content: str, mode: str = "overwrite") -> str:
    """
    Write (or append) text content to a local file.
    Returns a confirmation string.
    """
    file_mode = "a" if mode == "append" else "w"
    try:
        parent = os.path.dirname(filename)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(filename, file_mode, encoding="utf-8") as fh:
            fh.write(content)

        action = "Appended to" if mode == "append" else "Wrote"
        return f"{action} {len(content)} characters to '{filename}'."
    except Exception as exc:
        return f"[write_file error: {exc}]"


# ---------------------------------------------------------------------------
# Dispatcher — called by the agent's reason-act-observe loop
# ---------------------------------------------------------------------------

def dispatch_tool(tool_name: str, tool_args: dict) -> str:
    """
    Route a tool call from the LLM to the correct Python function.
    Returns the tool's string output.
    """
    if tool_name == "web_search":
        return web_search(
            query=tool_args["query"],
            max_results=tool_args.get("max_results", 5),
        )
    elif tool_name == "write_file":
        return write_file(
            filename=tool_args["filename"],
            content=tool_args["content"],
            mode=tool_args.get("mode", "overwrite"),
        )
    else:
        return f"[Unknown tool: {tool_name!r}]"
