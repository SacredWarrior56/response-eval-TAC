
import streamlit as st
import subprocess
import signal
import os
import sys
import time
import pandas as pd
from datetime import datetime, timezone
from core.db_utils import get_active_run, get_recent_responses, update_run_status, get_run_stats, get_last_completed_run, ensure_metadata_column, get_all_run_headers
from core.constants import DEFAULT_QUERIES

st.set_page_config(page_title="Scraper Control Center", layout="wide")

# Title
st.title("🤖 Agent Scraper Control Center")

# Init DB Schema
ensure_metadata_column()
from nuke_db import nuke_db

# --- SIDEBAR: RUN CONTROL & HISTORY ---
st.sidebar.header("Run Management")

# 1. Fetch History
all_runs = get_all_run_headers() # Ordered DESC by DB

# Determine Active Run globally
global_active_run = get_active_run() # (id, name, created_at)

if global_active_run:
    # 1. Run Time
    run_start = global_active_run[2].astimezone(timezone.utc)
    now_tz = datetime.now(timezone.utc)
    run_elapsed = now_tz - run_start
    
    # 2. Batch Time
    # Parse Batch ID from Name: "Run X/Y [Batch UUID]"
    batch_elapsed_str = "0s"
    try:
        if "[" in global_active_run[1] and "Batch " in global_active_run[1]:
            batch_part = global_active_run[1].split("Batch ")[1].split("]")[0]
            # Find earliest start time for this batch
            batch_runs = [r for r in all_runs if batch_part in r[1]]
            if batch_runs:
                earliest = min([r[3] for r in batch_runs]).astimezone(timezone.utc)
                batch_time = now_tz - earliest
                batch_elapsed_str = f"{batch_time.total_seconds():.0f}s"
    except:
        batch_elapsed_str = "N/A"

    t1, t2 = st.sidebar.columns(2)
    t1.metric("Run Time", f"{run_elapsed.total_seconds():.0f}s")
    t2.metric("Batch Time", batch_elapsed_str)
    
    st.sidebar.markdown("---")

# Process for display:
# We want Run #1, Run #2 labels based on creation time.
runs_asc = sorted(all_runs, key=lambda x: x[3]) # Sort by created_at

run_options = {}
active_label = None

# Build map: Label -> ID
for i, r in enumerate(runs_asc):
    rid, name, status, created_at, completed_at = r
    time_str = created_at.strftime('%H:%M')
    
    label = f"Run #{i+1} - {name} ({time_str})"
        
    if status == 'running':
        label = f"🟢 {label}"
        if global_active_run and rid == global_active_run[0]:
            active_label = label
    elif status == 'completed':
        label = f"✅ {label}"
    elif status == 'terminated':
        label = f"🔴 {label}"
        
    run_options[label] = rid

# Reverse options for Sidebar (Newest First)
runs_display_order = list(run_options.keys())[::-1]

if not runs_display_order:
    run_options = {"No Runs Available": None}
    runs_display_order = ["No Runs Available"]

# Run Selector
# Verify index of active run if exists
sel_index = 0
if active_label and active_label in runs_display_order:
    sel_index = runs_display_order.index(active_label)

selected_label = st.sidebar.selectbox("Select Run to View", options=runs_display_order, index=sel_index)
selected_run_id = run_options.get(selected_label)

st.sidebar.markdown("---")

# 2. Start New Run (Only if NO active run)
if global_active_run:
    st.sidebar.info(f"🚫 Cannot start new run.\nActive: {global_active_run[1]}")
    st.sidebar.caption("Wait for current run OR Terminate it.")
else:
    st.sidebar.subheader("Start New")
    num_runs = st.sidebar.number_input("Batches (25 queries each)", min_value=1, max_value=100, value=1)
    if st.sidebar.button("🚀 START NEW RUN", type="primary", use_container_width=True):
        cmd = [sys.executable, "backend_runner.py", "--runs", str(num_runs)]
        proc = subprocess.Popen(cmd)
        with open("run.pid", "w") as f:
            f.write(str(proc.pid))
        st.toast(f"Started Run PID {proc.pid}")
        time.sleep(2)
        st.rerun()

st.sidebar.markdown("---")

# 3. Nuke
# 3. Nuke
with st.sidebar.expander("☢️ NUKE DATABASE", expanded=False):
    if global_active_run:
        st.error("🚫 Nuke Disabled: Run in progress.")
        st.caption("Terminate the current run first.")
    else:
        st.caption("WARNING: This will wipe all data.")
        access_code = st.text_input("Enter Access Code", type="password")
        if st.button("CONFIRM NUKE", type="secondary", use_container_width=True, key="nuke_global_btn"):
            if access_code == "password":
                nuke_db()
                st.toast("Database Nuked Successfully.")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Invalid Code")

