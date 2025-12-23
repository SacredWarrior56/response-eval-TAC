# Scraper for vyas-poc.cwsystem.in
import os
import asyncio
from dotenv import load_dotenv
from hyperbrowser import AsyncHyperbrowser
from hyperbrowser.models import CreateSessionParams
from playwright.async_api import async_playwright
from datetime import datetime
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
    print("Attempting to load from current directory...")
    try:
        load_dotenv()
    except Exception as e2:
        print(f"❌ Failed to load .env file: {e2}")

HYPERBROWSER_API_KEY = os.getenv("HYPERBROWSER_API_KEY")
VYAS_URL = "https://vyas-poc.cwsystem.in/"
VYAS_USERNAME = os.getenv("VYAS_USERNAME")
VYAS_PASSWORD = os.getenv("VYAS_PASSWORD")

# Selectors
USERNAME_SELECTOR = '[aria-label="Username"]'
PASSWORD_SELECTOR = '[aria-label="Password"]'
SUBMIT_BUTTON_SELECTOR = '[data-testid="stBaseButton-secondaryFormSubmit"]'
INPUT_AREA_SELECTOR = '[data-testid="stChatInputTextArea"]'
CLEAR_MEMORY_SELECTOR = "button:has-text('Clear Memory')"
RESPONSE_DIV_SELECTOR = '[data-testid="stChatMessageContent"]'

# Session configuration
session_config = CreateSessionParams(
    use_stealth=True,
    use_proxy=False,
    solve_captchas=False
)

QUERIES = ["maruti vs audi"]


async def wait_for_response_completion(page, max_wait_time=120):
    """Wait for chatbot response by checking Stop button appearance/disappearance."""
    stop_button_selector = "button:has-text('Stop')"
    
    # Wait for Stop button to appear (response is generating)
    try:
        await page.wait_for_selector(stop_button_selector, timeout=20000)
    except Exception:
        # Stop button might not appear if response is very fast
        await asyncio.sleep(2)  # Small delay to ensure response is rendered
        return True
    
    # Wait for Stop button to disappear (response is complete)
    start_time = asyncio.get_event_loop().time()
    check_interval = 0.5
    
    while (asyncio.get_event_loop().time() - start_time) < max_wait_time:
        try:
            stop_button = await page.query_selector(stop_button_selector)
            if not stop_button:
                # Stop button disappeared, wait a bit more for response to fully render
                await asyncio.sleep(2)
                return True
        except Exception:
            pass
        
        await asyncio.sleep(check_interval)
    
    return False  # Timeout


async def extract_response(page):
    """Extract the chatbot response text from the response div."""
    response = await page.evaluate('''
        (selector) => {
            const divs = document.querySelectorAll(selector);
            if (divs.length === 0) return "";
            const lastDiv = divs[divs.length - 1];
            return lastDiv ? lastDiv.innerText.trim() : "";
        }
    ''', RESPONSE_DIV_SELECTOR)
    return response


async def clear_memory(page):
    """Click the clear memory button."""
    try:
        await page.click(CLEAR_MEMORY_SELECTOR)
        await asyncio.sleep(1)
    except Exception as e:
        print(f"Warning: Could not clear memory: {e}")


async def submit_query(page, query, query_id, total_queries):
    """Submit a single query to the chatbot."""
    try:
        print(f"Processing query {query_id}/{total_queries}: {query[:60]}...")
        
        # Clear memory before query
        await clear_memory(page)
        
        # Click input area
        await page.click(INPUT_AREA_SELECTOR)
        await asyncio.sleep(1)
        
        # Type query
        await page.type(INPUT_AREA_SELECTOR, query)
        await asyncio.sleep(1)
        
        # Submit query
        await page.keyboard.press("Enter")
        
        # Wait for response completion
        response_complete = await wait_for_response_completion(page)
        
        if not response_complete:
            print(f"Response not completed in time")
            return {
                'query': query,
                'response': None,
                'status': "timeout",
                'timestamp': datetime.now().isoformat()
            }
        
        # Extract response
        response = await extract_response(page)
        
        preview = response[:100] if len(response) > 100 else response
        print(f"✓ Query {query_id}/{total_queries} completed: {preview}...")
        
        return {
            'query': query,
            'response': response,
            'status': "success",
            'timestamp': datetime.now().isoformat() 
        }
    
    except Exception as e:
        print(f"Error in submit_query: {e}")
        return {
            'query': query,
            'response': None,
            'status': "error",
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }


