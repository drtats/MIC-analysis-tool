import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import math
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

def plot_mic_dot_plot(df: pd.DataFrame, group_cols: List[str], color_col: Optional[str] = None):
    """
    Generates a dot plot (strip plot) for MIC values across different conditions.
    df: DataFrame containing MIC results.
    group_cols: List of column names to used for grouping on the X-axis.
    color_col: Column name to use for coloring indices.
    """
    if df.empty:
        return None
        
    # Copy and prepare data
    plot_df = df.copy()
    
    # Create a combined grouping label for the X-axis
    if group_cols:
        plot_df['Group'] = plot_df[group_cols].astype(str).agg(' | '.join, axis=1)
    else:
        plot_df['Group'] = 'All Data'
        
    # Create the strip plot
    fig = px.strip(
        plot_df,
        x='Group',
        y='mic_value',
        color=color_col,
        hover_data=group_cols + (['mic_operator', 'mic_unit'] if 'mic_operator' in plot_df.columns else []),
        title="MIC Distribution by Group",
        labels={'Group': ' / '.join(group_cols) if group_cols else 'Global', 'mic_value': 'MIC Value'},
        stripmode='overlay'
    )
    
    # Update Y-axis to be log2 scaled for MICs
    fig.update_layout(
        yaxis=dict(
            type='log',
            dtick=math.log10(2),
            tickmode='array',
            # Generate common MIC values for ticks
            tickvals=[2**i for i in range(-10, 15)],
            ticktext=[str(2**i) if 2**i >= 1 else f"1/{2**-i}" for i in range(-10, 15)]
        )
    )
    
    fig.update_traces(marker=dict(size=10, opacity=0.7))
    
    return fig
