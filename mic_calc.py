import json
from typing import List, Dict, Optional
from models import WellData, MICResult

def calculate_mic_for_group(group_wells: List[WellData]) -> MICResult:
    """
    Calculates MIC for a single replicate group.
    Assumes wells are already background-subtracted and growth_called.
    Aggregates wells with duplicate concentrations within the group.
    """
    if not group_wells:
        raise ValueError("Empty well group")

    # Filter out wells with missing growth call (e.g. blanks)
    valid_wells = [w for w in group_wells if w.growth_call is not None and w.concentration is not None]
    if not valid_wells:
        raise ValueError("No valid wells with growth results and concentrations")

    # Aggregate by concentration (If any well at this conc has growth, the row has growth)
    conc_map = {} # concentration -> bool (any growth)
    for w in valid_wells:
        c = w.concentration
        if c not in conc_map:
            conc_map[c] = False
        if w.growth_call == True:
            conc_map[c] = True
    
    unique_concs = sorted(conc_map.keys())
    growth_calls = [conc_map[c] for c in unique_concs]
    
    lowest_conc = unique_concs[0]
    highest_conc = unique_concs[-1]

    mic_value = None
    mic_operator = "="
    warning = None

    # MIC logic: lowest concentration with growth_call == False
    first_no_growth_idx = -1
    for i, growth in enumerate(growth_calls):
        if not growth:
            first_no_growth_idx = i
            break
    
    if first_no_growth_idx == -1:
        # All wells show growth
        mic_value = highest_conc
        mic_operator = ">"
    else:
        mic_value = unique_concs[first_no_growth_idx]
        if first_no_growth_idx == 0:
            mic_operator = "<="
        
        # Check for growth at any concentration HIGHER than the first no-growth
        for i in range(first_no_growth_idx + 1, len(growth_calls)):
            if growth_calls[i]:
                warning = f"Growth bounce detected at {unique_concs[i]} after no-growth at {mic_value}"

    # Metadata for the first well in group to fill MICResult fields
    ref = valid_wells[0]
    
    return MICResult(
        plate_id=ref.plate_id,
        group_id=f"{ref.strain}_{ref.antibiotic}_{ref.media}_{ref.replicate}",
        strain=ref.strain or "Unknown",
        antibiotic=ref.antibiotic or "Unknown",
        media=ref.media or "Unknown",
        replicate=ref.replicate or 1,
        mic_value=mic_value,
        mic_operator=mic_operator,
        mic_unit=ref.concentration_unit,
        threshold_used=0.0,
        lowest_tested_conc=lowest_conc,
        highest_tested_conc=highest_conc,
        concentration_values_json=json.dumps(unique_concs),
        num_points=len(valid_wells),
        warning=warning
    )

def group_and_calculate_mics(wells: List[WellData]) -> List[MICResult]:
    """Groups wells and calculates MIC for each replicate."""
    groups = {}
    for well in wells:
        if well.is_blank:
            continue
        
        # Normalize keys (strip whitespace, uniform case for comparison)
        s_norm = str(well.strain).strip() if well.strain else "Unknown"
        a_norm = str(well.antibiotic).strip() if well.antibiotic else "Unknown"
        m_norm = str(well.media).strip() if well.media else "Unknown"
        r_norm = int(well.replicate) if well.replicate is not None else 1
        
        key = (s_norm, a_norm, m_norm, r_norm)
        if key not in groups:
            groups[key] = []
        
        # Ensure the well itself has normalized data
        well.strain = s_norm
        well.antibiotic = a_norm
        well.media = m_norm
        well.replicate = r_norm
        
        groups[key].append(well)
    
    results = []
    for key, group_wells in groups.items():
        try:
            mic_res = calculate_mic_for_group(group_wells)
            results.append(mic_res)
        except Exception:
            pass
            
    return results
