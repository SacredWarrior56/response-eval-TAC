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
        Run all scrapers with optimized batching:
        - ChatGPT runs in parallel (threaded).
        - Scrapers run in two batches: (Vyas Half + CarTrade Half) -> (Rest Vyas + Rest CarTrade)
        """
        print(f"Starting optimized execution with {len(queries)} queries...")
        start_time = asyncio.get_event_loop().time()
        
        # Helper callbacks
        def create_callback(source):
            if not on_result: return None
            async def wrapped_cb(res):
                if isinstance(res, dict): res['source'] = source
                await on_result(res)
            return wrapped_cb
        
        cb_vyas = create_callback('vyas')
        cb_cartrade = create_callback('cartrade')
        cb_chatgpt = create_callback('chatgpt')

        # Split queries
        n = len(queries)
        mid = n // 2 + (1 if n % 2 != 0 else 0) 
        batch1 = queries[:mid]
        batch2 = queries[mid:]
        
        print(f"Split queries into Batch 1 ({len(batch1)}) and Batch 2 ({len(batch2)})")

        # Task: Scraper Sequence
        async def run_scrapers_sequence():
             # Batch 1: Run Vyas and CarTrade concurrently for first half
             print(">> Running Batch 1: Vyas and CarTrade concurrently...")
             v1_task = self.run_vyas(batch1, on_result=cb_vyas)
             c1_task = self.run_cartrade(batch1, on_result=cb_cartrade)
             
             v1_res_obj, c1_res_obj = await asyncio.gather(v1_task, c1_task)
             
             v1 = v1_res_obj.get('data', [])
             c1 = c1_res_obj.get('data', [])
             
             # Cool down
             print(">> Cooling down (5s)...")
             await asyncio.sleep(5)

             # Batch 2: Run Vyas and CarTrade concurrently for second half
             print(">> Running Batch 2: Vyas and CarTrade concurrently...")
             v2_task = self.run_vyas(batch2, on_result=cb_vyas)
             c2_task = self.run_cartrade(batch2, on_result=cb_cartrade)
             
             v2_res_obj, c2_res_obj = await asyncio.gather(v2_task, c2_task)
             
             v2 = v2_res_obj.get('data', [])
             c2 = c2_res_obj.get('data', [])
             
             # Helper to merge dict results
             def build_result(data_list, duration, status):
                 return {'data': data_list, 'duration': duration, 'status': status}
            
             return (
                 build_result(v1+v2, v1_res_obj.get('duration',0)+v2_res_obj.get('duration',0), 'success'),
                 build_result(c1+c2, c1_res_obj.get('duration',0)+c2_res_obj.get('duration',0), 'success')
             )

        # Chat Task
        print(">> Launching ChatGPT in parallel...")
        task_chat = asyncio.create_task(self.run_chatgpt(queries, on_result=cb_chatgpt))
        task_scrapers = asyncio.create_task(run_scrapers_sequence())

        # Wait for both
        chatgpt_res, (vyas_res, cartrade_res) = await asyncio.gather(task_chat, task_scrapers)
        
        total_duration = asyncio.get_event_loop().time() - start_time
        
        return {
            'cartrade': cartrade_res,
            'vyas': vyas_res,
            'chatgpt': chatgpt_res,
            'total_duration': total_duration
        }



# Example usage for testing
if __name__ == "__main__":
    async def test_wrapper():
        wrapper = ScraperWrapper()
        test_queries = ["What is the mileage of Maruti Swift?"]
        results = await wrapper.run_all(test_queries)
        print("Results:", results.keys())
        
    asyncio.run(test_wrapper())
