import streamlit as st
import asyncio
import os
import sys
import time

# Add the project root to sys.path to ensure core module can be found
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.wrapper import ScraperWrapper
from core.logger_setup import setup_logging

# Silence terminal output
setup_logging()

# Page configuration
st.set_page_config(
    page_title="TAC Response Evaluation",
    page_icon="🤖",
    layout="wide"
)

# Initialize wrapper
# Initialize wrapper
@st.cache_resource
def get_wrapper():
    return ScraperWrapper()

try:
    wrapper = get_wrapper()
except Exception as e:
    st.error(f"Failed to initialize wrapper: {e}")
    st.stop()

st.title("🤖 TAC Response Evaluation & Scraping")

# Sidebar for status
with st.sidebar:
    st.header("Configuration")
    if os.path.exists(".env"):
        st.success("✅ .env file found")
    else:
        st.error("❌ .env file missing")
        st.info("Please create a .env file with your API keys.")
        
    st.info("Supported Scrapers:\n- CarTrade\n- Vyas\n- ChatGPT")

    st.divider()
    if st.button("Clear Results"):
        st.session_state['live_results'] = {'cartrade': [], 'vyas': [], 'chatgpt': []}
        st.session_state['results'] = {}
        st.rerun()

# Main content
st.subheader("Run Scrapers")

default_queries = """Alto vs kwid vs tiago
3xo vs nexon
Best car tata harrier or kia seltos
Grand vitara Sigma and delta difference
Forchnur vs mg gloster which is better for drive
Nexon ev is powerful or Punch ev
Which is best car to buy in 2025 creta or elevate
Nexon petrol vs punch petrol
Compare Nexon variants
curve vs curve ev
Nexon petrol vs punch diesel
best off-roading car under 25 lakhs
5 seater compat 4x4 family car (Budget - 15 lakhs maximum)
Find me right car under value 15 lakhs based on performance, safety and comfort.
Best milage car within Rs 10 lakh
6 air bag, turbo engine under 10lakh
I want best automation transmission car under 15-17 lakhs ehich has premium looks and money for value varient
Best car for 16 lakhs budget automatic and sunroof
Lowest price car with premium features with cruise control feature
Suggest a blue colour tata car below 15 Lacs
Which car is the best option for hill area under 9.5lacs on road price
torque converter cars in india
electric plus petrol car 25 lakhs
Nexon smart + AMT vs Exter vs Sonet. Or anything in that budget of 10L with automatic transmission for city 60:40 highway
3XO diesel vs nexon diesel,priorities are better NVH , better overall perfomance and less turbo lag ,should be equally good for steep hills"""

query_input = st.text_area("Enter your queries (one per line):", value=default_queries, height=400)

queries = [q.strip() for q in query_input.split('\n') if q.strip()]

col1, col2, col3, col4 = st.columns(4)

async def run_wrapper(method, *args):
    """Helper to run async wrapper methods."""
    return await method(*args)

def run_async(coro):
    """Helper to run async code in Streamlit."""
    try:
        # Check if there is a running loop
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
        
    if loop and loop.is_running():
        # If we are in a running loop (e.g. inside another async function), we should await
        # But Streamlit is sync.
        # This branch is unlikely unless Streamlit changes its execution model.
        return loop.run_until_complete(coro)
    else:
        return asyncio.run(coro)

# Initialize session state for live results if not present
if 'live_results' not in st.session_state:
    st.session_state['live_results'] = {'cartrade': [], 'vyas': [], 'chatgpt': []}

