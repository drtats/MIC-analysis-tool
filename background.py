from typing import List
from models import WellData

def calculate_background(wells: List[WellData]) -> float:
    """Calculates the background value from blank wells (average)."""
    blank_ods = [w.od_raw for w in wells if w.is_blank]
    if not blank_ods:
        return 0.0
    return sum(blank_ods) / len(blank_ods)

def subtract_background(wells: List[WellData], background_val: float):
    """Subtracts background value from each well's raw OD."""
    for well in wells:
        well.od_bg_subtracted = max(0.0, well.od_raw - background_val)

def apply_threshold(wells: List[WellData], threshold: float):
    """Determines growth/no-growth based on threshold."""
    for well in wells:
        if well.od_bg_subtracted is not None:
            well.growth_call = well.od_bg_subtracted >= threshold
