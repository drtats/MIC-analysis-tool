import sqlite3
import os
import json
import requests
import streamlit as st

LOCAL_DB = "mic_analysis.db"

try:
    TURSO_URL = st.secrets["TURSO_DATABASE_URL"]
    TURSO_TOKEN = st.secrets["TURSO_AUTH_TOKEN"]
except Exception:
    print("Error: Could not find TURSO_DATABASE_URL or TURSO_AUTH_TOKEN in .streamlit/secrets.toml")
    exit(1)

# Format URL for HTTP API (remove libsql:// or wss:// and use https://)
http_url = TURSO_URL.replace("libsql://", "https://").replace("wss://", "https://")

def execute_remote(query, args=()):
    # Convert args to Turso HTTP API format
    mapped_args = []
    for arg in args:
        if arg is None:
            mapped_args.append({"type": "null"})
        elif isinstance(arg, int):
            mapped_args.append({"type": "integer", "value": str(arg)})
        elif isinstance(arg, float):
            mapped_args.append({"type": "float", "value": arg})
        else:
            mapped_args.append({"type": "text", "value": str(arg)})

    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": query,
                    "args": mapped_args
                }
            },
            {
                "type": "close"
            }
        ]
    }
    
    headers = {
        "Authorization": f"Bearer {TURSO_TOKEN}",
        "Content-Type": "application/json"
    }

    resp = requests.post(f"{http_url}/v2/pipeline", json=payload, headers=headers)
    resp.raise_for_status()
    # The response is an array of results matching the requests array
    results = resp.json()["results"]
    if results[0]["type"] == "error":
        raise Exception(results[0]["error"]["message"])
    return results[0]["response"]["result"]

def migrate():
    print("Connecting to local database...")
    local_conn = sqlite3.connect(LOCAL_DB)
    local_cursor = local_conn.cursor()

    print(f"Connecting to Turso database via HTTP API at {http_url}...")

    # Get list of all tables
    local_cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in local_cursor.fetchall() if row[0] != "sqlite_sequence"]

    print("Initializing schema on Turso...")
    # Fetch schemas from local
    local_cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    schemas = [row[0] for row in local_cursor.fetchall() if row[0]]
    for s in schemas:
        s_safe = s.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1)
        execute_remote(s_safe)

    for table in tables:
        print(f"Migrating data for table: {table}...")
        local_cursor.execute(f"SELECT * FROM {table}")
        rows = local_cursor.fetchall()
        
        if not rows:
            print(f"  - Table {table} is empty, skipping.")
            continue
            
        col_names = [description[0] for description in local_cursor.description]
        placeholders = ", ".join(["?"] * len(col_names))
        insert_query = f"INSERT OR IGNORE INTO {table} ({', '.join(col_names)}) VALUES ({placeholders})"
        
        success = 0
        for row in rows:
            try:
                execute_remote(insert_query, row)
                success += 1
            except Exception as e:
                print(f"  ! Error migrating row in {table}: {e}")
        
        print(f"  + Successfully migrated {success}/{len(rows)} rows to {table}.")

    local_conn.close()
    print("\nMigration complete!")

if __name__ == "__main__":
    migrate()
