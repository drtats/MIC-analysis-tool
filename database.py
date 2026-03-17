import sqlite3
import os
import json
from typing import List, Dict, Any, Optional

DB_NAME = "mic_analysis.db"

def get_connection():
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "TURSO_DATABASE_URL" in st.secrets and "TURSO_AUTH_TOKEN" in st.secrets:
            # We use libsql_experimental as the drop-in sqlite3 replacement
            import libsql_experimental as libsql
            url = st.secrets["TURSO_DATABASE_URL"]
            token = st.secrets["TURSO_AUTH_TOKEN"]
            import platform
            if platform.system() == "Windows":
                 # On Windows, libsql-experimental might have issues, fallback to SQLite if URL looks local, but here we expect Turso.
                 # Actually libsql-experimental has windows wheels now, but let's just let it run.
                 pass
            return libsql.connect(database=url, auth_token=token)
    except Exception as e:
        print(f"Failed to connect to Turso: {e}")
    
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Create Experiments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS experiments (
            experiment_id TEXT PRIMARY KEY,
            date TEXT,
            person TEXT,
            reader TEXT,
            incubation_time REAL,
            inoculum_od REAL,
            growth_phase TEXT,
            harvest_od REAL,
            doubling_time REAL,
            notes TEXT,
            extra_metadata_json TEXT
        )
    ''')

    # Create Plates table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS plates (
            plate_id TEXT PRIMARY KEY,
            experiment_id TEXT,
            plate_name TEXT,
            plate_format INTEGER,
            threshold REAL,
            threshold_method TEXT,
            background_method TEXT,
            created_at TEXT,
            FOREIGN KEY (experiment_id) REFERENCES experiments (experiment_id)
        )
    ''')

    # Create Wells table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wells (
            well_id TEXT PRIMARY KEY,
            plate_id TEXT,
            well_position TEXT,
            row INTEGER,
            column INTEGER,
            od_raw REAL,
            od_bg_subtracted REAL,
            is_blank BOOLEAN,
            strain TEXT,
            antibiotic TEXT,
            concentration REAL,
            concentration_unit TEXT,
            media TEXT,
            replicate INTEGER,
            growth_call BOOLEAN,
            notes TEXT,
            extra_labels_json TEXT,
            FOREIGN KEY (plate_id) REFERENCES plates (plate_id),
            UNIQUE(plate_id, well_position)
        )
    ''')

    # Create MIC Results table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mic_results (
            mic_result_id TEXT PRIMARY KEY,
            plate_id TEXT,
            group_id TEXT,
            strain TEXT,
            antibiotic TEXT,
            media TEXT,
            replicate INTEGER,
            mic_value REAL,
            mic_operator TEXT,
            mic_unit TEXT,
            threshold_used REAL,
            lowest_tested_conc REAL,
            highest_tested_conc REAL,
            concentration_values_json TEXT,
            num_points INTEGER,
            calculation_status TEXT,
            warning TEXT,
            FOREIGN KEY (plate_id) REFERENCES plates (plate_id)
        )
    ''')

    # Create Saved Options table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_options (
            option_id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            value TEXT
        )
    ''')
    
    # Create Plate Templates table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS plate_templates (
            template_id TEXT PRIMARY KEY,
            template_name TEXT,
            layout_json TEXT,
            created_at TEXT
        )
    ''')

    # Migration: Check if extra_labels_json exists in wells
    cursor.execute('PRAGMA table_info(wells)')
    columns = [col[1] for col in cursor.fetchall()]
    if 'extra_labels_json' not in columns:
        cursor.execute('ALTER TABLE wells ADD COLUMN extra_labels_json TEXT')
        print("Added extra_labels_json to wells table.")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