if col1.button("Run ALL Scrapers", type="primary"):
    if not queries:
        st.warning("Please enter at least one query.")
    else:
        # Clear previous results
        st.session_state['live_results'] = {'cartrade': [], 'vyas': [], 'chatgpt': []}
        st.session_state['results'] = {} # Clear final stats
        
        # Create placeholders for live updates
        status_container = st.status("Initializing scrapers...", expanded=True)
        timer_placeholder = st.sidebar.empty()
        
        # Create tabs early so we can populate them
        tab_ct, tab_vy, tab_gpt = st.tabs(["CarTrade", "Vyas", "ChatGPT"])
        
        # specific progress bars
        ct_progress = tab_ct.progress(0, text="Waiting...")
        vy_progress = tab_vy.progress(0, text="Waiting...")
        gpt_progress = tab_gpt.progress(0, text="Waiting...")
        
        ct_container = tab_ct.container()
        vy_container = tab_vy.container()
        gpt_container = tab_gpt.container()
        
        start_time = time.time()
        
        async def on_stream_result(result):
            """Callback for live updates."""
            source = result.get('source', 'unknown')
            
            # Update data
            st.session_state['live_results'][source].append(result)
            
            # Update Timer
            current_time = time.time() - start_time
            timer_placeholder.metric("Elapsed Time", f"{current_time:.1f}s")
            
            # Update UI for specific source
            # We use local containers for immediate feedback
            if source == 'cartrade': target_container = ct_container
            elif source == 'vyas': target_container = vy_container
            elif source == 'chatgpt': target_container = gpt_container
            
            def format_metrics(res, source):
                metrics = []
                # Common metrics
                if 'response_time_seconds' in res:
                    metrics.append(f"Time: {res['response_time_seconds']:.2f}s")
                elif 'processing_time_seconds' in res:
                    metrics.append(f"Time: {res['processing_time_seconds']:.2f}s")
                    
                if 'response_length_chars' in res:
                     metrics.append(f"Chars: {res['response_length_chars']}")
                if 'response_word_count' in res:
                     metrics.append(f"Words: {res['response_word_count']}")
                     
                # Source specific
                if source == 'chatgpt' and 'tokens_used' in res:
                    metrics.append(f"Tokens: {res['tokens_used']}")
                
                # Vyas conversation file
                if 'conversation_file' in res and res['conversation_file']:
                     metrics.append(f"File: {res['conversation_file']}")
                    
                return " | ".join(metrics)

            if target_container:
                with target_container:
                    # Append new result card
                    metrics_str = format_metrics(result, source)
                    with st.expander(f"Query: {result.get('query', 'Unknown')}  [{metrics_str}]", expanded=False):
                        st.markdown(f"**Metrics:** {metrics_str}")
                        if result.get('conversation_file'):
                            st.caption(f"📁 Conversation saved to: `{result['conversation_file']}`")
                        st.write("**Response:**")
                        st.write(result.get('response') or "No response")
                        st.caption(f"Status: {result.get('status')} | Time: {result.get('timestamp')}")
                        if 'error' in result:
                            st.error(f"Error details: {result['error']}")
            
            # Update overall status
            count_ct = len(st.session_state['live_results']['cartrade'])
            count_vy = len(st.session_state['live_results']['vyas'])
            count_gpt = len(st.session_state['live_results']['chatgpt'])
            
            total_q = len(queries)
            if total_q > 0:
                ct_progress.progress(min(count_ct / total_q, 1.0), text=f"Progress: {count_ct}/{total_q}")
                vy_progress.progress(min(count_vy / total_q, 1.0), text=f"Progress: {count_vy}/{total_q}")
                gpt_progress.progress(min(count_gpt / total_q, 1.0), text=f"Progress: {count_gpt}/{total_q}")
            
            status_container.update(label=f"Running... (CarTrade: {count_ct}/{total_q}, Vyas: {count_vy}/{total_q}, ChatGPT: {count_gpt}/{total_q})")
            
        
        try:
            # We use run_async to drive the execution
            final_stats = run_async(wrapper.run_all(queries, on_result=on_stream_result))
            
            st.session_state['results'] = final_stats
            
            # Final sync validation - Ensure live results match final count
            # Use 'final_stats' to ensure final state consistency
            status_container.update(label="Analysis Complete!", state="complete", expanded=False)
            timer_placeholder.metric("Total Time", f"{final_stats.get('total_duration', 0):.2f}s")
            
            # Force progress 100% on complete
            ct_progress.progress(1.0, text=f"Done: {len(queries)}/{len(queries)}")
            vy_progress.progress(1.0, text=f"Done: {len(queries)}/{len(queries)}")
            gpt_progress.progress(1.0, text=f"Done: {len(queries)}/{len(queries)}")

            st.success("Analysis complete!")
            
        except Exception as e:
            st.error(f"Execution failed: {e}")
            status_container.update(label="Failed", state="error")

if col2.button("Run CarTrade"):
    if not queries:
        st.warning("Please enter at least one query.")
    else:
        st.info("Live update not implemented for single runner yet. Use 'Run ALL' for live view.")
        with st.spinner("Running CarTrade scraper..."):
            try:
                results = run_async(wrapper.run_cartrade(queries))
                st.session_state['results'] = {'cartrade': results}
                st.success("CarTrade analysis complete!")
            except Exception as e:
                st.error(f"Execution failed: {e}")

