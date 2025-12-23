# ChatGPT scraper (API based)
import os
import json
import time
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime

# Load environment variables
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
ENV_PATH = os.path.join(PROJECT_ROOT, '.env')
load_dotenv(ENV_PATH)

OPENAI_API_KEY = os.getenv("OPENAI_KEY")

# Configuration
MODEL = "gpt-3.5-turbo"
MAX_TOKENS = 500

# Default queries
QUERIES = ["What are the best SUVs?", "Show me sedans with best mileage"]


def submit_query(query, query_id=None, total=None):
    """Submit a query to ChatGPT API and return response with metadata."""
    if not OPENAI_API_KEY:
        return {
            'query': query,
            'response': None,
            'status': 'failed',
            'error': 'OPENAI_API_KEY not found'
        }
    
    try:
        if query_id and total:
            print(f"Processing query {query_id}/{total}: {query[:60]}...")
        
        client = OpenAI(api_key=OPENAI_API_KEY)
        start_time = datetime.now()
        
        response = client.chat.completions.create(
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
            'prompt_tokens': usage.prompt_tokens,
            'completion_tokens': usage.completion_tokens,
            'processing_time_seconds': (datetime.now() - start_time).total_seconds(),
            'timestamp': start_time.isoformat()
        }
        
        if query_id and total:
            print(f"✓ Query {query_id}/{total} completed ({usage.total_tokens} tokens)")
        
        return result
    except Exception as e:
        if query_id and total:
            print(f"✗ Query {query_id}/{total} failed: {str(e)}")
        return {
            'query': query,
            'response': None,
            'status': 'failed',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }


def chatgpt_query_processor(queries=None, delay=1):
    """Process multiple queries through ChatGPT API."""
    if not queries:
        queries = QUERIES
    
    print(f"Processing {len(queries)} queries...")
    results = []
    for idx, query in enumerate(queries, 1):
        result = submit_query(query, query_id=idx, total=len(queries))
        results.append(result)
        if idx < len(queries):
            time.sleep(delay)
    return results

def main():
    """Main entry point."""
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY not set")
        return
    
    results = chatgpt_query_processor()
    
    filename = f"chatgpt_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(SCRIPT_DIR, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(results)} results to: {filepath}")


if __name__ == "__main__":
    main()
