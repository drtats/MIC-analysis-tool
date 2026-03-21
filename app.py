import streamlit as st
import pandas as pd
import numpy as np
import uuid
import json
from datetime import datetime
from typing import List, Dict

from database import init_db, get_connection
from models import WellData, PlateData, ExperimentData, MICResult
from parser import matrix_to_long_format
from background import calculate_background, subtract_background, apply_threshold
from mic_calc import group_and_calculate_mics
from plotting import plot_plate_heatmap, plot_growth_map, plot_mic_dot_plot

# Page Config
st.set_page_config(page_title="MIC Analysis Tool", layout="wide")

def get_admin_password():
    # 1. Try local file (for local development)
    try:
        if os.path.exists(".admin_password"):
            with open(".admin_password", "r") as f:
                return f.read().strip()
    except:
        pass
        
    # 2. Try st.secrets (for Streamlit Cloud)
    try:
        import streamlit as st
        if "ADMIN_PASSWORD" in st.secrets:
            return str(st.secrets["ADMIN_PASSWORD"]).strip()
    except:
        pass
        
    return None

# Initialize DB
init_db()
if 'db_init' not in st.session_state:
    st.session_state.db_init = True

# Helper to create empty 8x12 grid
def create_empty_grid(fill_val=""):
    return pd.DataFrame(
        np.full((8, 12), fill_val),
        index=list("ABCDEFGH"),
        columns=[str(i) for i in range(1, 13)]
    )

# Session State for current plate grids
if 'grids' not in st.session_state:
    st.session_state.grids = {
        "Raw OD": create_empty_grid(0.0),
        "Strain": create_empty_grid(""),
        "Antibiotic": create_empty_grid(""),
        "Concentration": create_empty_grid(0.0),
        "Media": create_empty_grid(""),
        "Replicate": create_empty_grid(1),
        "Blank": create_empty_grid(False)
    }

if 'dynamic_labels' not in st.session_state:
    st.session_state.dynamic_labels = []

if 'current_plate_id' not in st.session_state:
    st.session_state.current_plate_id = str(uuid.uuid4())
if 'wells' not in st.session_state:
    st.session_state.wells = []

def check_for_existing_plate(plate_name, date_str):
    conn = get_connection()
    res = conn.execute('''
        SELECT p.plate_id FROM plates p 
        JOIN experiments e ON p.experiment_id = e.experiment_id
        WHERE p.plate_name = ? AND e.date = ?
    ''', (plate_name, date_str)).fetchone()
    conn.close()
    return res[0] if res else None