if col3.button("Run Vyas"):
    if not queries:
        st.warning("Please enter at least one query.")
    else:
        st.info("Live update not implemented for single runner yet. Use 'Run ALL' for live view.")
        with st.spinner("Running Vyas scraper..."):
            try:
                results = run_async(wrapper.run_vyas(queries))
                st.session_state['results'] = {'vyas': results}
                st.success("Vyas analysis complete!")
            except Exception as e:
                st.error(f"Execution failed: {e}")

if col4.button("Run ChatGPT"):
    if not queries:
        st.warning("Please enter at least one query.")
    else:
        st.info("Live update not implemented for single runner yet. Use 'Run ALL' for live view.")
        with st.spinner("Running ChatGPT scraper..."):
            try:
                results = run_async(wrapper.run_chatgpt(queries))
                st.session_state['results'] = {'chatgpt': results}
                st.success("ChatGPT analysis complete!")
            except Exception as e:
                st.error(f"Execution failed: {e}")

# Display Final Summary (if not already shown by live view)
if 'results' in st.session_state and not st.session_state.get('live_results'):
    results = st.session_state['results']
    st.divider()
    
    # Display total duration if available
    if 'total_duration' in results:
        st.subheader("Results")
        st.metric("Total Execution Time", f"{results['total_duration']:.2f}s")
        # Remove total_duration from iteration items
        display_results = {k: v for k, v in results.items() if k != 'total_duration'}
    else:
        st.subheader("Results")
        display_results = results

    if not display_results:
        st.info("No results to display.")
    else:
        # Create tabs for each scraper present in results
        tabs = st.tabs([k.capitalize() for k in display_results.keys()])
        
        for i, (scraper_name, scraper_data) in enumerate(display_results.items()):
            with tabs[i]:
                # Check if it's the new format with timing
                if isinstance(scraper_data, dict) and 'data' in scraper_data:
                    duration = scraper_data.get('duration', 0)
                    status = scraper_data.get('status', 'unknown')
                    data = scraper_data.get('data')
                    error = scraper_data.get('error')

                    col_time, col_status = st.columns(2)
                    col_time.metric("Execution Time", f"{duration:.2f}s")
                    col_status.metric("Status", status.upper())

                    if error:
                        st.error(f"Error: {error}")
                    
                    if data:
                        st.write(f"Found {len(data)} results")
                        for item in data:
                            query_text = item.get('query', 'Unknown')
                            
                            # Re-use metric logic slightly differently here or just inline
                            metrics = []
                            if 'response_time_seconds' in item: metrics.append(f"Time: {item['response_time_seconds']:.2f}s")
                            if 'processing_time_seconds' in item: metrics.append(f"Time: {item['processing_time_seconds']:.2f}s")
                            if 'response_length_chars' in item: metrics.append(f"Chars: {item['response_length_chars']}")
                            if 'tokens_used' in item: metrics.append(f"Tokens: {item['tokens_used']}")
                            if 'conversation_file' in item and item['conversation_file']: metrics.append(f"File: {item['conversation_file']}")
                            
                            metrics_str = " | ".join(metrics)
                            
                            with st.expander(f"Query: {query_text} [{metrics_str}]", expanded=True):
                                st.markdown(f"**Metrics:** {metrics_str}")
                                if item.get('conversation_file'):
                                     st.caption(f"📁 Conversation saved to: `{item['conversation_file']}`")
                                st.write("**Response:**")
                                st.write(item.get('response') or "No response")
                                st.caption(f"Status: {item.get('status')} | Time: {item.get('timestamp')}")
                                if 'error' in item:
                                    st.error(f"Error details: {item['error']}")
                                st.json(item)
                
                # Fallback for old format or unexpected structure
                elif isinstance(scraper_data, dict) and 'error' in scraper_data:
                     st.error(f"Error: {scraper_data['error']}")
                elif isinstance(scraper_data, list):
                    st.write(f"Found {len(scraper_data)} results")
                    for item in scraper_data:
                        with st.expander(f"Query: {item.get('query', 'Unknown')}", expanded=True):
                            st.write("**Response:**")
                            st.write(item.get('response') or "No response")
                            st.caption(f"Status: {item.get('status')} | Time: {item.get('timestamp')}")
                            if 'error' in item:
                                st.error(f"Error details: {item['error']}")
                            st.json(item)
                else:
                    st.json(scraper_data)