async def vyas_chatbot_scraper(queries=None):
    """Main scraper function using Hyperbrowser + Playwright."""
    if queries is None:
        queries = QUERIES
    
    print("Initializing AsyncHyperbrowser...")
    client = AsyncHyperbrowser(api_key=HYPERBROWSER_API_KEY)
    
    session = None
    results = []
    
    try:
        # Create Hyperbrowser session
        print("Creating session...")
        session = await client.sessions.create(params=session_config)
        
        print(f"Session ID: {session.id}")
        print(f"WebSocket Endpoint: {session.ws_endpoint}")
        
        # Connect Playwright to Hyperbrowser session
        print("Connecting Playwright...")
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(session.ws_endpoint)
            
            # Get the default context and create a page
            context = browser.contexts[0]
            page = await context.new_page()
            
            # Navigate to Vyas
            print("Navigating to Vyas...")
            await page.goto(VYAS_URL)
            await asyncio.sleep(2)
            
            # Login
            print("Logging in...")
            await page.fill(USERNAME_SELECTOR, VYAS_USERNAME)
            await page.fill(PASSWORD_SELECTOR, VYAS_PASSWORD)
            await page.click(SUBMIT_BUTTON_SELECTOR)
            await asyncio.sleep(3)
            print("Logged in!")
            
            # Clear memory initially
            await clear_memory(page)
            
            # Process queries
            for query_id, query in enumerate(queries, 1):
                result = await submit_query(page, query, query_id, len(queries))
                results.append(result)
                
                # Clear memory after each query (except last one)
                if query_id < len(queries):
                    await clear_memory(page)
                    await asyncio.sleep(1)
            
            await browser.close()
    
    except Exception as e:
        print(f"Error in scraper: {e}")
        import traceback
        traceback.print_exc()
        if not results and queries:
            for query_id, query in enumerate(queries, 1):
                results.append({
                    'query': query,
                    'response': None,
                    'status': "failed",
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
        
    finally:
        if session:
            print("Stopping session...")
            await client.sessions.stop(session.id)
            print("Session closed")
    
    return results


def check_setup():
    """Check if setup is valid."""
    print("🔍 Checking setup...\n")
    
    if not os.path.exists(ENV_PATH):
        if not os.path.exists('.env'):
            print(f"❌ .env file not found!")
            print(f"   Checked: {ENV_PATH}")
            print(f"   Also checked: {os.path.abspath('.env')}")
            return False
        else:
            print(f"⚠️ Warning: Found .env in current directory, but expected at: {ENV_PATH}")
    else:
        print(f"✅ Found .env file at: {ENV_PATH}")
    
    if not HYPERBROWSER_API_KEY or HYPERBROWSER_API_KEY == 'your_key_here':
        print("❌ HYPERBROWSER_API_KEY not set!")
        return False
    
    if not VYAS_USERNAME or not VYAS_PASSWORD:
        print("❌ VYAS_USERNAME or VYAS_PASSWORD not set!")
        return False
    
    print("✅ Setup looks good!\n")
    return True


async def main():
    """Main entry point."""
    if not check_setup():
        return
    
    results = await vyas_chatbot_scraper()
    
    # Save results
    filename = f"vyas_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Saved results to: {filename}")


if __name__ == "__main__":
    asyncio.run(main())
