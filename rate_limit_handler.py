"""
rate_limit_handler.py — Week 1, Task 3
Simulates 15 rapid API calls with exponential-backoff retry logic so the
script never crashes even if the rate limit is hit.
"""

import os
import time
from dotenv import load_dotenv
from groq import Groq, RateLimitError

# Load environment variables from .env file
load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise EnvironmentError("GROQ_API_KEY not found. Please set it in your .env file.")

client = Groq(api_key=api_key)
MODEL = "llama-3.3-70b-versatile"

# Number of simulated rapid API calls
TOTAL_REQUESTS = 15

# Backoff settings
INITIAL_BACKOFF_SECONDS = 5
MAX_BACKOFF_SECONDS = 60


def make_request(request_number: int) -> str:
    """
    Make a single LLM API call.

    Args:
        request_number: The 1-based index of this request (for logging).

    Returns:
        The text response from the model.
    """
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": "Say 'OK' and nothing else.",
            }
        ],
        max_tokens=5,
    )
    return response.choices[0].message.content.strip()


def main():
    """Attempt 15 API calls, gracefully handling rate-limit errors."""
    for i in range(1, TOTAL_REQUESTS + 1):
        backoff = INITIAL_BACKOFF_SECONDS
        while True:
            try:
                result = make_request(i)
                print(f"Request {i} successful: {result}")
                break  # Move to the next request on success
            except RateLimitError:
                print(f"Rate limit hit on request {i}, retrying in {backoff}s...")
                time.sleep(backoff)
                # Exponential backoff, capped at MAX_BACKOFF_SECONDS
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            except Exception as exc:
                # Catch-all for network errors, server errors, etc.
                print(f"Request {i} failed with unexpected error: {exc}. Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


if __name__ == "__main__":
    main()
