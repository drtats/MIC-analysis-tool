import sqlite3
import os
import json
from typing import List, Dict, Any, Optional

DB_NAME = "mic_analysis.db"

import requests

class TursoCursor:
    def __init__(self, url, token):
        self.url = url
        self.token = token
        self._description = None
        self._results = []
        self._rowcount = -1

    def _execute_remote(self, sql, args=()):
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
                {"type": "execute", "stmt": {"sql": sql, "args": mapped_args}},
                {"type": "close"}
            ]
        }
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        resp = requests.post(f"{self.url}/v2/pipeline", json=payload, headers=headers)
        resp.raise_for_status()
        results = resp.json()["results"]
        if results[0]["type"] == "error":
            raise Exception(results[0]["error"]["message"])
        
        res = results[0]["response"]["result"]
        if "cols" in res:
            self._description = [(col["name"], None, None, None, None, None, None) for col in res["cols"]]
        else:
            self._description = None
            
        if "rows" in res:
            # Depending on libsql version, rows are dictionaries with {"type": "text", "value": "..."}
            parsed_rows = []
            for row in res["rows"]:
                parsed_row = []
                for val_dict in row:
                    if val_dict["type"] == "null":
                        parsed_row.append(None)
                    elif val_dict["type"] == "integer":
                        parsed_row.append(int(val_dict["value"]))
                    elif val_dict["type"] == "float":
                        parsed_row.append(float(val_dict["value"]))
                    else:
                        parsed_row.append(val_dict.get("value", None))
                parsed_rows.append(tuple(parsed_row))
            self._results = parsed_rows
            self._rowcount = len(parsed_rows)
        else:
            self._results = []
            # For non-select statements, affected_row_count might be in res
            self._rowcount = res.get("affected_row_count", 0) if "rows" not in res else len(self._results)
            
        return self

    def execute(self, sql, args=()):
        if str(sql).strip().upper() == "BEGIN TRANSACTION":
            return self
        return self._execute_remote(sql, args)
        
    @property
    def description(self):
        return self._description

    @property
    def rowcount(self):
        return self._rowcount

    def fetchone(self):
        return self._results.pop(0) if self._results else None
        
    def fetchall(self):
        res = self._results
        self._results = []
        return res
        
    def fetchmany(self, size=1):
        res = self._results[:size]
        self._results = self._results[size:]
        return res

    def close(self):
        pass

    def __iter__(self):
        return self

    def __next__(self):
        if not self._results:
            raise StopIteration
        return self._results.pop(0)

class TursoConnection:
    def __init__(self, url, token):
        self.url = url.replace("libsql://", "https://").replace("wss://", "https://")
        self.token = token
        
    def cursor(self):
        return TursoCursor(self.url, self.token)
        
    def execute(self, sql, args=()):
        # DBAPI2 execute usually returns None, but some impls return the cursor.
        # However, custom ones often benefit from returning self if chained.
        # But here we should probably return a cursor if we want to mimic sqlite3.
        cur = self.cursor()
        return cur.execute(sql, args)
        
    def commit(self):
        pass
        
    def rollback(self):
        pass
        
    def close(self):
        pass

def get_connection():
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "TURSO_DATABASE_URL" in st.secrets and "TURSO_AUTH_TOKEN" in st.secrets:
            url = st.secrets["TURSO_DATABASE_URL"]
            token = st.secrets["TURSO_AUTH_TOKEN"]
            return TursoConnection(url, token)
    except Exception as e:
        import streamlit as st
        st.error(f"Failed to connect to Turso: {e}")
        pass
    
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
