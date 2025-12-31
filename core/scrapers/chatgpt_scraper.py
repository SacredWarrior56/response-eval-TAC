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
MODEL = "gpt-5.2"  # Updated to gpt-4o for web search API

# System prompt for factual, grounded responses
SYSTEM_PROMPT = """You are a highly accurate research assistant with access to real-time web search capabilities.

Your primary objectives are:
1. FACTUAL ACCURACY: Provide only information that is directly supported by web search results
2. RELEVANCE: Focus on answering the specific query asked, staying on topic
3. GROUNDING: Base all claims on verifiable sources from the web search results
4. COMPLETENESS: Provide comprehensive answers that fully address the user's question

Guidelines:
- Always prioritize current, up-to-date information from reliable sources
- When stating facts, ensure they are directly found in the search results
- If search results are insufficient or contradictory, acknowledge this limitation
- Avoid speculation or assumptions beyond what the sources provide
- For questions about current prices, specifications, or timely information, rely heavily on recent web data
- Organize information clearly and logically
- When relevant, mention the timeframe or recency of the information
- If the search results don't contain enough information to answer fully, say so honestly

Remember: Your value comes from providing accurate, grounded information based on web search, not from generating plausible-sounding but unverified content."""

# Default queries
QUERIES = ["What are the best SUVs?", "Show me sedans with best mileage"]

async def submit_query_async(client, query, query_id=None, total=None):
    """Submit a query to ChatGPT API asynchronously using web search."""
    if not OPENAI_API_KEY:
        return {'query': query, 'response': None, 'status': 'failed', 'error': 'OPENAI_API_KEY missing'}
    
    start_time = datetime.now()
    max_retries = 3
    base_delay = 2
    
    for attempt in range(max_retries):
        try:
            # Use responses.create with web_search tool
            response = await client.responses.create(
                model=MODEL,
                instructions=SYSTEM_PROMPT,
                tools=[
                    {"type": "web_search"},
                ],
                input=query
            )
            
            # Extract the response text
            response_text = response.output_text
            
            # Extract token usage from response
            tokens_used = None
            prompt_tokens = None
            completion_tokens = None
            if hasattr(response, 'usage') and response.usage:
                tokens_used = getattr(response.usage, 'total_tokens', None)
                prompt_tokens = getattr(response.usage, 'prompt_tokens', None)
                completion_tokens = getattr(response.usage, 'completion_tokens', None)
            
            result = {
                'query': query,
                'response': response_text,
                'status': 'success',
                'model': MODEL,
                'tokens_used': tokens_used,
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'response_length_chars': len(response_text),
                'response_word_count': len(response_text.split()),
                'processing_time_seconds': (datetime.now() - start_time).total_seconds(),
                'timestamp': start_time.isoformat()
            }
            
            if query_id and total:
                print(f"✓ ChatGPT: Query {query_id}/{total} finished in {result['processing_time_seconds']:.2f}s (with web search)")
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
