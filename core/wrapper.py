import asyncio
import os
from core.scrapers.cartrade_scraper import cartrade_chatbot_scraper
from core.scrapers.chatgpt_scraper import chatgpt_query_processor_async
from core.scrapers.vyas_scraper import vyas_chatbot_scraper

class ScraperWrapper:
    """
    Wrapper class to unify the interface for different scrapers.
    """
    def __init__(self):
        # Global Semaphore to prevent hitting 25 session limit
        # We set it to 20 to be safe (leave buffer for others)
        self.global_sem = asyncio.Semaphore(20)

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
        """Run a scraper instance for a specific chunk of queries."""
        api_key = os.getenv("HYPERBROWSER_API_KEY")
        if not api_key: return {"error": "No API Key", "status": "error", "duration": 0, "data": []}

        print(f"Running {name} with {len(queries)} queries...")
        start_time = asyncio.get_event_loop().time()
        
        # We assume strict orchestration by caller, so we run all these in parallel
        # But we still stagger them slightly to be nice to the API
        tasks = []
        
        async def run_one(q, idx):
            # No stagger, let's go fast
            retries = 3
            last_err = None
            for attempt in range(retries):
                try:
                    return await scraper_func([q], api_key=api_key, on_result=on_result)
                except Exception as e:
                    last_err = e
                    if "429" in str(e) or "503" in str(e):
                        await asyncio.sleep(2 * (attempt + 1))
                    else:
                        break
            return [{'query': q, 'response': None, 'error': str(last_err), 'status': 'failed'}]

        for i, q in enumerate(queries):
            tasks.append(run_one(q, i))
            
        results_nested = await asyncio.gather(*tasks)
        
        # Flatten
        merged = []
        for sublist in results_nested:
            merged.extend(sublist)
            
        duration = asyncio.get_event_loop().time() - start_time
        return {"data": merged, "duration": duration, "status": "success"}

    async def run_cartrade(self, queries, on_result=None):
        return await self._run_parallel_scraper(cartrade_chatbot_scraper, queries, "CarTrade", on_result)

    async def run_vyas(self, queries, on_result=None):
        return await self._run_parallel_scraper(vyas_chatbot_scraper, queries, "Vyas", on_result)

    async def run_chatgpt(self, queries, on_result=None):
        async def wrapped_chatgpt(q):
            return await chatgpt_query_processor_async(q, on_result=on_result)
        return await self._run_with_timing(wrapped_chatgpt, queries, "ChatGPT")

    async def run_all(self, queries, on_result=None):
        """
        Orchestrated implementation to maximize 25 sessions.
        Pass 1: Vyas(12) + CarTrade(13) = 25
        Pass 2: Vyas(13) + CarTrade(12) = 25
        """
        print(f"Starting Orchestrated Execution: {len(queries)} queries")
        start_time = asyncio.get_event_loop().time()

        # Callbacks
        def create_callback(source):
            if not on_result: return None
            async def wrapped_cb(res):
                if isinstance(res, dict): res['source'] = source
                await on_result(res)
            return wrapped_cb
        
        cb_vy = create_callback('vyas')
        cb_ct = create_callback('cartrade')
        cb_gpt = create_callback('chatgpt')

        # Split Indices
        # Vyas: [0:12] then [12:]
        # CarTrade: [0:13] then [13:]
        
        n = len(queries)
        # Sizing logic
        split_vy = 12
        split_ct = 13
        
        q_vy_1 = queries[:split_vy]
        q_vy_2 = queries[split_vy:]
        
        q_ct_1 = queries[:split_ct]
        q_ct_2 = queries[split_ct:]
        
        async def run_scrapers_orchestrated():
            # PASS 1
            print(f">> PASS 1: Vyas({len(q_vy_1)}) + CarTrade({len(q_ct_1)}) = {len(q_vy_1)+len(q_ct_1)} Sessions")
            t1 = self.run_vyas(q_vy_1, on_result=cb_vy)
            t2 = self.run_cartrade(q_ct_1, on_result=cb_ct)
            res_vy_1, res_ct_1 = await asyncio.gather(t1, t2)
            
            print(">> Pass 1 Done. Immediate transition...")
            
            # PASS 2
            print(f">> PASS 2: Vyas({len(q_vy_2)}) + CarTrade({len(q_ct_2)}) = {len(q_vy_2)+len(q_ct_2)} Sessions")
            t3 = self.run_vyas(q_vy_2, on_result=cb_vy)
            t4 = self.run_cartrade(q_ct_2, on_result=cb_ct)
            res_vy_2, res_ct_2 = await asyncio.gather(t3, t4)
            
            # Merge
            return (
                {'data': res_vy_1['data'] + res_vy_2['data'], 'status': 'success'},
                {'data': res_ct_1['data'] + res_ct_2['data'], 'status': 'success'}
            )

        # Launch
        task_gpt = asyncio.create_task(self.run_chatgpt(queries, on_result=cb_gpt))
        task_scrapers = asyncio.create_task(run_scrapers_orchestrated())
        
        res_gpt, (res_vy, res_ct) = await asyncio.gather(task_gpt, task_scrapers)
        
        total_duration = asyncio.get_event_loop().time() - start_time
        return {
            'cartrade': res_ct,
            'vyas': res_vy,
            'chatgpt': res_gpt,
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
