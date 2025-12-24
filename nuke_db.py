
from core.db_utils import get_db_connection

def nuke_db():
    print("Nuking Database...")
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Cascade truncate to clear all data but keep schema? 
        # User said "comeback to a clean slate".
        # If I drop tables, I must recreate schema.
        # If I truncate, I keep schema.
        # Given the error "column metadata does not exist", the schema is WRONG.
        # So I should DROP TABLES and let them be recreated (via inspect_postgres or I just recreate response table?)
        
        # Best approach: Drop 'responses', 'runs', 'queries', 'agents'.
        cur.execute("""
            DROP TABLE IF EXISTS responses CASCADE;
            DROP TABLE IF EXISTS runs CASCADE;
            DROP TABLE IF EXISTS queries CASCADE;
            DROP TABLE IF EXISTS agents CASCADE;
        """)
        
        # Recreate Schema (Based on user request dump)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name TEXT NOT NULL,
                version TEXT
            );
            
            CREATE TABLE IF NOT EXISTS runs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name TEXT,
                status TEXT DEFAULT 'running',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                completed_at TIMESTAMP WITH TIME ZONE
            );
            
            CREATE TABLE IF NOT EXISTS queries (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                query_text TEXT NOT NULL UNIQUE
            );
            
            CREATE TABLE IF NOT EXISTS responses (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                run_id UUID REFERENCES runs(id),
                query_id UUID REFERENCES queries(id),
                agent_id UUID REFERENCES agents(id),
                response_text TEXT NOT NULL,
                metadata JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(run_id, query_id, agent_id)
            );
        """)
        conn.commit()
        print("Database Nuked and Schema Recreated.")
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    nuke_db()
