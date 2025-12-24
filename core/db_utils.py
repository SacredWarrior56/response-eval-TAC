
import os
import psycopg2
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv

# Load env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# Setup Logger
import logging
db_logger = logging.getLogger('db_logger')
db_logger.setLevel(logging.INFO)
fh = logging.FileHandler('db_log.log')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
if not db_logger.handlers:
    db_logger.addHandler(fh)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("PGHOST"),
        port=int(os.getenv("PGPORT")),
        dbname=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        sslmode=os.getenv("PGSSLMODE", "require"),
    )

def ensure_metadata_column():
    """Idempotently add metadata column to responses table."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            ALTER TABLE responses 
            ADD COLUMN IF NOT EXISTS metadata JSONB;
        """)
        conn.commit()
    except Exception as e:
        db_logger.warning(f"Migration warning: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def init_agents():
    """Ensure agents exist in DB."""
    conn = get_db_connection()
    cur = conn.cursor()
    agents = ['Vyas', 'CarTrade', 'ChatGPT']
    ids = {}
    try:
        for name in agents:
            # Check exist
            cur.execute("SELECT id FROM agents WHERE name = %s", (name,))
            res = cur.fetchone()
            if res:
                ids[name] = res[0]
            else:
                new_id = str(uuid.uuid4())
                cur.execute("INSERT INTO agents (id, name) VALUES (%s, %s)", (new_id, name))
                ids[name] = new_id
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
    return ids

def create_run(run_name, total_runs_planned):
    """Create a new run entry."""
    conn = get_db_connection()
    cur = conn.cursor()
    run_id = str(uuid.uuid4())
    try:
        # We store total runs planned in metadata of the run or name?
        # status 'running' is default
        cur.execute("""
            INSERT INTO runs (id, name, status, created_at)
            VALUES (%s, %s, %s, NOW())
        """, (run_id, f"{run_name} (Plan: {total_runs_planned})", 'running'))
        conn.commit()
        db_logger.info(f"Created Run: {run_id} ({run_name})")
        return run_id
    except Exception as e:
        db_logger.error(f"Create Run Error: {e}")
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def update_run_status(run_id, status):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE runs SET status = %s, completed_at = %s WHERE id = %s", 
                   (status, datetime.now() if status in ['completed', 'terminated'] else None, run_id))
        conn.commit()
    finally:
        cur.close()
        conn.close()

def log_response(run_id, agent_id, query_text, response_text, meta):
    """
    Log a response.
    Also ensures query exists in 'queries' table.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 1. Ensure Query
        cur.execute("SELECT id FROM queries WHERE query_text = %s", (query_text,))
        q_res = cur.fetchone()
        if q_res:
            query_id = q_res[0]
        else:
            query_id = str(uuid.uuid4())
            cur.execute("INSERT INTO queries (id, query_text) VALUES (%s, %s)", (query_id, query_text))
        
        # 2. Insert Response
        # Check if already exists for this run/agent/query (idempotency)
        # Unique constraint: (run_id, query_id, agent_id)
        
        # We need to handle potential conflict if we retry?
        resp_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO responses (id, run_id, query_id, agent_id, response_text, metadata, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (run_id, query_id, agent_id) 
            DO UPDATE SET response_text = EXCLUDED.response_text, metadata = EXCLUDED.metadata, created_at = NOW()
        """, (resp_id, run_id, query_id, agent_id, response_text, json.dumps(meta)))
        
        conn.commit()
        db_logger.info(f"Logged response: {resp_id} (Run: {run_id}, Agent: {agent_id})")
    except Exception as e:
        db_logger.error(f"DB Log Error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def get_active_run():
    """Get the most recent running run."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, name, created_at FROM runs 
            WHERE status = 'running' 
            ORDER BY created_at DESC 
            LIMIT 1
        """)
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()

def get_run_stats(run_id):
    """Get stats for a run."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT a.name, COUNT(*) 
            FROM responses r 
            JOIN agents a ON r.agent_id = a.id 
            WHERE r.run_id = %s 
            GROUP BY a.name
        """, (run_id,))
        return dict(cur.fetchall())
    finally:
        cur.close()
        conn.close()

def get_last_completed_run():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, completed_at FROM runs 
            WHERE status = 'completed' 
            ORDER BY completed_at DESC 
            LIMIT 1
        """)
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()

def get_recent_responses(run_id, limit=50):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT a.name, q.query_text, r.response_text, r.metadata, r.created_at
            FROM responses r
            JOIN agents a ON r.agent_id = a.id
            JOIN queries q ON r.query_id = q.id
            WHERE r.run_id = %s
            ORDER BY r.created_at DESC
            LIMIT %s
        """, (run_id, limit))
        
        # Convert to list of dicts
        cols = ['source', 'query', 'response', 'metadata', 'created_at']
        results = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            # Flatten metadata if needed or keep raw
            if d['metadata']:
                # Ensure it's dict
                if isinstance(d['metadata'], str):
                    d.update(json.loads(d['metadata']))
                else:
                    d.update(d['metadata'])
            results.append(d)
        return results
    finally:
        cur.close()
        conn.close()

