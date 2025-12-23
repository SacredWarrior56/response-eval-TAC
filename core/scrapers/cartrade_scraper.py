#scraper for cartrade.com
import os
import asyncio
from dotenv import load_dotenv
from hyperbrowser import AsyncHyperbrowser
from hyperbrowser.models import CreateSessionParams
from playwright.async_api import async_playwright
from datetime import datetime
import json

# Load environment variables
# Get project root (2 levels up from this file)
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
CARTRADE_URL = "https://www.cartrade.com"

# Selectors
CHATBOT_CONTAINER_SELECTOR = "div.js-ai-chatbot-cta.ai-chatbot-desktop-container"
INPUT_FIELD_SELECTOR = "#ai-search-input"
RESPONSE_CONTAINER_SELECTOR = "div.p1MF55"

# Session configuration
session_config = CreateSessionParams(
    use_stealth=True,
    use_proxy=False,
    solve_captchas=False
)

QUERIES = ["What are the best SUVs?", "Show me sedans with best mileage"]


async def wait_for_response_completion(page, max_wait_time=60, response_index=-1):
    """Wait for chatbot response by polling until text stabilizes."""
    
    await asyncio.sleep(10)
    
    await page.wait_for_selector(RESPONSE_CONTAINER_SELECTOR, timeout=15000)
    
    stability_duration = 3.0
    check_interval = 1.5
    
    start_time = asyncio.get_event_loop().time()
    last_text = ""
    last_change_time = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start_time) < max_wait_time:
        current_text = await page.evaluate(f'''
            (index) => {{
                const divs = document.querySelectorAll("{RESPONSE_CONTAINER_SELECTOR}");
                if (divs.length === 0) return "";
                
                let targetDiv;
                if (index === -1) {{
                    targetDiv = divs[divs.length - 1];  // Last div
                }} else {{
                    targetDiv = divs[index];  // Specific index
                }}
                
                return targetDiv ? targetDiv.innerText.trim() : "";
            }}
        ''', response_index)
        
        if current_text != last_text:
            last_text = current_text
            last_change_time = asyncio.get_event_loop().time()
        else:
            time_stable = asyncio.get_event_loop().time() - last_change_time
            if time_stable >= stability_duration:
                return True
        
        await asyncio.sleep(check_interval)
    
    return False


async def extract_response(page, response_index=-1):
    """Extract the chatbot response text from the response div."""
    response = await page.evaluate(f'''
        (index) => {{
            const divs = document.querySelectorAll("{RESPONSE_CONTAINER_SELECTOR}");
            if (divs.length === 0) return "";
            
            let targetDiv;
            if (index === -1) {{
                targetDiv = divs[divs.length - 1];  // Last div
            }} else {{
                targetDiv = divs[index];  // Specific index
            }}
            
            return targetDiv ? targetDiv.innerText.trim() : "";
        }}
    ''', response_index)
    return response


async def submit_query(page, query, query_id, total_queries):
    """Submit a single query to the chatbot."""
    print(f"Clicking input field for query {query_id}/{total_queries}")

    existing_count = await page.evaluate(f'''
        () => {{
            return document.querySelectorAll("{RESPONSE_CONTAINER_SELECTOR}").length;
        }}
    ''')

    print(f"  Existing responses before query: {existing_count}")
    await page.click(INPUT_FIELD_SELECTOR)
    await asyncio.sleep(1)

    await page.type(INPUT_FIELD_SELECTOR, query)
    await asyncio.sleep(1)

    print(f"Submitting query {query_id}/{total_queries}")
    await page.keyboard.press("Enter")

    print(f"  Waiting for new response to appear...")
    max_wait = 15
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < max_wait:
        current_count = await page.evaluate(f'''
            () => {{
                return document.querySelectorAll("{RESPONSE_CONTAINER_SELECTOR}").length;
            }}
        ''')
        
        if current_count > existing_count:
            print(f"  ✓ New response appeared! (count: {existing_count} → {current_count})")
            break
        
        await asyncio.sleep(0.5)

    response_complete = await wait_for_response_completion(page)

    if not response_complete:
        print(f"Response not completed in time")
        return {
            'query': query,
            'response': None,
            'status': "timeout",
            'timestamp': datetime.now().isoformat()
        }
    
    print("Extracting response...")
    response = await extract_response(page)

    preview = response[:100] if len(response) > 100 else response
    print(f"Response {query_id}/{total_queries}: {preview}")

    return {
        'query': query,
        'response': response,
        'status': "success",
        'timestamp': datetime.now().isoformat() 
    }


async def cartrade_chatbot_scraper(queries=None):
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

            # Navigate to CarTrade
            print("Navigating to CarTrade...")
            await page.goto(CARTRADE_URL)
            await asyncio.sleep(2)

            # Open chatbot
            print("Opening chatbot...")
            await page.wait_for_selector(CHATBOT_CONTAINER_SELECTOR, timeout=10000)
            await page.click(CHATBOT_CONTAINER_SELECTOR)
            await asyncio.sleep(2)
            print("Chatbot opened!")

            # Process queries
            for query_id, query in enumerate(queries, 1):
                result = await submit_query(page, query, query_id, len(queries))
                results.append(result)

                if query_id < len(queries):
                    print(f"Waiting 3 seconds before next query...")
                    await asyncio.sleep(3)
            
            await browser.close()

    except Exception as e:
        print(f"Error in scraper: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if session:
            print("Stopping session...")
            await client.sessions.stop(session.id)
            print("Session closed")

    return results


def check_setup():
    """Check if setup is valid."""
    print("🔍 Checking setup...\n")
    
    # Check for .env file in project root (where we actually load it from)
    if not os.path.exists(ENV_PATH):
        # Fallback: check current directory
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
        print(f"   .env file exists: {os.path.exists(ENV_PATH) or os.path.exists('.env')}")
        return False
    
    print("✅ Setup looks good!\n")
    return True


async def main():
    """Main entry point."""
    if not check_setup():
        return
    
    results = await cartrade_chatbot_scraper()
    
    # Save results
    filename = f"cartrade_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Saved results to: {filename}")


if __name__ == "__main__":
    asyncio.run(main())