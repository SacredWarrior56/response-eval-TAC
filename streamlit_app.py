
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
all_runs = get_all_run_headers() # [(id, name, status, created_at, completed_at), ...]

# Determine Active Run globally
global_active_run = get_active_run() # (id, name, created_at)

# Format options for selectbox
run_options = {}
default_index = 0

if all_runs:
    for i, r in enumerate(all_runs):
        rid, name, status, created_at, completed_at = r
        # Label: "[Running] Batch Exec... (10:00:05)"
        time_str = created_at.strftime('%m-%d %H:%M')
        label = f"[{status.upper()}] {name} ({time_str})"
        run_options[label] = rid
        
        # If this is the active run, try to set as default if not manually overridden?
        # Streamlit resets on rerun, so we need to be careful.
        # Logic: If global_active_run exists, default to it? 
        # But if user selected another one, we want to stay there.
        # We'll rely on Streamlit's widget state persistence basically.
        
else:
    run_options = {"No Runs Available": None}

# Run Selector
selected_label = st.sidebar.selectbox("Select Run to View", options=list(run_options.keys()))
selected_run_id = run_options[selected_label]

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
with st.sidebar.expander("☢️ NUKE DATABASE", expanded=False):
    st.caption("WARNING: This will wipe all data.")
    access_code = st.text_input("Enter Access Code", type="password")
    if st.button("CONFIRM NUKE", type="secondary", use_container_width=True):
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
                    m = []
                    if 'response_time_seconds' in metrics_data: m.append(f"Time: {metrics_data['response_time_seconds']:.2f}s")
                    if 'response_length_chars' in metrics_data: m.append(f"Chars: {metrics_data['response_length_chars']}")
                    if 'response_word_count' in metrics_data: m.append(f"Words: {metrics_data['response_word_count']}")
                    m_str = " | ".join(m)
                    
                    timestamp = r['created_at'].strftime('%H:%M:%S')
                    q_idx = DEFAULT_QUERIES.index(r['query']) + 1 if r['query'] in DEFAULT_QUERIES else '?'
                    
                    with st.expander(f"{q_idx}. {r['query']} [{timestamp}]"):
                        st.markdown(f"**Metrics:** {m_str}")
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