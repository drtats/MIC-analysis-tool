import pandas as pd
import io
from typing import List, Optional

def parse_8x12_matrix(text: str) -> List[List[str]]:
    """
    Parses a pasted string into an 8x12 matrix.
    Handles tab, space, or comma delimiters.
    """
    # Clean up the text: replace commas with tabs to handle CSV-like paste
    # But usually Excel/Plate reader paste is tab-separated.
    lines = text.strip().splitlines()
    matrix = []
    for line in lines:
        if not line.strip():
            continue
        # Split by tabs first, then spaces if multiple
        row = re.split(r'\t| +', line.strip())
        if len(row) > 0:
            matrix.append(row)
    
    if len(matrix) != 8:
        raise ValueError(f"Expected 8 rows, found {len(matrix)}")
    
    for i, row in enumerate(matrix):
        if len(row) != 12:
             raise ValueError(f"Row {i+1} has {len(row)} columns, expected 12")
             
    return matrix

import re # needed inside parse_8x12_matrix

def matrix_to_long_format(matrix: List[List[float]], plate_id: str) -> List[dict]:
    """Converts 8x12 float matrix to long-format well dicts."""
    from plate_layout import get_well_position
    wells = []
    for r in range(8):
        for c in range(12):
            wells.append({
                "plate_id": plate_id,
                "well_position": get_well_position(r, c),
                "row": r,
                "column": c,
                "od_raw": float(matrix[r][c])
            })
    return wells

def parse_labels_text(text: str) -> List[List[str]]:
    """Identical to parse_8x12_matrix but returns strings."""
    return parse_8x12_matrix(text)
