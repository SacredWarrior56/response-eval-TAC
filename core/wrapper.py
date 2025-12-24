import asyncio
import os
from core.scrapers.cartrade_scraper import cartrade_chatbot_scraper
from core.scrapers.chatgpt_scraper import chatgpt_query_processor
from core.scrapers.vyas_scraper import vyas_chatbot_scraper

class ScraperWrapper:
    """
    Wrapper class to unify the interface for different scrapers.
    """
    def __init__(self):
        pass

    async def _run_with_timing(self, correlator, queries, name):
        """Helper to run a scraper with timing."""
        start_time = asyncio.get_event_loop().time()
        try:
            results = await correlator(queries)
            duration = asyncio.get_event_loop().time() - start_time
            return {
                "data": results,
                "duration": duration,
                "status": "success"
            }
        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            print(f"{name} scraper failed: {e}")
            return {
                "data": None,
                "error": str(e),
                "duration": duration,
                "status": "error"
            }

    async def _run_parallel_scraper(self, scraper_func, queries, name, on_result=None):
        """Run a scraper instance in parallel using a semaphore and chunks."""
        api_key = os.getenv("HYPERBROWSER_API_KEY")
        if not api_key:
             return {"error": "HYPERBROWSER_API_KEY not found", "status": "error", "duration": 0, "data": None}

        print(f"Running {name} with optimized concurrency (up to 25 sessions)...")
        
        # Determine strict concurrency limit
        CONCURRENCY_LIMIT = 25 # Back to max
        
        # Split queries into N chunks where N is min(len, LIMIT)
        # It is better to have more tasks with fewer items if possible to utilize all 25 slots
        num_tasks = min(len(queries), CONCURRENCY_LIMIT)
        if num_tasks < 1: num_tasks = 1
        
        # Create Chunks
        chunk_size = (len(queries) + num_tasks - 1) // num_tasks
        chunks = [queries[i:i + chunk_size] for i in range(0, len(queries), chunk_size)]
        
        print(f"Splitting {len(queries)} queries into {len(chunks)} parallel tasks for {name}...")
        
        start_time = asyncio.get_event_loop().time()
        
        
        tasks = []
        
        # Create a semaphore to ensure we don't strictly exceed concurrent session limits if this method is called multiple times
        # effectively, though, hyperbrowser handles limits, but client-side throttling is good practice.
        sem = asyncio.Semaphore(CONCURRENCY_LIMIT)

        async def run_chunk_with_retry(chunk, idx, start_delay=0):
            # Stagger start to avoid hitting API rate limits instantly
            if start_delay > 0:
                await asyncio.sleep(start_delay)
                
            async with sem:
                retries = 5 # Increased retries
                base_delay = 2
                last_error = None
                
                import random
                for attempt in range(retries):
                    try:
                        return await scraper_func(chunk, api_key=api_key, on_result=on_result)
                    except Exception as e:
                        error_str = str(e)
                        # Check for 503 or 429 errors
                        if "503" in error_str or "Service Unavailable" in error_str or "429" in error_str or "Too Many Requests" in error_str:
                            last_error = e
                            # Add jitter to prevent thundering herd where all retry at exact same time
                            base_wait = base_delay * (2 ** attempt)
                            wait_time = base_wait + random.uniform(1, 4)
                            print(f"⚠️ Task {idx} failed with {error_str[:50]}... Retrying in {wait_time:.2f}s ({attempt+1}/{retries})...")
                            await asyncio.sleep(wait_time)
                        else:
                            # Re-raise other errors immediately or return info
                            raise e
                
                # If we exhausted retries
                print(f"❌ Task {idx} failed after {retries} retries: {last_error}")
                # Return a list of failed results specifically for this chunk so we don't crash everything
                return [{
                    'query': q,
                    'response': None,
                    'status': "failed_max_retries",
                    'error': str(last_error),
                    'timestamp': asyncio.get_event_loop().time()
                } for q in chunk]

        for i, chunk in enumerate(chunks):
            # Stagger by 0.1 seconds per task
            delay = i * 0.1
            tasks.append(run_chunk_with_retry(chunk, i, start_delay=delay))
        
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        duration = asyncio.get_event_loop().time() - start_time
        
        # Merge results
        merged_data = []
        errors = []
        
        for res in results_list:
            if isinstance(res, Exception):
                errors.append(str(res))
            elif isinstance(res, list):
                merged_data.extend(res)
                
        status = "success" if not errors else ("partial_error" if merged_data else "error")
        error_msg = "; ".join(errors) if errors else None
        
        return {
            "data": merged_data,
            "duration": duration,
            "status": status,
            "error": error_msg
        }

    async def run_cartrade(self, queries, on_result=None):
        """Run the CarTrade scraper using parallel sessions."""
        return await self._run_parallel_scraper(cartrade_chatbot_scraper, queries, "CarTrade", on_result)

    async def run_vyas(self, queries, on_result=None):
        """Run the Vyas scraper using parallel sessions."""
        return await self._run_parallel_scraper(vyas_chatbot_scraper, queries, "Vyas", on_result)

    async def run_chatgpt(self, queries, on_result=None):
        """Run the ChatGPT scraper."""
        loop = asyncio.get_running_loop()

        def sync_on_result(res):
            if on_result:
                loop.call_soon_threadsafe(lambda: asyncio.create_task(on_result(res)))

        async def wrapped_chatgpt(q):
            return await asyncio.to_thread(chatgpt_query_processor, q, delay=0.5, on_result=sync_on_result)
            
        return await self._run_with_timing(wrapped_chatgpt, queries, "ChatGPT")

    async def run_all(self, queries, on_result=None):
        """
        Run all scrapers concurrently.
        """
        print(f"Starting all scrapers concurrent execution with {len(queries)} queries...")
        start_time = asyncio.get_event_loop().time()
        
        # Helper callbacks
        def create_callback(source):
            if not on_result: return None
            async def wrapped_cb(res):
                if isinstance(res, dict): res['source'] = source
                await on_result(res)
            return wrapped_cb
        
        # Launch everything sequentially as per user request to avoid concurrency limits
        print("Executing Vyas first...")
        vyas_res = await self.run_vyas(queries, on_result=create_callback('vyas'))
        
        print("Executing CarTrade second...")
        cartrade_res = await self.run_cartrade(queries, on_result=create_callback('cartrade'))
        
        print("Executing ChatGPT third...")
        chatgpt_res = await self.run_chatgpt(queries, on_result=create_callback('chatgpt'))
        
        results_list = [chatgpt_res, cartrade_res, vyas_res]
        
        total_duration = asyncio.get_event_loop().time() - start_time
        chatgpt_res, cartrade_res, vyas_res = results_list
        
        final_results = {}
        for name, res in zip(['chatgpt', 'cartrade', 'vyas'], [chatgpt_res, cartrade_res, vyas_res]):
            if isinstance(res, Exception):
                 final_results[name] = {"data": None, "error": str(res), "duration": 0, "status": "system_error"}
            else:
                final_results[name] = res
        
        final_results['total_duration'] = total_duration
        return final_results



# Example usage for testing
if __name__ == "__main__":
    async def test_wrapper():
        wrapper = ScraperWrapper()
        test_queries = ["What is the mileage of Maruti Swift?"]
        results = await wrapper.run_all(test_queries)
        print("Results:", results.keys())
        
    asyncio.run(test_wrapper())
