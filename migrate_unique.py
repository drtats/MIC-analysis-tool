import sqlite3

def migrate():
    conn = sqlite3.connect('mic_analysis.db')
    cursor = conn.cursor()
    
    # Check if index already exists
    cursor.execute("PRAGMA index_list('wells')")
    indexes = cursor.fetchall()
    # index_list returns (seq, name, unique, origin, partial)
    if any(idx[2] == 1 and 'well_position' in str(idx[1]) for idx in indexes):
        print("Unique index already exists.")
        conn.close()
        return

    print("Migrating wells table to add UNIQUE constraint...")
    
    # 1. Ensure no duplicates exist (should be done by recalculate_all, but let's be safe)
    cursor.execute('''
        DELETE FROM wells 
        WHERE rowid NOT IN (
            SELECT MAX(rowid) FROM wells GROUP BY plate_id, well_position
        )
    ''')
    
    # 2. Add the unique index
    try:
        cursor.execute("CREATE UNIQUE INDEX idx_wells_plate_pos ON wells(plate_id, well_position)")
        print("Unique index created successfully.")
    except Exception as e:
        print(f"Error creating unique index: {e}")
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
