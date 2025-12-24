
import streamlit as st
import subprocess
import signal
import os
import sys
import time
import pandas as pd
from datetime import datetime, timezone
from core.db_utils import get_active_run, get_recent_responses, update_run_status, get_run_stats, get_last_completed_run, ensure_metadata_column
from core.constants import DEFAULT_QUERIES

st.set_page_config(page_title="Scraper Control Center", layout="wide")

# Title
st.title("🤖 Agent Scraper Control Center")

# Init DB Schema
ensure_metadata_column()
from nuke_db import nuke_db

# Sidebar
st.sidebar.header("Configuration")
num_runs = st.sidebar.number_input("Number of Full Batches (25 queries each)", min_value=1, max_value=100, value=1)

st.sidebar.markdown("---")
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

# Check for active run
active_run = get_active_run()

if active_run:
    run_id, run_name, created_at = active_run
    
    # --- RUNNING STATE ---
    # Timer
    elapsed = datetime.now(timezone.utc) - created_at.astimezone(timezone.utc)
    st.sidebar.metric("⏱️ Elapsed Time", f"{elapsed.total_seconds():.0f}s")

    st.info(f"🔵 **Test in Progress:** {run_name}")
    
    # Calculate totals
    try:
        plan_str = run_name.split("Plan: ")[1].replace(")", "")
        total_runs_plan = int(plan_str)
        total_q_per_agent = total_runs_plan * len(DEFAULT_QUERIES)
    except:
        total_q_per_agent = 1
        
    stats = get_run_stats(run_id)
    c_vy = stats.get('Vyas', 0)
    c_ct = stats.get('CarTrade', 0)
    c_gpt = stats.get('ChatGPT', 0)

    # Progress Bars
    dst_vy, dst_ct, dst_gpt = st.columns(3)
    dst_vy.progress(min(c_vy / total_q_per_agent, 1.0), text=f"Vyas: {c_vy}/{total_q_per_agent}")
    dst_ct.progress(min(c_ct / total_q_per_agent, 1.0), text=f"CarTrade: {c_ct}/{total_q_per_agent}")
    dst_gpt.progress(min(c_gpt / total_q_per_agent, 1.0), text=f"ChatGPT: {c_gpt}/{total_q_per_agent}")
    
    # Terminate Button (Sidebar or Top?)
    if st.sidebar.button("🔴 TERMINATE RUN"):
         try:
             if os.path.exists("run.pid"):
                 with open("run.pid", "r") as f:
                     pid = int(f.read())
                 os.kill(pid, signal.SIGTERM)
                 st.toast("Process terminated.")
         except: pass
         update_run_status(run_id, 'terminated')
         st.rerun()
    st.subheader("Live Response Feed (Sorted by Query Order)")
    
    # Fetch ALL for this run
    recents = get_recent_responses(run_id, limit=5000)
    
    t_vy, t_ct, t_gpt = st.tabs(["Vyas", "CarTrade", "ChatGPT"])
    
    def render_feed(container, source_name):
        # Filter for source
        filtered = [r for r in recents if r['source'].lower() == source_name.lower()]
        
        # Validate and Sort by DEFAULT_QUERIES index
        valid_queries = []
        for r in filtered:
            if r['query'] in DEFAULT_QUERIES:
                valid_queries.append(r)
            else:
                 # Handle unknown queries (maybe from old list)
                 r['_sort_idx'] = 9999
                 valid_queries.append(r)
        
        # Sort key
        def sort_key(r):
            if r['query'] in DEFAULT_QUERIES:
                return DEFAULT_QUERIES.index(r['query'])
            return 9999
            
        filtered.sort(key=sort_key)
        
        with container:
            if not filtered:
                st.caption("No responses yet.")
            for r in filtered:
                # Construct Metrics String
                meta = r.get('metadata') or {}
                metrics_data = meta.get('metrics', {})
                
                m = []
                if 'response_time_seconds' in metrics_data: m.append(f"Time: {metrics_data['response_time_seconds']:.2f}s")
                if 'response_length_chars' in metrics_data: m.append(f"Chars: {metrics_data['response_length_chars']}")
                if 'response_word_count' in metrics_data: m.append(f"Words: {metrics_data['response_word_count']}")
                m_str = " | ".join(m)
                
                # Check run index if multiple runs? 
                # If we have multiple runs, we might have duplicate queries.
                # User wants "runs" 10 times.
                # So we will have 10 entries for "Alto vs kwid".
                # Display them all? Or group?
                # User said "systematically dump... show it on UI".
                # I will show them all. Maybe add timestamp to header differentiates them.
                
                timestamp = r['created_at'].strftime('%H:%M:%S')
                with st.expander(f"{DEFAULT_QUERIES.index(r['query']) + 1}. {r['query']}  [{timestamp}]"):
                    st.markdown(f"**Metrics:** {m_str}")
                    st.text(r['response'])
    
    render_feed(t_vy, 'Vyas')
    render_feed(t_ct, 'CarTrade')
    render_feed(t_gpt, 'ChatGPT')

    # Auto-refresh
    time.sleep(3)
    st.rerun()

else:
    # --- IDLE STATE ---
    # Check for recent completion
    last_run = get_last_completed_run()
    if last_run:
        rid, completed_at = last_run
        now = datetime.now(timezone.utc)
        if completed_at.tzinfo:
             diff = (now - completed_at.astimezone(timezone.utc)).total_seconds()
             if 0 <= diff < 30: 
                 st.balloons()
                 st.success("🎉 All runs completed successfully!")

    st.success("✅ System Ready")
    
    if st.button("🚀 START EXECUTION", type="primary", use_container_width=True):
        # Clean import inside button just in case, but rely on top level
        cmd = [sys.executable, "backend_runner.py", "--runs", str(num_runs)]
        
        proc = subprocess.Popen(cmd)
        
        with open("run.pid", "w") as f:
            f.write(str(proc.pid))
            
        st.toast(f"Execution started with PID {proc.pid}")
        time.sleep(2)
        st.rerun()

    st.markdown("---")
    with st.expander("Manual / Debug Mode"):
        st.write("Use this to run locally in this browser session (Original Mode)")
        if st.button("Run Custom Logic (Debug)"):
            st.write("Not implemented in this refactor.")