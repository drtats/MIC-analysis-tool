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

def plot_mic_dot_plot(df: pd.DataFrame, group_cols: List[str], color_col: Optional[str] = None, symbol_col: Optional[str] = None, category_orders: Optional[Dict[str, List]] = None):
    """
    Generates a dot plot (strip plot) for MIC values across different conditions.
    df: DataFrame containing MIC results.
    group_cols: List of column names to used for grouping on the X-axis.
    color_col: Column name to use for coloring indices.
    symbol_col: Column name to use for symbol/shape.
    category_orders: Dictionary mapping column names to a specific order of categories.
    """
    if df.empty:
        return None
        
    # Copy and prepare data
    plot_df = df.copy()
    
    # Define high-visibility symbol sequence
    symbols = ['circle', 'square', 'diamond', 'cross', 'x', 'triangle-up', 'star', 'hexagon']
    
    # Generate evenly spaced colors from a rainbow scale (Turbo) if color_col is used
    color_seq = px.colors.qualitative.Prism # Fallback
    if color_col and color_col in plot_df.columns:
        n_colors = len(plot_df[color_col].unique())
        if n_colors > 1:
            color_offsets = [i / (n_colors - 1) for i in range(n_colors)]
            color_seq = px.colors.sample_colorscale("turbo", color_offsets)
        elif n_colors == 1:
            color_seq = px.colors.sample_colorscale("turbo", [0.5])

    # Create a combined grouping label for the X-axis to handle ordering and jittering
    if group_cols:
        # Sort the dataframe according to the desired category orders before combining
        sort_cols = []
        for col in group_cols:
            if category_orders and col in category_orders:
                # To sort by a specific list, we can use Categorical mapping
                plot_df[col] = pd.Categorical(plot_df[col], categories=category_orders[col], ordered=True)
                sort_cols.append(col)
        
        if sort_cols:
            plot_df = plot_df.sort_values(by=sort_cols)
            
        plot_df['Group'] = plot_df[group_cols].astype(str).agg(' | '.join, axis=1)
    else:
        plot_df['Group'] = 'All Data'
        
    # Manual Jittering for px.scatter (since px.strip doesn't support 'symbol')
    unique_groups = plot_df['Group'].unique().tolist()
    group_map = {group: i for i, group in enumerate(unique_groups)}
    plot_df['Group_Index'] = plot_df['Group'].map(group_map)
    # Add random jitter offset
    np.random.seed(42) # Consistent jitter for reruns
    plot_df['Group_Jittered'] = plot_df['Group_Index'] + np.random.uniform(-0.25, 0.25, size=len(plot_df))
    
    # Create the scatter plot
    fig = px.scatter(
        plot_df,
        x='Group_Jittered',
        y='mic_value',
        color=color_col,
        symbol=symbol_col,
        symbol_sequence=symbols,
        hover_data=group_cols + (['mic_operator', 'mic_unit'] if 'mic_operator' in plot_df.columns else []),
        title="MIC Distribution by Group",
        labels={'Group_Jittered': ' / '.join(group_cols) if group_cols else 'Global', 'mic_value': 'MIC Value'},
        color_discrete_sequence=color_seq,
        category_orders=category_orders
    )
    
    # Set high-visibility marker style
    fig.update_traces(marker=dict(size=12, opacity=0.9, line=dict(width=1, color='DarkSlateGrey')))
    
    # Update X-axis to show category labels instead of numeric indices
    fig.update_layout(
        xaxis=dict(
            tickmode='array',
            tickvals=list(range(len(unique_groups))),
            ticktext=unique_groups,
            title=' / '.join(group_cols) if group_cols else ''
        ),
        yaxis=dict(
            type='log',
            dtick=math.log10(2),
            tickmode='array',
            # Generate common MIC values for ticks
            tickvals=[2**i for i in range(-10, 15)],
            ticktext=[str(2**i) if 2**i >= 1 else f"1/{2**-i}" for i in range(-10, 15)]
        )
    )
    
    return fig
