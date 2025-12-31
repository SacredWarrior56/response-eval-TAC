import os
from dotenv import load_dotenv
from openai import OpenAI

# Load .env file
load_dotenv()

# Get API key
api_key = os.getenv("OPENAI_KEY")
if not api_key:
    raise RuntimeError("OPENAI_KEY not found in .env")

# Create client
client = OpenAI(api_key=api_key)

# Make request
response = client.responses.create(
    model="gpt-4o",
    tools=[
        {"type": "web_search"},
    ],
    input="temprature in udupi today and what scene with NYE",
)

# Print output
print(response.output_text)