# --- MAIN VIEW ---

if selected_run_id:
    # Get details for selected run
    # We have header data from all_runs matching selected_run_id
    # Find row
    selected_row = next((r for r in all_runs if r[0] == selected_run_id), None)
    if selected_row:
        rid, rname, rstatus, rcreated, rcompleted = selected_row
        
        # Header
        c1, c2 = st.columns([3, 1])
        with c1:
            st.subheader(f"{rname}")
            st.caption(f"ID: {rid} | Started: {rcreated.strftime('%Y-%m-%d %H:%M:%S')}")
        with c2:
            st.metric("Status", rstatus.upper())
            
        # Stats & Progress
        # Calculate totals
        try:
            plan_str = rname.split("Plan: ")[1].replace(")", "")
            total_runs_plan = int(plan_str)
            total_q_per_agent = total_runs_plan * len(DEFAULT_QUERIES)
        except:
            total_q_per_agent = 1
            
        stats = get_run_stats(rid)
        c_vy = stats.get('Vyas', 0)
        c_ct = stats.get('CarTrade', 0)
        c_gpt = stats.get('ChatGPT', 0)

        # Progress Bars
        dst_vy, dst_ct, dst_gpt = st.columns(3)
        dst_vy.progress(min(c_vy / total_q_per_agent, 1.0), text=f"Vyas: {c_vy}/{total_q_per_agent}")
        dst_ct.progress(min(c_ct / total_q_per_agent, 1.0), text=f"CarTrade: {c_ct}/{total_q_per_agent}")
        dst_gpt.progress(min(c_gpt / total_q_per_agent, 1.0), text=f"ChatGPT: {c_gpt}/{total_q_per_agent}")

        # Terminate Control (Only if THIS run is running)
        if rstatus == 'running':
             if st.button("🔴 TERMINATE THIS RUN"):
                 try:
                     if os.path.exists("run.pid"):
                         with open("run.pid", "r") as f:
                             pid = int(f.read())
                         os.kill(pid, signal.SIGTERM)
                 except: pass
                 update_run_status(rid, 'terminated')
                 st.rerun()
        else:
            # Delete Control (Only if NOT running)
            from core.db_utils import delete_run
            if st.button("🗑️ DELETE RUN", type="secondary"):
                delete_run(rid)
                st.toast(f"Deleted Run: {rname}")
                time.sleep(1)
                st.rerun()
        
        # Feed
        st.markdown("---")
        st.subheader("Data Feed (Sorted by Query Order)")
        
        recents = get_recent_responses(rid, limit=5000)
        
        t_vy, t_ct, t_gpt = st.tabs(["Vyas", "CarTrade", "ChatGPT"])
        
        def render_feed(container, source_name):
            filtered = [r for r in recents if r['source'].lower() == source_name.lower()]
            
            # Sort
            def sort_key(r):
                if r['query'] in DEFAULT_QUERIES:
                    return DEFAULT_QUERIES.index(r['query'])
                return 9999
            filtered.sort(key=sort_key)
            
            with container:
                if not filtered:
                    st.info("No data yet.")
                for r in filtered:
                    meta = r.get('metadata') or {}
                    metrics_data = meta.get('metrics', {})
                    
                    # 1. Resolve Time
                    # Prefer top-level 'time_taken' -> then metrics keys
                    time_val = meta.get('time_taken')
                    if time_val is None:
                        time_val = metrics_data.get('response_time_seconds') or metrics_data.get('processing_time_seconds') or 0.0
                    
                    # 2. Resolve Conversation ID
                    conv_id = meta.get('conversation_id') or metrics_data.get('conversation_file')
                    
                    # 3. Other metrics
                    chars = metrics_data.get('response_length_chars', 'N/A')
                    words = metrics_data.get('response_word_count', 'N/A')
                    
                    timestamp = r['created_at'].strftime('%H:%M:%S')
                    q_idx = DEFAULT_QUERIES.index(r['query']) + 1 if r['query'] in DEFAULT_QUERIES else '?'
                    
                    # Header: Query + Time
                    header = f"{q_idx}. {r['query']} [{timestamp}] — ⏱️ {float(time_val):.2f}s"
                    
                    with st.expander(header):
                        if conv_id:
                            st.caption(f"🆔 Conversation ID: `{conv_id}`")
                        
                        st.caption(f"**Metrics:** Words: {words} | Chars: {chars}")
                        st.text(r['response'])

        render_feed(t_vy, 'Vyas')
        render_feed(t_ct, 'CarTrade')
        render_feed(t_gpt, 'ChatGPT')
        
        # Auto-refresh ONLY if running
        if rstatus == 'running':
            time.sleep(3)
            st.rerun()

