"""
basic_call.py — Week 1, Task 2
Makes a simple LLM call to Groq and prints the response.
"""

import os
from dotenv import load_dotenv
from groq import Groq

# Load environment variables from .env file
load_dotenv()

# Retrieve the API key securely from the environment
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise EnvironmentError("GROQ_API_KEY not found. Please set it in your .env file.")

# Initialise the Groq client
client = Groq(api_key=api_key)

# Model to use across all scripts
MODEL = "llama-3.3-70b-versatile"

def main():
    """Send a simple prompt to the Groq API and print the response."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": "Explain Newton's Second Law in one sentence.",
            }
        ],
    )

    # Extract and print the text response
    answer = response.choices[0].message.content
    print(answer)


if __name__ == "__main__":
    main()
