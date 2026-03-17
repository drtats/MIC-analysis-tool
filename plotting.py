import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from typing import List, Optional
from models import WellData

def plot_plate_heatmap(wells: List[WellData], value_field: str = "od_raw", title: str = "Plate Heatmap"):
    """Generates a Plotly heatmap for the 96-well plate."""
    # Create 8x12 matrix
    data = np.zeros((8, 12))
    well_positions = []
    
    for well in wells:
        val = getattr(well, value_field)
        if val is None:
            val = 0.0
        data[well.row, well.column] = val
        
    rows = [chr(ord('A') + i) for i in range(8)]
    cols = [str(i + 1) for i in range(12)]
    
    fig = px.imshow(
        data,
        labels=dict(x="Column", y="Row", color="Value"),
        x=cols,
        y=rows,
        color_continuous_scale="Viridis",
        title=title,
        aspect="equal"
    )
    
    fig.update_xaxes(side="top")
    fig.update_traces(
        hovertemplate="Well: %{y}%{x}<br>Value: %{z}<extra></extra>"
    )
    
    return fig

def plot_growth_map(wells: List[WellData], title: str = "Growth/No-Growth Map"):
    """Generates a categorical heatmap for growth calls."""
    data = np.zeros((8, 12))
    for well in wells:
        if well.growth_call is True:
            data[well.row, well.column] = 1
        elif well.growth_call is False:
            data[well.row, well.column] = 0
        else:
            data[well.row, well.column] = -1 # N/A or Blank
            
    rows = [chr(ord('A') + i) for i in range(8)]
    cols = [str(i + 1) for i in range(12)]
    
    # Custom color scale: -1=Gray (Blank), 0=Blue (No Growth), 1=Red (Growth)
    fig = px.imshow(
        data,
        labels=dict(x="Column", y="Row", color="Growth"),
        x=cols,
        y=rows,
        color_continuous_scale=[[0, 'gray'], [0.5, 'blue'], [1, 'red']],
        title=title,
        aspect="equal",
        zmin=-1,
        zmax=1
    )
    
    fig.update_xaxes(side="top")
    fig.update_traces(
        hovertemplate="Well: %{y}%{x}<br>Growth: %{z}<extra></extra>"
    )
    
    return fig
