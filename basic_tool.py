"""
basic_tool.py — Week 2, Task 1
A Groq tool-calling agent that fetches live cryptocurrency prices from the
CoinGecko free API and answers the user's question in plain language.

Flow:
  1. User asks a question about crypto.
  2. Groq decides to call get_crypto_price().
  3. Tool executes against CoinGecko.
  4. Result is returned to Groq.
  5. Groq produces a natural-language final answer.
"""

import os
import json
import requests
from dotenv import load_dotenv
from groq import Groq

# Load environment variables from .env file
load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise EnvironmentError("GROQ_API_KEY not found. Please set it in your .env file.")

client = Groq(api_key=api_key)
MODEL = "llama-3.3-70b-versatile"

# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------

def get_crypto_price(coin_id: str) -> str:
    """
    Fetch the current USD price and 24-hour change for a cryptocurrency.

    Args:
        coin_id: The CoinGecko coin identifier (e.g. 'bitcoin', 'ethereum').

    Returns:
        A human-readable string with the price and 24h change percentage,
        or an error message if the request fails.
    """
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if coin_id not in data:
            return f"Coin '{coin_id}' not found on CoinGecko. Try a valid id like 'bitcoin' or 'ethereum'."
        price = data[coin_id]["usd"]
        change = data[coin_id].get("usd_24h_change", 0)
        return (
            f"{coin_id.capitalize()} is currently ${price:,.2f} USD "
            f"(24h change: {change:+.2f}%)."
        )
    except requests.RequestException as exc:
        return f"Network error fetching crypto price: {exc}"


# ---------------------------------------------------------------------------
# Tool schema (Groq-compatible JSON schema)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_crypto_price",
            "description": (
                "Fetch the live USD price and 24-hour percentage change for a "
                "cryptocurrency. Use this whenever the user asks about the current "
                "price or recent performance of any crypto coin."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "coin_id": {
                        "type": "string",
                        "description": (
                            "The CoinGecko identifier for the coin, e.g. 'bitcoin', "
                            "'ethereum', 'dogecoin', 'solana'."
                        ),
                    }
                },
                "required": ["coin_id"],
            },
        },
    }
]

# Map tool names to their Python implementations
AVAILABLE_TOOLS = {"get_crypto_price": get_crypto_price}


def run_agent(user_question: str) -> str:
    """
    Run a single-turn tool-calling agent loop.

    Args:
        user_question: The user's natural-language question.

    Returns:
        The model's final answer as a string.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful crypto assistant. When the user asks about "
                "cryptocurrency prices or performance, use the get_crypto_price tool."
            ),
        },
        {"role": "user", "content": user_question},
    ]

    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        # If no tool was called, the model has produced its final answer
        if not msg.tool_calls:
            return msg.content

        # Append the assistant's message (with tool_calls) to the conversation
        messages.append(msg)

        # Execute each requested tool and append results
        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)
            print(f"[Tool call] {fn_name}({fn_args})")

            if fn_name in AVAILABLE_TOOLS:
                result = AVAILABLE_TOOLS[fn_name](**fn_args)
            else:
                result = f"Error: unknown tool '{fn_name}'"

            print(f"[Tool result] {result}")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fn_name,
                    "content": result,
                }
            )


def main():
    question = "What is the current price of Bitcoin and how has it changed in the last 24 hours?"
    print(f"User: {question}\n")
    answer = run_agent(question)
    print(f"Agent: {answer}")


if __name__ == "__main__":
    main()
