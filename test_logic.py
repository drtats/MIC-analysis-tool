import numpy as np
import pandas as pd
from parser import parse_8x12_matrix, matrix_to_long_format
from background import calculate_background, subtract_background, apply_threshold
from mic_calc import group_and_calculate_mics
from models import WellData

def test_mic_logic():
    print("Testing MIC Calculation Logic...")
    
    # Simulate a plate with 1 strain, 1 antibiotic, 2 replicates
    # Column 1: Rep 1, Column 2: Rep 2
    # Concentrations: 0.25, 0.5, 1, 2, 4, 8, 16, 32
    
    wells = []
    pid = "test-plate"
    
    for r in range(8):
        # Rep 1 (Col 0)
        wells.append(WellData(
            plate_id=pid, well_position=f"{chr(ord('A')+r)}1", row=r, column=0,
            od_raw=0.5 if r < 4 else 0.005, # Growth at 0.25, 0.5, 1, 2. No growth at 4, 8, 16, 32.
            strain="S1", antibiotic="A1", concentration=2**r * 0.25, replicate=1
        ))
        # Rep 2 (Col 1)
        wells.append(WellData(
            plate_id=pid, well_position=f"{chr(ord('A')+r)}2", row=r, column=1,
            od_raw=0.5 if r < 2 else 0.005, # Growth at 0.25, 0.5. No growth at 1, 2, 4, 8, 16, 32.
            strain="S1", antibiotic="A1", concentration=2**r * 0.25, replicate=2
        ))
        
    # Blank well (H12)
    wells.append(WellData(
        plate_id=pid, well_position="H12", row=7, column=11,
        od_raw=0.005, is_blank=True
    ))
    
    # 1. Background
    bg = calculate_background(wells)
    print(f"Calculated Background: {bg}")
    subtract_background(wells, bg)
    
    # 2. Threshold
    threshold = 0.010
    apply_threshold(wells, threshold)
    
    # 3. MIC
    results = group_and_calculate_mics(wells)
    
    for res in results:
        print(f"Rep {res.replicate}: MIC {res.mic_operator} {res.mic_value}")
        
    # Expected: 
    # Rep 1: MIC 4.0 (r=4 is the first no-growth)
    # Rep 2: MIC 1.0 (r=2 is the first no-growth)
    
    assert results[0].mic_value == 4.0
    assert results[1].mic_value == 1.0
    print("Test Passed!")

if __name__ == "__main__":
    test_mic_logic()
