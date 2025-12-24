
import asyncio
import argparse
import sys
import traceback
from core.wrapper import ScraperWrapper
from core.db_utils import (
    ensure_metadata_column, init_agents, create_run, 
    update_run_status, log_response
)
from core.constants import DEFAULT_QUERIES

async def main(num_runs):
    print(f"Starting Backend Runner for {num_runs} runs...")
    
    # 1. Init DB
    ensure_metadata_column()
    raw_agent_ids = init_agents()
    # Normalize keys to lowercase for matching
    agent_ids = {k.lower(): v for k, v in raw_agent_ids.items()}
    print("Agents initialized:", agent_ids)
    
    # 2. Create Run Record
    run_id = create_run("Batch Execution", num_runs)
    print(f"Run ID created: {run_id}")
    
    wrapper = ScraperWrapper()
    
    try:
        for i in range(num_runs):
            print(f"=== Starting Run {i+1}/{num_runs} ===")
            
            # Callback to log to DB
            async def on_result(res):
                source = res.get('source', 'Unknown')
                text = res.get('response') or ""
                query = res.get('query', "")
                
                # Metadata
                meta = {
                    'metrics': {
                        k: v for k, v in res.items() 
                        if k not in ['source', 'response', 'query']
                    }
                }
                
                # Log
                agent_id = agent_ids.get(source)
                if agent_id:
                    log_response(run_id, agent_id, query, text, meta)
                    print(f"Logged {source} result for query: {query[:30]}...")
            
            # Execute
            await wrapper.run_all(DEFAULT_QUERIES, on_result=on_result)
            
            print(f"=== Completed Run {i+1}/{num_runs} ===")
            
        update_run_status(run_id, 'completed')
        print("All runs completed successfully.")
        
    except Exception as e:
        print(f"Run failed: {e}")
        traceback.print_exc()
        update_run_status(run_id, 'failed')
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1, help="Number of runs")
    args = parser.parse_args()
    
    asyncio.run(main(args.runs))
