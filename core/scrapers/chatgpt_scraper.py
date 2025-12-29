# UI Scraper for chatgpt.com (Hyperbrowser + Playwright)
import os
import asyncio
from dotenv import load_dotenv
from hyperbrowser import AsyncHyperbrowser
from hyperbrowser.models import CreateSessionParams
from playwright.async_api import async_playwright
from datetime import datetime
import time
import json

# Load environment variables
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
ENV_PATH = os.path.join(PROJECT_ROOT, '.env')

try:
    load_dotenv(ENV_PATH)
    print(f"✅ Loaded .env file from: {ENV_PATH}")
except Exception as e:
    print(f"⚠️ Warning: Could not load .env file from {ENV_PATH}: {e}")
    try:
        load_dotenv()
    except Exception as e2:
        print(f"❌ Failed to load .env file: {e2}")

HYPERBROWSER_API_KEY = os.getenv("HYPERBROWSER_API_KEY")
CHATGPT_URL = "https://chatgpt.com"

# Selectors
INPUT_SELECTOR = "#prompt-textarea"
SEND_BUTTON_SELECTOR = '[data-testid="send-button"]'
# When generating, the send button usually changes to a stop button or disappears
STOP_BUTTON_SELECTOR = '[data-testid="stop-button"]' 
RESPONSE_SELECTOR = '.markdown' # Common class for message content

# Session configuration
session_config = CreateSessionParams(
    use_stealth=True,
    use_proxy=False,
    solve_captchas=True  # ChatGPT often requires captcha solving
)

QUERIES = [
    "What are the best SUVs?", 
    "Show me sedans with best mileage"
]

async def wait_for_response_completion(page, max_wait_time=120):
    """Wait for chatbot response by watching for the 'Send' button to reappear."""
    
    # 1. Wait for the 'Stop' button to appear (indicating generation started)
    #    OR wait for the Send button to disappear.
    try:
        # Give it a moment to switch states
        await asyncio.sleep(2)
        # If the send button is still there, maybe it was instant or failed?
        # We'll assume generation starts if we see stop button OR input is disabled/send missing
    except Exception:
        pass

    # 2. Polling loop: Wait until 'Send' button is visible and enabled again
    start_time = time.time()
    while (time.time() - start_time) < max_wait_time:
        is_send_visible = await page.is_visible(SEND_BUTTON_SELECTOR)
        if is_send_visible:
            # extra safety buffer for rendering
            await asyncio.sleep(2) 
            return True
        await asyncio.sleep(1)
    
    return False

async def extract_last_response(page):
    """Extract the text of the latest response."""
    # We get all markdown divs and take the last one.
    # Note: This assumes the conversation view. User prompts are also sometimes distinct.
    # A more robust selector usually involves data-message-author-role="assistant"
    return await page.evaluate('''
        () => {
            const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
            if (msgs.length === 0) return "";
            const lastMsg = msgs[msgs.length - 1];
            return lastMsg.innerText.trim();
        }
    ''')

