
import asyncio
import argparse
import sys
import traceback
import uuid
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
    
    # 2. Setup Batch Context
    batch_uuid = str(uuid.uuid4())[:8]
    print(f"Batch ID: {batch_uuid}")
    
    wrapper = ScraperWrapper()
    
    try:
        for i in range(num_runs):
            # Create DISTINCT run record
            run_name = f"Run {i+1}/{num_runs} [Batch {batch_uuid}]"
            current_run_id = create_run(run_name, 1) # Plan is 1 for this individual run
            print(f"=== Starting Run {i+1}/{num_runs} (ID: {current_run_id}) ===")
            
            # Callback to log to DB (captures current_run_id)
            async def on_result(res):
                source = res.get('source', 'Unknown')
                text = res.get('response') or ""
                query = res.get('query', "")
                
                # Normalize Time Taken
                time_taken = res.get('response_time_seconds') or res.get('processing_time_seconds') or 0.0
                
                # Metadata Base
                meta = {
                    'metrics': {
                        k: v for k, v in res.items() 
                        if k not in ['source', 'response', 'query']
                    },
                    'batch_id': batch_uuid,
                    'run_index': i+1,
                    # Explicit Top-Level Fields as requested
                    'time_taken': float(f"{time_taken:.2f}"),
                }
                
                # Vyas Specific: Conversation ID
                if source.lower() == 'vyas':
                    conv_file = res.get('conversation_file')
                    if conv_file:
                        meta['conversation_id'] = conv_file
                
                # Log
                agent_id = agent_ids.get(source)
                if agent_id:
                    log_response(current_run_id, agent_id, query, text, meta)
                    if source.lower() == 'vyas':
                        print(f"Logged {source} result (Time: {time_taken:.2f}s, ID: {meta.get('conversation_id', 'N/A')})")
                    else:
                        print(f"Logged {source} result (Time: {time_taken:.2f}s)")

            # Execute
            await wrapper.run_all(DEFAULT_QUERIES, on_result=on_result)
            
            update_run_status(current_run_id, 'completed')
            print(f"=== Completed Run {i+1}/{num_runs} ===")
            
        print("All runs in batch completed successfully.")
        
    except Exception as e:
        print(f"Batch execution failed: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1, help="Number of runs")
    args = parser.parse_args()
    
    asyncio.run(main(args.runs))
