from dotenv import load_dotenv
load_dotenv()  # <-- THIS loads your .env file

import psycopg2
import os
from pprint import pprint


# ---- Sanity check (leave this in; it saves hours of pain) ----
required_vars = ["PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"]
missing = [v for v in required_vars if not os.getenv(v)]

if missing:
    raise RuntimeError(f"Missing env vars: {missing}")

print("✅ Connecting to:", os.getenv("PGHOST"), ":", os.getenv("PGPORT"))


# ---- Connection (DigitalOcean compatible) ----
conn = psycopg2.connect(
    host=os.getenv("PGHOST"),
    port=int(os.getenv("PGPORT")),
    dbname=os.getenv("PGDATABASE"),
    user=os.getenv("PGUSER"),
    password=os.getenv("PGPASSWORD"),
    sslmode=os.getenv("PGSSLMODE", "require"),
)

cur = conn.cursor()


def q(sql):
    cur.execute(sql)
    return cur.fetchall()


print("\n===== DATABASE VERSION =====")
pprint(q("SELECT version();"))

print("\n===== EXTENSIONS =====")
pprint(q("""
    SELECT extname, extversion
    FROM pg_extension
    ORDER BY extname;
"""))

print("\n===== SCHEMAS =====")
pprint(q("""
    SELECT schema_name
    FROM information_schema.schemata
    ORDER BY schema_name;
"""))

print("\n===== TABLES =====")
pprint(q("""
    SELECT table_schema, table_name
    FROM information_schema.tables
    WHERE table_type = 'BASE TABLE'
      AND table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY table_schema, table_name;
"""))

print("\n===== COLUMNS =====")
pprint(q("""
    SELECT
        table_schema,
        table_name,
        column_name,
        data_type,
        is_nullable,
        column_default
    FROM information_schema.columns
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY table_schema, table_name, ordinal_position;
"""))

print("\n===== PRIMARY KEYS =====")
pprint(q("""
    SELECT
        tc.table_schema,
        tc.table_name,
        kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
    WHERE tc.constraint_type = 'PRIMARY KEY'
    ORDER BY tc.table_schema, tc.table_name;
"""))

print("\n===== FOREIGN KEYS =====")
pprint(q("""
    SELECT
        tc.table_schema,
        tc.table_name,
        kcu.column_name,
        ccu.table_schema AS foreign_schema,
        ccu.table_name AS foreign_table,
        ccu.column_name AS foreign_column
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name
    WHERE tc.constraint_type = 'FOREIGN KEY'
    ORDER BY tc.table_schema, tc.table_name;
"""))

print("\n===== INDEXES =====")
pprint(q("""
    SELECT
        schemaname,
        tablename,
        indexname,
        indexdef
    FROM pg_indexes
    WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
    ORDER BY schemaname, tablename;
"""))

print("\n===== UNIQUE & CHECK CONSTRAINTS =====")
pprint(q("""
    SELECT
        tc.table_schema,
        tc.table_name,
        tc.constraint_type,
        tc.constraint_name
    FROM information_schema.table_constraints tc
    WHERE tc.constraint_type IN ('UNIQUE', 'CHECK')
    ORDER BY tc.table_schema, tc.table_name;
"""))

print("\n===== VIEWS =====")
pprint(q("""
    SELECT table_schema, table_name
    FROM information_schema.views
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY table_schema, table_name;
"""))

print("\n===== FUNCTIONS =====")
pprint(q("""
    SELECT
        n.nspname AS schema,
        p.proname AS function_name
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
    ORDER BY schema, function_name;
"""))

print("\n===== TRIGGERS =====")
pprint(q("""
    SELECT
        event_object_schema,
        event_object_table,
        trigger_name,
        action_timing,
        event_manipulation
    FROM information_schema.triggers
    ORDER BY event_object_schema, event_object_table;
"""))

cur.close()
conn.close()

print("\n✅ Database inspection completed successfully.")