async def submit_query(page, query, query_id, total_queries):
    """Submit a single query to the chatbot."""
    try:
        print(f"Processing query {query_id}/{total_queries}: {query[:60]}...")
        
        # Check if input is available
        await page.wait_for_selector(INPUT_SELECTOR, timeout=30000)
        
        # Click and fill
        await page.click(INPUT_SELECTOR)
        await asyncio.sleep(0.5)
        # Clear existing text if any (sanity check)
        await page.fill(INPUT_SELECTOR, "")
        await page.fill(INPUT_SELECTOR, query)
        await asyncio.sleep(1)
        
        # Send
        start_time = time.time()
        # Prefer clicking the button if available, or Enter
        if await page.is_visible(SEND_BUTTON_SELECTOR):
            await page.click(SEND_BUTTON_SELECTOR)
        else:
            await page.keyboard.press("Enter")
            
        # Wait for response
        completed = await wait_for_response_completion(page, max_wait_time=120)
        response_duration = time.time() - start_time
        
        if not completed:
            print(f"  ⚠️ Timeout waiting for response completion (Query {query_id})")
        
        # Extract
        response_text = await extract_last_response(page)
        
        # Validate extraction
        if not response_text:
            print("  ❌ Failed to extract response text.")
        else:
            preview = response_text[:100].replace('\n', ' ')
            print(f"  ✓ Response captured: {preview}...")

        return {
            'query': query,
            'response': response_text,
            'status': "success" if response_text else "failed",
            'response_time_seconds': response_duration,
            'response_length_chars': len(response_text) if response_text else 0,
            'response_word_count': len(response_text.split()) if response_text else 0,
            'timestamp': datetime.now().isoformat() 
        }

    except Exception as e:
        print(f"Error in submit_query {query_id}: {e}")
        return {
            'query': query,
            'response': None,
            'status': "error",
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

async def chatgpt_chatbot_scraper(queries=None, api_key=None, on_result=None):
    """Main scraper function using Hyperbrowser + Playwright."""
    if queries is None:
        queries = QUERIES
    
    target_api_key = api_key or HYPERBROWSER_API_KEY
    if not target_api_key:
        raise ValueError("No Hyperbrowser API key provided and HYPERBROWSER_API_KEY not set")

    print(f"Initializing AsyncHyperbrowser...")
    client = AsyncHyperbrowser(api_key=target_api_key)
    session = None
    results = []

    try:
        print("Creating Hyperbrowser session...")
        session = await client.sessions.create(params=session_config)
        print(f"Session ID: {session.id}")
        
        print("Connecting Playwright...")
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(session.ws_endpoint)
            context = browser.contexts[0]
            page = await context.new_page()
            
            print(f"Navigating to {CHATGPT_URL}...")
            await page.goto(CHATGPT_URL)
            
            # NOTE: ChatGPT might redirect to login. 
            # Dealing with login (SSO/Email) is complex and requires credentials.
            # This scraper assumes the session is either guest-allowed or stealth enough 
            # to get the free interface immediately.
            
            # Initial wait for interface to load
            try:
                await page.wait_for_selector(INPUT_SELECTOR, timeout=30000)
                print("ChatGPT interface loaded.")
            except Exception:
                print("⚠️ Could not find input selector immediately. Check if login is required.")
                # Snapshot for debugging could be useful here
            
            # Process Queries
            for query_id, query in enumerate(queries, 1):
                result = await submit_query(page, query, query_id, len(queries))
                results.append(result)
                
                if on_result:
                    await on_result(result)
                    
                if query_id < len(queries):
                    await asyncio.sleep(3)
            
            await browser.close()

    except Exception as e:
        print(f"Error in scraper: {e}")
        # Re-raise rate limits/critical errors
        if "429" in str(e) or "503" in str(e):
            raise e
        
        # Fill failed results for remaining queries
        if not results and queries:
            for q in queries:
                results.append({'query': q, 'status': 'failed', 'error': str(e)})

    finally:
        if session:
            print("Stopping session...")
            await client.sessions.stop(session.id)
            print("Session closed")

    return results

def check_setup():
    """Check if setup is valid."""
    print("🔍 Checking setup...\n")
    if not os.path.exists(ENV_PATH) and not os.path.exists('.env'):
        print(f"❌ .env file not found!")
        return False
    
    if not HYPERBROWSER_API_KEY:
        print("❌ HYPERBROWSER_API_KEY not set!")
        return False
        
    print("✅ Setup looks good!\n")
    return True

async def main():
    """Main entry point."""
    if not check_setup():
        return
    
    results = await chatgpt_chatbot_scraper()
    
    filename = f"chatgpt_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Saved results to: {filename}")

# Alias to maintain compatibility with wrapper
chatgpt_query_processor_async = chatgpt_chatbot_scraper

if __name__ == "__main__":
    asyncio.run(main())