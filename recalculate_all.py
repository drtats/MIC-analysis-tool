import sqlite3
import json
import uuid
from typing import List
from models import WellData, MICResult
from mic_calc import group_and_calculate_mics

DB_NAME = "mic_analysis.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def recalculate_all():
    print("Starting bulk MIC recalculation...")
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all plates
    plates = cursor.execute("SELECT plate_id, threshold FROM plates").fetchall()
    print(f"Found {len(plates)} plates to process.")

    for plate in plates:
        pid = plate['plate_id']
        threshold = plate['threshold']
        print(f"Processing plate: {pid} (Threshold: {threshold})")

        # --- DEDUPLICATION STEP ---
        # Find duplicates (same position) and keep the one with highest rowid
        cursor.execute('''
            DELETE FROM wells 
            WHERE plate_id = ? AND rowid NOT IN (
                SELECT MAX(rowid) 
                FROM wells 
                WHERE plate_id = ? 
                GROUP BY well_position
            )
        ''', (pid, pid))
        
        # Load cleaned wells
        wells_rows = cursor.execute("SELECT * FROM wells WHERE plate_id = ?", (pid,)).fetchall()
        wells = []
        for row in wells_rows:
            d = dict(row)
            if d.get('extra_labels_json'):
                d['extra_labels'] = json.loads(d['extra_labels_json'])
            
            if d.get('concentration_unit') is None:
                d['concentration_unit'] = "ug/mL"
            
            wells.append(WellData(**d))

        if not wells:
            print(f"  No wells found for plate {pid}. Skipping.")
            continue

        # Re-verify growth_calls based on the threshold
        for w in wells:
            if w.od_bg_subtracted is not None:
                w.growth_call = w.od_bg_subtracted > threshold

        new_results = group_and_calculate_mics(wells)
        for r in new_results:
            r.threshold_used = threshold

        # Clear old results for this plate
        cursor.execute("DELETE FROM mic_results WHERE plate_id = ?", (pid,))

        # Insert new results
        for m in new_results:
            cursor.execute('''
                INSERT INTO mic_results (
                    mic_result_id, plate_id, group_id, strain, antibiotic, media, replicate,
                    mic_value, mic_operator, mic_unit, threshold_used, lowest_tested_conc,
                    highest_tested_conc, concentration_values_json, num_points, calculation_status, warning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                m.mic_result_id, m.plate_id, m.group_id, m.strain, m.antibiotic, m.media, m.replicate,
                m.mic_value, m.mic_operator, m.mic_unit, m.threshold_used, m.lowest_tested_conc,
                m.highest_tested_conc, m.concentration_values_json, m.num_points, m.calculation_status, m.warning
            ))
        
        # Update normalized names
        for w in wells:
            cursor.execute('''
                UPDATE wells SET 
                    strain = ?, antibiotic = ?, media = ?, replicate = ?
                WHERE well_id = ?
            ''', (w.strain, w.antibiotic, w.media, w.replicate, w.well_id))

    conn.commit()
    conn.close()
    print("Recalculation complete.")

if __name__ == "__main__":
    recalculate_all()
