"""
json_extractor.py — Week 1, Task 5
Uses Groq to parse unstructured text into a strict JSON schema,
then extracts and prints just the skills list.
"""

import os
import json
from dotenv import load_dotenv
from groq import Groq

# Load environment variables from .env file
load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise EnvironmentError("GROQ_API_KEY not found. Please set it in your .env file.")

client = Groq(api_key=api_key)
MODEL = "llama-3.3-70b-versatile"

# Source text to parse — copied verbatim from the task specification
RAW_TEXT = (
    "We interviewed Alex Mercer today. He is 24 years old and works as a "
    "Junior Data Analyst. His technical toolkit consists of Python, SQL, and Tableau."
)

# System prompt that forces the model to output ONLY raw JSON with no extras
SYSTEM_INSTRUCTION = (
    "You are a strict data-extraction engine. "
    "Your sole job is to parse the user's text and return a single JSON object. "
    "Do NOT include markdown code fences, explanations, or any text outside the JSON. "
    "Output ONLY a raw JSON object that exactly matches this schema:\n"
    '{"name": "", "age": 0, "role": "", "skills": []}'
)


def main():
    """Extract structured data from unstructured text and print the skills list."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": RAW_TEXT},
        ],
    )

    raw_output = response.choices[0].message.content.strip()

    # Attempt to parse the model's output as JSON
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as e:
        print(f"JSONDecodeError — the model returned non-JSON output: {e}")
        print(f"Raw output was:\n{raw_output}")
        return

    # Extract and print just the skills list
    skills = parsed.get("skills", [])
    print(skills)


if __name__ == "__main__":
    main()
