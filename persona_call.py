"""
persona_call.py — Week 1, Task 4
Demonstrates system-instruction manipulation by giving the model a strict
Victorian-era butler persona and sending it a casual question.
"""

import os
from dotenv import load_dotenv
from groq import Groq

# Load environment variables from .env file
load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise EnvironmentError("GROQ_API_KEY not found. Please set it in your .env file.")

client = Groq(api_key=api_key)
MODEL = "llama-3.3-70b-versatile"

# System instruction that locks the model into a Victorian butler persona
SYSTEM_INSTRUCTION = (
    "You are Reginald, a formal Victorian-era butler of the highest calibre. "
    "You speak with impeccable politeness, elaborate vocabulary, and the refined "
    "manners of 19th-century English aristocracy. You never use modern slang, "
    "contractions, or casual language. Every response must be delivered as though "
    "you are addressing the lord or lady of the manor."
)


def main():
    """Send a casual prompt through a Victorian butler persona and print the response."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": "How is the weather today?"},
        ],
    )

    answer = response.choices[0].message.content
    print(answer)


if __name__ == "__main__":
    main()
