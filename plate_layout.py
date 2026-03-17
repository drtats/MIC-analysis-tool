import re

def get_well_position(row_idx: int, col_idx: int) -> str:
    """Converts 0-based row and column indices to well position string (e.g., A1, H12)."""
    row_char = chr(ord('A') + row_idx)
    col_str = str(col_idx + 1)
    return f"{row_char}{col_str}"

def parse_well_position(well_pos: str):
    """Parses well position string (e.g., A1) to 0-based row and column indices."""
    match = re.match(r"([A-H])(\d+)", well_pos.upper())
    if not match:
        raise ValueError(f"Invalid well position format: {well_pos}")
    row_char, col_str = match.groups()
    row_idx = ord(row_char) - ord('A')
    col_idx = int(col_str) - 1
    return row_idx, col_idx

def get_row_name(row_idx: int) -> str:
    """Returns row name (A-H) for a given index."""
    return chr(ord('A') + row_idx)

def get_96_well_list():
    """Returns a list of all well positions in a 96-well plate (A1 to H12)."""
    wells = []
    for r in range(8):
        for c in range(12):
            wells.append(get_well_position(r, c))
    return wells