else:
    st.info("👋 Welcome! Use the sidebar to Start a New Run or select a completed run to view history.")
    
# Balloons Logic (Global check for COMPLETED events?)
# To preserve "🎉 All runs completed successfully!" capability:
# We can check if global_active_run JUST finished? 
# Or relying on user selecting the completed run.
# If user is watching a running run, and it completes, rstatus changes to 'completed' -> Balloons?

if selected_run_id and 'rstatus' in locals() and rstatus == 'completed':
    # Check if completed recently? 
    if rcompleted and rcompleted.tzinfo:
         now = datetime.now(timezone.utc)
         diff = (now - rcompleted.astimezone(timezone.utc)).total_seconds()
         if 0 <= diff < 10:
             st.balloons()
             st.success("🎉 Run Completed!")

# --- GLOBAL EXCEL DOWNLOAD ---
# Added at the bottom or sidebar. User asked for sidebar button or somewhere visible.
# "Do not allow to download the excel during a run is going on."
if not global_active_run:
    from core.db_utils import get_full_data_dump
    import io
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("📥 Export Data")
    
    # We use a button to trigger generation, then show download button, 
    # OR just a download button that calls a function.
    # st.download_button's 'data' arg can be a callback or computed on render.
    # Since we want it robust, we can compute it on press? No, download_button needs data ready.
    # If the DB is large, this is slow on every re-run.
    # BUT, we only show it when NO run is active, so re-runs are triggered by user interaction (clicks).
    # So it might be okay.
    
    # Or optimize: Only fetch when user clicks "Prepare Download"?
    # User said: "have a button called download excel".
    
    # Let's try direct download button. If it's too slow, we'll cache it.
    
    @st.cache_data(ttl=60, show_spinner="Preparing Excel...")
    def get_excel_bytes():
        raw_data = get_full_data_dump()
        if not raw_data:
            return None
        
        df = pd.DataFrame(raw_data)
        
        # Pivot or ensure columns: Query, Vyas, CarTrade, ChatGPT, Metadata
        # raw_data has: run_name, run_created_at, query, agent, response, metadata
        # We need to pivot to Query level? USER SAID: "Query, Vyas, CarTrade, ChatGPT, metadata"
        # Since we have runs, if we just dump all data, we have duplicates for query.
        # User said: "The excel downloaded should have all the data dumped on the database so far."
        # So I will keep 'Run Name' and 'Time' as columns, and pivot Agents.
        
        # Pivot: Index=[Run Name, Time, Query], Columns=[Agent], Values=[Response, Metadata]
        # This is tricky because we want Vyas Response AND Meta, CarTrade Response AND Meta.
        # Simpler: Just One row per response? No, "Query, Vyas, CarTrade, ChatGPT, metadata" implies wide format.
        
        # Let's try to group by (Run, Query).
        # We'll construct a new list of dicts.
        
        grouped = {}
        for row in raw_data:
            key = (row['run_name'], row['run_created_at'], row['query'])
            if key not in grouped:
                grouped[key] = {
                    'Run Name': row['run_name'],
                    'Run Date': row['run_created_at'],
                    'Query': row['query'],
                    'Vyas': None,
                    'CarTrade': None,
                    'ChatGPT': None,
                    'Metadata': {} 
                }
            
            agent = row['agent']
            if agent in ['Vyas', 'CarTrade', 'ChatGPT']:
                grouped[key][agent] = row['response']
                # Aggregate metadata
                grouped[key]['Metadata'][agent] = row['metadata']
                
        # Convert back to list
        final_rows = []
        for k, v in grouped.items():
            # Stringify metadata
            v['Metadata'] = json.dumps(v['Metadata'], indent=2)
            final_rows.append(v)
            
        df_pivot = pd.DataFrame(final_rows)
        
        # Reorder columns
        cols = ['Run Name', 'Run Date', 'Query', 'Vyas', 'CarTrade', 'ChatGPT', 'Metadata']
        # Filter only existing cols
        existing_cols = [c for c in cols if c in df_pivot.columns]
        df_pivot = df_pivot[existing_cols]
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_pivot.to_excel(writer, index=False, sheet_name='All Data')
        return output.getvalue()

    # The button
    # To avoid re-fetching on every script run (which happens on every interaction), we used cache.
    # But cache key needs to depend on DB state? 
    # Actually, get_excel_bytes is cached. If data changed, we need to invalidate. 
    # 'ttl=60' helps.
    
    excel_data = get_excel_bytes()
    if excel_data:
        st.sidebar.download_button(
            label="📊 Download Excel",
            data=excel_data,
            file_name=f"scraper_dump_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.sidebar.warning("No data found to export.")