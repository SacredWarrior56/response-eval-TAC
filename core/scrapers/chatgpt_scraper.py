# ChatGPT scraper (Async & Concurrent)
import os
import json
import time
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI
from datetime import datetime

# Load environment variables
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
ENV_PATH = os.path.join(PROJECT_ROOT, '.env')
load_dotenv(ENV_PATH)

OPENAI_API_KEY = os.getenv("OPENAI_KEY")

# Configuration
MODEL = "gpt-4o-mini"
MAX_TOKENS = 500

# Default queries
QUERIES = ["What are the best SUVs?", "Show me sedans with best mileage"]

async def submit_query_async(client, query, query_id=None, total=None):
    """Submit a query to ChatGPT API asynchronously."""
    if not OPENAI_API_KEY:
        return {'query': query, 'response': None, 'status': 'failed', 'error': 'OPENAI_API_KEY missing'}
    
    start_time = datetime.now()
    max_retries = 3
    base_delay = 2
    
    for attempt in range(max_retries):
        try:
            response = await client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": query}],
                max_tokens=MAX_TOKENS
            )
            
            usage = response.usage
            result = {
                'query': query,
                'response': response.choices[0].message.content,
                'status': 'success',
                'model': response.model,
                'tokens_used': usage.total_tokens,
                'response_length_chars': len(response.choices[0].message.content),
                'response_word_count': len(response.choices[0].message.content.split()),
                'processing_time_seconds': (datetime.now() - start_time).total_seconds(),
                'timestamp': start_time.isoformat()
            }
            
            if query_id and total:
                print(f"✓ ChatGPT: Query {query_id}/{total} finished in {result['processing_time_seconds']:.2f}s")
            return result

        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait = base_delay * (2 ** attempt)
                print(f"⚠️ ChatGPT Rate Limit. Retry in {wait}s...")
                await asyncio.sleep(wait)
            else:
                return {
                    'query': query, 'response': None, 'status': 'failed', 
                    'error': str(e), 'timestamp': datetime.now().isoformat()
                }

async def chatgpt_query_processor_async(queries=None, on_result=None):
    """Process queries concurrently."""
    if not queries: queries = QUERIES
    
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    # Limit concurrency to 5 to be safe with OpenAI rate limits
    sem = asyncio.Semaphore(5)
    
    async def worker(idx, q):
        async with sem:
            res = await submit_query_async(client, q, idx, len(queries))
            # Callback
            if on_result:
                try:
                    await on_result(res)
                except Exception as e:
                    print(f"Callback error: {e}")
            return res

    tasks = [worker(i+1, q) for i, q in enumerate(queries)]
    results = await asyncio.gather(*tasks)
    return results

def main():
    """Sync entry point for testing."""
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY not set")
        return
    asyncio.run(chatgpt_query_processor_async())

if __name__ == "__main__":
    main()