def save_plate_to_db(exp: ExperimentData, plate: PlateData, wells: List[WellData], mics: List[MICResult]):
    conn = get_connection()
    try:
        stmts = []
        
        # 1. Insert/Replace Experiment
        stmts.append((
            '''
            INSERT OR REPLACE INTO experiments (
                experiment_id, date, person, reader, incubation_time, 
                inoculum_od, growth_phase, harvest_od, doubling_time, notes, extra_metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (exp.experiment_id, exp.date, exp.person, exp.reader, exp.incubation_time,
             exp.inoculum_od, exp.growth_phase, exp.harvest_od, exp.doubling_time, exp.notes, exp.extra_metadata_json)
        ))
        
        # 2. Insert/Replace Plate
        stmts.append((
            '''
            INSERT OR REPLACE INTO plates (plate_id, experiment_id, plate_name, threshold, created_at) 
            VALUES (?, ?, ?, ?, ?)
            ''',
            (plate.plate_id, plate.experiment_id, plate.plate_name, plate.threshold, plate.created_at.isoformat())
        ))
        
        # 3. Clear and Insert Wells
        stmts.append(('DELETE FROM wells WHERE plate_id = ?', (plate.plate_id,)))
        for w in wells:
            stmts.append((
                '''
                INSERT INTO wells (
                    well_id, plate_id, well_position, row, column, od_raw, od_bg_subtracted, 
                    is_blank, strain, antibiotic, concentration, concentration_unit, media, replicate, growth_call, notes, extra_labels_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (w.well_id, w.plate_id, w.well_position, w.row, w.column, w.od_raw, w.od_bg_subtracted,
                 w.is_blank, w.strain, w.antibiotic, w.concentration, w.concentration_unit, w.media, w.replicate, 
                 w.growth_call, w.notes, json.dumps(w.extra_labels))
            ))
            
        # 4. Clear and Insert MIC Results
        stmts.append(('DELETE FROM mic_results WHERE plate_id = ?', (plate.plate_id,)))
        for m in mics:
            stmts.append((
                '''
                INSERT INTO mic_results (
                    mic_result_id, plate_id, group_id, strain, antibiotic, media, replicate,
                    mic_value, mic_operator, mic_unit, threshold_used, lowest_tested_conc,
                    highest_tested_conc, concentration_values_json, num_points, calculation_status, warning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (m.mic_result_id, m.plate_id, m.group_id, m.strain, m.antibiotic, m.media, m.replicate,
                 m.mic_value, m.mic_operator, m.mic_unit, m.threshold_used, m.lowest_tested_conc,
                 m.highest_tested_conc, m.concentration_values_json, m.num_points, m.calculation_status, m.warning)
            ))
        
        # Execute based on connection type
        from database import TursoConnection
        if isinstance(conn, TursoConnection):
            conn.execute_batch(stmts)
        else:
            cursor = conn.cursor()
            cursor.execute("BEGIN TRANSACTION")
            for sql, args in stmts:
                cursor.execute(sql, args)
            conn.commit()
            
    except Exception as e:
        if not isinstance(conn, TursoConnection):
            conn.rollback()
        raise e
    finally:
        conn.close()

def render_editor_and_logic(prefix, metadata_defaults=None, editable=True):
    # Lock/Unlock button
    is_disabled = not editable
    
    st.header("1. Experiment Metadata")
    with st.expander("Show Metadata Form", expanded=True):
        col1, col2 = st.columns(2)
        
        # Use defaults if provided
        d = metadata_defaults or {}
        
        with col1:
            m_date = st.date_input("Date", value=datetime.fromisoformat(d.get('date')) if isinstance(d.get('date'), str) else (d.get('date') or datetime.today()), key=f"{prefix}_date", disabled=is_disabled)
            m_person = st.text_input("Person", value=d.get('person', ""), placeholder="Researcher Initials", key=f"{prefix}_person", disabled=is_disabled)
            m_reader = st.text_input("Reader Used", value=d.get('reader', ""), key=f"{prefix}_reader", disabled=is_disabled)
            m_inc = st.number_input("Incubation Time (hrs)", value=float(d.get('incubation_time', 0.0)), min_value=0.0, step=0.5, key=f"{prefix}_inc", disabled=is_disabled)
        with col2:
            m_pn = st.text_input("Plate Name", value=d.get('plate_name', "Plate 1"), key=f"{prefix}_pn", disabled=is_disabled)
            m_th = st.number_input("Threshold (OD)", value=float(d.get('threshold', 0.010)), format="%.3f", key=f"{prefix}_th", disabled=is_disabled)
            m_in_od = st.number_input("Inoculum OD", value=float(d.get('inoculum_od', 0.0)), format="%.4f", key=f"{prefix}_in_od", disabled=is_disabled)
            gp_list = ["Lag", "Exponential", "Stationary", "Custom"]
            m_gp = st.selectbox("Growth Phase", gp_list, index=gp_list.index(d['growth_phase']) if d.get('growth_phase') in gp_list else 1, key=f"{prefix}_gp", disabled=is_disabled)
        
        col3, col4 = st.columns(2)
        with col3:
            m_h_od = st.number_input("Harvest OD", value=float(d.get('harvest_od', 0.0)), format="%.4f", key=f"{prefix}_h_od", disabled=is_disabled)
            m_dt = st.number_input("Doubling Time (min)", value=float(d.get('doubling_time', 0.0)), min_value=0.0, step=1.0, key=f"{prefix}_dt", disabled=is_disabled)
        with col4:
            m_notes = st.text_area("Notes", value=d.get('notes', ""), height=68, key=f"{prefix}_notes", disabled=is_disabled)

    st.header("2. Plate Layout & Data")
    
    # Fill Helpers (Only show when unlocked)
    if not is_disabled:
        with st.expander("Fill Helpers"):
            fill_col1, fill_col2, fill_col3 = st.columns(3)
            all_grids = list(st.session_state.grids.keys())
            target_grid = fill_col1.selectbox("Target Grid", all_grids, key=f"{prefix}_fill_target")
            f_val = fill_col2.text_input("Value to Fill", key=f"{prefix}_fill_val")
            f_type = fill_col3.selectbox("Fill Type", ["Full Plate", "Row", "Column"], key=f"{prefix}_fill_type")
            
            row_idx = None
            col_idx = None
            if f_type == "Row":
                row_idx = st.selectbox("Select Row", list("ABCDEFGH"), key=f"{prefix}_fill_row_sel")
            elif f_type == "Column":
                col_idx = st.selectbox("Select Column", [str(i) for i in range(1, 13)], key=f"{prefix}_fill_col_sel")

            if st.button("Apply Fill", key=f"{prefix}_fill_btn"):
                if f_type == "Full Plate":
                    st.session_state.grids[target_grid] = create_empty_grid(f_val)
                elif f_type == "Row":
                    if row_idx:
                        st.session_state.grids[target_grid].loc[row_idx, :] = f_val
                elif f_type == "Column":
                    if col_idx:
                        st.session_state.grids[target_grid].loc[:, col_idx] = f_val
                st.success(f"Applied {f_val} to {target_grid}")

        # Dynamic Tabs (Only show when unlocked)
        st.subheader("Manage Custom Labels")
        n_label = st.text_input("Add New Label Grid (e.g., 'Oxygen')", key=f"{prefix}_label_input")
        if st.button("Add Tab", key=f"{prefix}_tab_btn") and n_label:
            if n_label not in st.session_state.grids:
                st.session_state.grids[n_label] = create_empty_grid("")
                st.session_state.dynamic_labels.append(n_label)
                st.rerun()

    # Render Tabs
    tab_list = list(st.session_state.grids.keys())
    tabs = st.tabs(tab_list)
    for i, t_name in enumerate(tab_list):
        with tabs[i]:
            st.markdown(f"**{t_name} Map**")
            st.session_state.grids[t_name] = st.data_editor(
                st.session_state.grids[t_name], 
                width="stretch", 
                key=f"editor_{prefix}_{t_name.lower().replace(' ', '_')}",
                disabled=is_disabled
            )

    if not is_disabled:
        if st.button("Process & Save Changes", type="primary", key=f"{prefix}_process_btn"):
            try:
                wells = []
                for r_idx, r_label in enumerate(list("ABCDEFGH")):
                    for c_idx in range(12):
                        c_label = str(c_idx + 1)
                        well_pos = f"{r_label}{c_label}"
                        
                        g = st.session_state.grids
                        w = WellData(
                            plate_id=st.session_state.current_plate_id,
                            well_position=well_pos,
                            row=r_idx,
                            column=c_idx,
                            od_raw=float(g["Raw OD"].at[r_label, c_label]),
                            is_blank=bool(g["Blank"].at[r_label, c_label]),
                            strain=str(g["Strain"].at[r_label, c_label]),
                            antibiotic=str(g["Antibiotic"].at[r_label, c_label]),
                            concentration=float(g["Concentration"].at[r_label, c_label]),
                            media=str(g["Media"].at[r_label, c_label]),
                            replicate=int(g["Replicate"].at[r_label, c_label])
                        )
                        for label in st.session_state.dynamic_labels:
                            w.extra_labels[label] = str(g[label].at[r_label, c_label])
                        wells.append(w)

                bg_val = calculate_background(wells)
                subtract_background(wells, bg_val)
                apply_threshold(wells, m_th)
                results = group_and_calculate_mics(wells)
                for r in results:
                    r.threshold_used = m_th
                
                st.session_state.wells = wells
                st.session_state.mic_results = results
                
                exp = ExperimentData(
                    experiment_id=m_pn + "_" + str(m_date), # basic ID or preserve if editing
                    date=str(m_date), person=m_person, reader=m_reader,
                    incubation_time=float(m_inc), inoculum_od=float(m_in_od),
                    growth_phase=m_gp, harvest_od=float(m_h_od),
                    doubling_time=float(m_dt), notes=m_notes
                )
                # If editing, preserve experiment_id from d
                if d.get('experiment_id'):
                    exp.experiment_id = d['experiment_id']

                plate = PlateData(
                    plate_id=st.session_state.current_plate_id,
                    experiment_id=exp.experiment_id,
                    plate_name=m_pn,
                    threshold=m_th
                )
                
                # Collision Check for New Plate
                if prefix == "new":
                    existing_pid = check_for_existing_plate(m_pn, str(m_date))
                    if existing_pid and existing_pid != st.session_state.current_plate_id:
                        st.warning(f"⚠️ A plate named '{m_pn}' on {m_date} already exists. Saving will overwrite the previous record.")
                        if not st.checkbox("Confirm Overwrite", key=f"{prefix}_confirm_overwrite"):
                            st.stop()
                        else:
                            # Use the existing PID to perform the update instead of a new one
                            plate.plate_id = existing_pid
                            for w in wells: w.plate_id = existing_pid

                save_plate_to_db(exp, plate, wells, results)
                st.success(f"Plate '{m_pn}' processed and saved successfully!")
                st.rerun() # Refresh results
            except Exception as e:
                st.error(f"Error during save: {e}")

# --- SIDEBAR ---
if 'nav_mode' not in st.session_state:
    st.session_state.nav_mode = "New Plate"

with st.sidebar:
    st.title("MIC Analysis")
    nav_options = ["New Plate", "Plate Library", "Search Results", "Visualization"]
    mode = st.radio("Navigation", nav_options, index=nav_options.index(st.session_state.nav_mode))
    st.session_state.nav_mode = mode
    
    # Mode switch clearing
    if 'last_mode' not in st.session_state:
        st.session_state.last_mode = mode
    
    if st.session_state.last_mode != mode:
        st.session_state.wells = []
        if 'mic_results' in st.session_state:
            st.session_state.mic_results = []
        if 'loaded_plate_name' in st.session_state:
            st.session_state.loaded_plate_name = ""
        if 'loaded_successfully' in st.session_state:
            st.session_state.loaded_successfully = False
        if 'loaded_metadata' in st.session_state:
            st.session_state.loaded_metadata = None
        if 'lib_edit_mode' in st.session_state:
            st.session_state.lib_edit_mode = False
        # Reset current_plate_id on new plate start
        if mode == "New Plate":
            st.session_state.current_plate_id = str(uuid.uuid4())
            st.session_state.grids = {
                "Raw OD": create_empty_grid(0.0),
                "Strain": create_empty_grid(""),
                "Antibiotic": create_empty_grid(""),
                "Concentration": create_empty_grid(0.0),
                "Media": create_empty_grid(""),
                "Replicate": create_empty_grid(1),
                "Blank": create_empty_grid(False)
            }
            st.session_state.dynamic_labels = []
            
        st.session_state.last_mode = mode
        st.rerun()

if mode == "New Plate":
    render_editor_and_logic("new")

elif mode == "Plate Library":
    st.header("Plate Library")
    conn = get_connection()
    df_plates = pd.read_sql_query('''
        SELECT p.plate_id, p.plate_name, e.date, e.person, e.reader, p.threshold, p.created_at, p.is_locked, p.is_checked
        FROM plates p
        JOIN experiments e ON p.experiment_id = e.experiment_id
        WHERE p.is_deleted = 0
        ORDER BY p.created_at DESC
    ''', conn)
    conn.close()
    
    if not df_plates.empty:
        st.dataframe(df_plates, width="stretch")
        
        # If coming from search, pre-select
        lib_idx = 0
        if st.session_state.get('selected_search_plate_id') in df_plates["plate_id"].values:
            lib_idx = list(df_plates["plate_id"].values).index(st.session_state['selected_search_plate_id'])
            
        selected_pid = st.selectbox("Select Plate ID", df_plates["plate_id"], index=lib_idx, key="lib_sel_pid")
        
        if st.button("Load Data & View Result", key="lib_load_btn"):
            try:
                conn = get_connection()
                # Get metadata for filling the forms
                row_raw = conn.execute('''
                    SELECT p.*, e.* FROM plates p 
                    JOIN experiments e ON p.experiment_id = e.experiment_id 
                    WHERE p.plate_id = ?
                ''', (selected_pid,)).fetchone()
                
                # Fetch columns
                p_cols = [d[0] for d in conn.execute("SELECT * FROM plates LIMIT 1").description]
                e_cols = [d[0] for d in conn.execute("SELECT * FROM experiments LIMIT 1").description]
                
                # Fetch wells to reconstruct grids
                wells_df = pd.read_sql_query("SELECT * FROM wells WHERE plate_id = ?", conn, params=(selected_pid,))
                results_df = pd.read_sql_query("SELECT * FROM mic_results WHERE plate_id = ?", conn, params=(selected_pid,))
                conn.close()
                
                # Update grids and metadata in session state
                st.session_state.loaded_metadata = dict(zip(p_cols + e_cols, list(row_raw)))
                
                # Reset grids to empty then fill
                st.session_state.grids = {
                    "Raw OD": create_empty_grid(0.0),
                    "Strain": create_empty_grid(""),
                    "Antibiotic": create_empty_grid(""),
                    "Concentration": create_empty_grid(0.0),
                    "Media": create_empty_grid(""),
                    "Replicate": create_empty_grid(1),
                    "Blank": create_empty_grid(False)
                }
                st.session_state.dynamic_labels = []
                
                wells = []
                for _, w in wells_df.iterrows():
                    row_dict = w.to_dict()
                    if row_dict.get('extra_labels_json'):
                        row_dict['extra_labels'] = json.loads(row_dict['extra_labels_json'])
                        for k in row_dict['extra_labels']:
                            if k not in st.session_state.grids:
                                st.session_state.grids[k] = create_empty_grid("")
                                st.session_state.dynamic_labels.append(k)
                    
                    r_l = list("ABCDEFGH")[w['row']]; c_l = str(w['column'] + 1)
                    st.session_state.grids["Raw OD"].at[r_l, c_l] = w['od_raw']
                    st.session_state.grids["Strain"].at[r_l, c_l] = w['strain'] or ""
                    st.session_state.grids["Antibiotic"].at[r_l, c_l] = w['antibiotic'] or ""
                    st.session_state.grids["Concentration"].at[r_l, c_l] = w['concentration'] or 0.0
                    st.session_state.grids["Media"].at[r_l, c_l] = w['media'] or ""
                    st.session_state.grids["Replicate"].at[r_l, c_l] = w['replicate'] or 1
                    st.session_state.grids["Blank"].at[r_l, c_l] = bool(w['is_blank'])
                    if row_dict.get('extra_labels'):
                        for k, v in row_dict['extra_labels'].items():
                            st.session_state.grids[k].at[r_l, c_l] = v

                    if row_dict.get('concentration_unit') is None:
                        row_dict['concentration_unit'] = "ug/mL"
                    wells.append(WellData(**row_dict))

                st.session_state.wells = wells
                
                mics = []
                for _, row in results_df.iterrows():
                    row_dict = row.to_dict()
                    if row_dict.get('calculation_status') is None:
                        row_dict['calculation_status'] = "success"
                    mics.append(MICResult(**row_dict))
                st.session_state.mic_results = mics
                st.session_state.current_plate_id = selected_pid
                st.session_state.loaded_successfully = True
                st.success("Loaded successfully!")
                st.rerun()
            except Exception as e:
                import traceback
                st.error(f"Load failed: {e}")
                st.code(traceback.format_exc())

    else:
        st.info("No saved data found.")

elif mode == "Search Results":
    st.header("Search MIC Results")
    conn = get_connection()
    
    # Discovery available fields
    exp_fields = ['experiment_id', 'date', 'person', 'reader', 'incubation_time', 'inoculum_od', 'growth_phase', 'harvest_od', 'doubling_time', 'notes']
    plate_fields = ['plate_name', 'plate_format', 'threshold', 'created_at']
    mic_fields = ['strain', 'antibiotic', 'media', 'replicate', 'mic_value', 'mic_operator', 'mic_unit', 'warning']
    
    # Try to find custom labels across all experiments
    all_label_keys = set()
    label_search = conn.execute("SELECT DISTINCT extra_labels_json FROM wells WHERE extra_labels_json IS NOT NULL").fetchall()
    for row in label_search:
        try:
            if row[0]:
                all_label_keys.update(json.loads(row[0]).keys())
        except: pass
    custom_label_list = sorted(list(all_label_keys))
    
    col_sel1, col_sel2 = st.columns([1, 2])
    
    with col_sel1:
        st.subheader("1. Add Filters")
        # Standard filters first
        strains = [r[0] for r in conn.execute("SELECT DISTINCT strain FROM mic_results").fetchall() if r[0]]
        abs = [r[0] for r in conn.execute("SELECT DISTINCT antibiotic FROM mic_results").fetchall() if r[0]]
        
        f_strain = st.multiselect("Filter Strains", ["All"] + strains, default="All", key="search_f_strain")
        f_ab = st.multiselect("Filter Antibiotics", ["All"] + abs, default="All", key="search_f_ab")
        
        # Add dynamic filter
        available_filters = sorted(exp_fields + plate_fields + ['media'] + custom_label_list)
        new_filter_field = st.selectbox("Add another Filter field", ["-- Select --"] + available_filters)
        
        if 'search_extra_filters' not in st.session_state:
            st.session_state.search_extra_filters = {}
            
        if new_filter_field != "-- Select --":
            if new_filter_field not in st.session_state.search_extra_filters:
                st.session_state.search_extra_filters[new_filter_field] = ""
        
        # Render extra filters
        to_delete = []
        for field, val in st.session_state.search_extra_filters.items():
            col_f1, col_f2 = st.columns([4, 1])
            st.session_state.search_extra_filters[field] = col_f1.text_input(f"Filter {field}", value=val, key=f"f_input_{field}")
            if col_f2.button("✖", key=f"f_del_{field}"):
                to_delete.append(field)
        for field in to_delete:
            del st.session_state.search_extra_filters[field]
            st.rerun()

    with col_sel2:
        st.subheader("2. Choose Columns")
        default_cols = ["date", "plate_name", "strain", "antibiotic", "mic_operator", "mic_value", "replicate"]
        all_possible_cols = sorted(list(set(exp_fields + plate_fields + mic_fields + custom_label_list)))
        display_cols = st.multiselect("Columns to display", all_possible_cols, default=default_cols)
    
    # Build Query
    # Note: custom labels require a subquery or join with wells
    # Since labels are per-well, we aggregate them by picking the first well's label for that replicate group
    # We join mic_results (m) with plates (p) and experiments (e)
    
    select_clause = []
    for c in display_cols:
        if c in mic_fields: select_clause.append(f"m.{c}")
        elif c in plate_fields: select_clause.append(f"p.{c}")
        elif c in exp_fields: select_clause.append(f"e.{c}")
        elif c in custom_label_list: 
            # This is tricky because it's inside JSON. 
            # We'll use SQLite's json_extract if available, or just join with wells.
            # SQLite 3.38+ has ->> for json_extract.
            select_clause.append(f"json_extract(w.extra_labels_json, '$.{c}') as {c}")
    
    # We also always need plate_id, plate_name, date, strain for the navigation dropdown
    mandatory_cols = [('plate_id', 'm'), ('plate_name', 'p'), ('date', 'e'), ('strain', 'm')]
    current_select_names = [c.split(' as ')[-1].split('.')[-1] for c in select_clause]
    
    for col, table in mandatory_cols:
        if col not in current_select_names:
            select_clause.append(f"{table}.{col}")
    
    query = f"""
        SELECT {', '.join(select_clause)}
        FROM mic_results m
        JOIN plates p ON m.plate_id = p.plate_id
        JOIN experiments e ON p.experiment_id = e.experiment_id
        LEFT JOIN wells w ON m.plate_id = w.plate_id 
          AND m.strain = w.strain 
          AND m.antibiotic = w.antibiotic 
          AND m.media = w.media 
          AND m.replicate = w.replicate
    """
    
    # GROUP BY needed because we joined with wells (one row per group)
    query += " GROUP BY m.mic_result_id"
    
    where_clauses = ["p.is_deleted = 0"]
    params = []
    
    if "All" not in f_strain and f_strain:
        where_clauses.append(f"m.strain IN ({','.join(['?']*len(f_strain))})")
        params.extend(f_strain)
    if "All" not in f_ab and f_ab:
        where_clauses.append(f"m.antibiotic IN ({','.join(['?']*len(f_ab))})")
        params.extend(f_ab)
        
    for field, val in st.session_state.search_extra_filters.items():
        if val:
            if field in mic_fields: where_clauses.append(f"m.{field} LIKE ?"); params.append(f"%{val}%")
            elif field in plate_fields: where_clauses.append(f"p.{field} LIKE ?"); params.append(f"%{val}%")
            elif field in exp_fields: where_clauses.append(f"e.{field} LIKE ?"); params.append(f"%{val}%")
            elif field in custom_label_list:
                where_clauses.append(f"json_extract(w.extra_labels_json, '$.{field}') LIKE ?")
                params.append(f"%{val}%")
                
    full_query = query.replace("GROUP BY", f"WHERE {' AND '.join(where_clauses)} GROUP BY")
    
    try:
        df_search = pd.read_sql_query(full_query, conn, params=params)
        conn.close()
        
        if not df_search.empty:
            # Add Navigation Column
            st.divider()
            st.subheader(f"Results ({len(df_search)} groups found)")
            
            # Show strictly requested columns + Navigation
            final_df = df_search[display_cols].copy()
            st.dataframe(final_df, width="stretch")
            
            # Row selection for navigation
            nav_col1, nav_col2 = st.columns([3, 1])
            target_plate = nav_col1.selectbox("Select a result to open in Editor", 
                                             options=df_search.index,
                                             format_func=lambda i: f"{df_search.iloc[i]['date']} - {df_search.iloc[i]['plate_name']} ({df_search.iloc[i]['strain']})")
            
            if nav_col2.button("🚀 Open in Library"):
                st.session_state.selected_search_plate_id = df_search.iloc[target_plate]['plate_id']
                st.session_state.nav_mode = "Plate Library"
                st.rerun()
                
        else:
            st.warning("No results found for these filters.")
            conn.close()
            
    except Exception as e:
        st.error(f"Search failed: {e}")
        conn.close()

elif mode == "Visualization":
    st.header("Generate Visualization")
    conn = get_connection()
    
    # Fetch all relevant MIC results joined with ALL metadata and custom labels
    # We join mic_results (m) with plates (p), experiments (e), and pick first well's labels (w)
    query = """
        SELECT m.*, p.*, e.*, e.notes as exp_notes, w.extra_labels_json
        FROM mic_results m
        JOIN plates p ON m.plate_id = p.plate_id
        JOIN experiments e ON p.experiment_id = e.experiment_id
        LEFT JOIN wells w ON m.plate_id = w.plate_id 
          AND m.strain = w.strain 
          AND m.antibiotic = w.antibiotic 
          AND m.media = w.media 
          AND m.replicate = w.replicate
        WHERE p.is_deleted = 0
        GROUP BY m.mic_result_id
    """
    df_all = pd.read_sql_query(query, conn)
    conn.close()
    
    if df_all.empty:
        st.info("No data available for visualization. Save some experiments first!")
    else:
        # Expand Custom Labels from JSON
        custom_label_keys = set()
        if 'extra_labels_json' in df_all.columns:
            def expand_labels(row):
                if row['extra_labels_json']:
                    try:
                        labels = json.loads(row['extra_labels_json'])
                        for k, v in labels.items():
                            row[f"label_{k}"] = v
                            custom_label_keys.add(k)
                    except: pass
                return row
            df_all = df_all.apply(expand_labels, axis=1)
            
        # Dynamic discovery of categorical/grouping columns
        exclude_cols = [
            'mic_result_id', 'plate_id', 'experiment_id', 'group_id', 
            'mic_value', 'lowest_tested_conc', 'highest_tested_conc', 
            'concentration_values_json', 'num_points', 'is_deleted', 
            'is_locked', 'is_checked', 'extra_labels_json', 'notes', 'exp_notes'
        ]
        
        all_cols = df_all.columns.tolist()
        groupable_cols = [c for c in all_cols if c not in exclude_cols]
        
        # Friendly names for categories
        standard_cols = sorted(list(set(groupable_cols)))
        
        st.subheader("1. Select Data (Filters)")
        
        # Initialize extra filters in session state
        if 'viz_extra_filters' not in st.session_state:
            st.session_state.viz_extra_filters = []
            
        # Define available fields
        standard_cols = ['strain', 'antibiotic', 'media', 'replicate', 'plate_name', 'date', 'person', 'reader']
        
        # 1a. Default Filters (Strain and Antibiotic)
        current_filters = {}
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            all_strains = sorted(df_all['strain'].unique().tolist())
            current_filters['strain'] = st.multiselect("Filter Strains", options=all_strains, default=all_strains, key="viz_f_strain")
        with col_f2:
            all_abs = sorted(df_all['antibiotic'].unique().tolist())
            current_filters['antibiotic'] = st.multiselect("Filter Antibiotics", options=all_abs, default=all_abs, key="viz_f_ab")
            
        # 1b. Add Extra Filter Dropdown
        remaining_fields = [f for f in standard_cols if f not in ['strain', 'antibiotic'] and f not in st.session_state.viz_extra_filters]
        if remaining_fields:
            new_f = st.selectbox("➕ Add another filter for...", ["-- Select --"] + remaining_fields, key="viz_add_f_select")
            if new_f != "-- Select --":
                st.session_state.viz_extra_filters.append(new_f)
                st.rerun()
                
        # 1c. Render Extra Filters
        to_delete = []
        for field in st.session_state.viz_extra_filters:
            col_ef1, col_ef2 = st.columns([4, 1])
            if field in df_all.columns:
                unique_vals = sorted(df_all[field].unique().tolist())
                current_filters[field] = col_ef1.multiselect(
                    f"Filter {field.replace('_', ' ').title()}", 
                    options=unique_vals, 
                    default=unique_vals,
                    key=f"viz_filter_{field}"
                )
            if col_ef2.button("✖", key=f"viz_del_{field}"):
                to_delete.append(field)
        
        for field in to_delete:
            st.session_state.viz_extra_filters.remove(field)
            st.rerun()
            
        # Apply filters dynamically
        df_filtered = df_all.copy()
        for field, selected in current_filters.items():
            if selected:
                df_filtered = df_filtered[df_filtered[field].isin(selected)]
        
        if df_filtered.empty:
            st.warning("No data matches the selected filters.")
        else:
            st.subheader("2. Dot Plot Settings (Grouping)")
            
            # Identify possible grouping columns
            # standard_cols = ['strain', 'antibiotic', 'media', 'replicate', 'plate_name', 'date', 'person', 'reader'] # This was moved up
            
            v_col1, v_col2, v_col3 = st.columns(3)
            with v_col1:
                group_by = st.multiselect(
                    "Group by (select in order)", 
                    options=standard_cols,
                    default=['antibiotic', 'strain'],
                    key="viz_group_by"
                )
            
            with v_col2:
                color_by = st.selectbox(
                    "Color by",
                    options=[None] + standard_cols,
                    index=standard_cols.index('strain') + 1 if 'strain' in standard_cols else 0,
                    key="viz_color_by"
                )

            with v_col3:
                shape_by = st.selectbox(
                    "Shape by",
                    options=[None] + standard_cols,
                    index=0,
                    key="viz_shape_by"
                )
                
            if st.button("Generate Dot Plot", type="primary"):
                # Capturing ALL filtered orders to ensure visual alignment
                cat_orders = {field: selected for field, selected in current_filters.items() if selected}
                
                fig = plot_mic_dot_plot(df_filtered, group_by, color_by, symbol_col=shape_by, category_orders=cat_orders)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.error("Could not generate plot with selected data.")

# --- GLOBAL RESULTS DISPLAY ---
if 'wells' in st.session_state and st.session_state.wells:
    st.divider()
    st.header("Analysis Results")
    colA, colB = st.columns(2)
    with colA: st.plotly_chart(plot_plate_heatmap(st.session_state.wells, value_field="od_raw", title="Raw OD Heatmap"), width="stretch")
    with colB: st.plotly_chart(plot_growth_map(st.session_state.wells, title="Growth/No-Growth Map"), width="stretch")
    
    if st.session_state.get('mic_results'):
        df_mic = pd.DataFrame([m.model_dump() for m in st.session_state.mic_results])
        st.dataframe(df_mic[["strain", "antibiotic", "media", "mic_operator", "mic_value", "mic_unit", "replicate"]], width="stretch")

# INTEGRATED EDITOR IN LIBRARY
if mode == "Plate Library" and st.session_state.get('loaded_successfully'):
    st.divider()
    
    # Soft Delete Option
    with st.expander("🗑️ Danger Zone: Soft Delete Plate", expanded=False):
        st.warning("This will hide the plate from the library and search results, but keep it in the database.")
        is_locked = st.session_state.loaded_metadata.get('is_locked', 0)
        pwd_input = st.text_input("Enter Admin Password to Delete", type="password", key="delete_pwd_input", disabled=bool(is_locked))
        if st.button("Confirm Soft Delete", type="primary", key="confirm_delete_btn", disabled=bool(is_locked)):
            admin_pwd = get_admin_password()
            if admin_pwd and pwd_input == admin_pwd:
                try:
                    conn = get_connection()
                    conn.execute("UPDATE plates SET is_deleted = 1 WHERE plate_id = ?", (selected_pid,))
                    if hasattr(conn, "commit"): conn.commit()
                    conn.close()
                    st.success(f"Plate '{st.session_state.loaded_metadata.get('plate_name')}' soft-deleted successfully.")
                    # Clear session state
                    st.session_state.loaded_successfully = False
                    st.session_state.wells = []
                    st.session_state.mic_results = []
                    st.rerun()
                except Exception as e:
                    st.error(f"Delete failed: {e}")
            else:
                st.error("Invalid password.")

    st.divider()
    
    # Plate Lock and Check Toggles
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        is_locked = bool(st.session_state.loaded_metadata.get('is_locked', 0))
        new_lock_state = st.checkbox("🔒 Locked from Deletion", value=is_locked, key="plate_lock_checkbox")
        if new_lock_state != is_locked:
            try:
                conn = get_connection()
                conn.execute("UPDATE plates SET is_locked = ? WHERE plate_id = ?", (1 if new_lock_state else 0, selected_pid))
                if hasattr(conn, "commit"): conn.commit()
                conn.close()
                st.session_state.loaded_metadata['is_locked'] = 1 if new_lock_state else 0
                if new_lock_state:
                    st.session_state.lib_edit_mode = False
                st.rerun()
            except Exception as e:
                st.error(f"Failed to update lock state: {e}")
                
    with col_t2:
        is_checked = bool(st.session_state.loaded_metadata.get('is_checked', 0))
        new_check_state = st.checkbox("✅ MIC manually checked", value=is_checked, key="plate_check_checkbox")
        if new_check_state != is_checked:
            try:
                conn = get_connection()
                conn.execute("UPDATE plates SET is_checked = ? WHERE plate_id = ?", (1 if new_check_state else 0, selected_pid))
                if hasattr(conn, "commit"): conn.commit()
                conn.close()
                st.session_state.loaded_metadata['is_checked'] = 1 if new_check_state else 0
                st.rerun()
            except Exception as e:
                st.error(f"Failed to update checked state: {e}")

    # Toggle Lock/Unlock for Editing (UI Session State)
    if not st.session_state.get('lib_edit_mode'):
        st.info("💡 Data is currently **locked** (View Only). Click the button below to edit.")
        
        if st.button("🔓 Unlock Data & Layout for Editing"):
            st.session_state.lib_edit_mode = True
            st.rerun()
    else:
        st.warning("⚠️ Data is currently **unlocked**. Be careful when making changes.")
        if st.button("🔒 Lock Data (View Only)"):
            st.session_state.lib_edit_mode = False
            st.rerun()
            
    st.subheader("Plate Details & Layout")
    render_editor_and_logic("lib", 
                            metadata_defaults=st.session_state.get('loaded_metadata'),
                            editable=st.session_state.get('lib_edit_mode', False))
