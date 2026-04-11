"""
plotly_fig.py — Plotly figure builder for guitar FR scope.

Replaces the Chart.js chart_cur/chart_ref state approach with a proper
go.Figure pushed via trame-plotly widget.
"""
import numpy as np
import plotly.graph_objects as go

DARK_BG    = "#f8f8f6"
GRID_COLOR = "#e8e8e4"
AXIS_COLOR = "#aaaaaa"
PAPER_BG   = "#f8f8f6"

TRACE_COLORS = {
    "electronics": "#1a5fa8",    # blue
    "ref_open":    "#aaaaaa",    # light grey dashed
    "audio":       "#2a7a3a",    # green dashed
    "audio_ref":   "#b07820",    # amber dashed
}


def make_fr_figure(freqs, cur_db, ref_db=None, audio_db=None, audio_ref_db=None,
                   height=None):
    """
    Build a Plotly go.Figure for the frequency response scope.

    Parameters
    ----------
    freqs      : list[float]  — frequency axis (Hz)
    cur_db     : list[float]  — current electronics FR (dB, normalised)
    ref_db     : list[float] | None — reference electronics FR
    audio_db   : list[float] | None — audio FR from last pluck
    audio_ref_db: list[float] | None — frozen audio reference
    height     : int | None   — figure height in px (None = auto)
    """
    fig = go.Figure()

    # Convert to numpy for safe handling
    f = np.array(freqs)
    log_f = np.log10(f)

    def _add(y_data, name, color, dash="solid", width=2, opacity=1.0):
        if y_data is None:
            return
        y = np.array(y_data)
        # clip to reasonable dB range
        y = np.clip(y, -50, 6)
        fig.add_trace(go.Scatter(
            x=list(f),
            y=list(y),
            name=name,
            mode="lines",
            line=dict(color=color, width=width, dash=dash),
            opacity=opacity,
            hovertemplate="%{x:.0f} Hz<br>%{y:.1f} dB<extra></extra>",
        ))

    _add(ref_db,       "ref (open)",  TRACE_COLORS["ref_open"],  dash="dot",   width=1.5, opacity=0.7)
    _add(audio_ref_db, "audio ref",   TRACE_COLORS["audio_ref"], dash="dash",  width=1.5, opacity=0.8)
    _add(audio_db,     "audio FR",    TRACE_COLORS["audio"],     dash="dash",  width=2,   opacity=0.9)
    _add(cur_db,       "electronics", TRACE_COLORS["electronics"],dash="solid", width=2.5)

    # Tick values and labels for log x-axis
    tickvals = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
    ticktext = ["50", "100", "200", "500", "1k", "2k", "5k", "10k", "20k"]

    layout_args = dict(
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=DARK_BG,
        font=dict(family="system-ui", size=11, color="#444444"),
        margin=dict(l=50, r=16, t=16, b=40),
        legend=dict(
            orientation="h",
            yanchor="top", y=1.0,
            xanchor="left", x=0.0,
            font=dict(size=10, color="#555"),
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(
            type="log",
            range=[np.log10(50), np.log10(20000)],
            tickvals=tickvals,
            ticktext=ticktext,
            title=dict(text="frequency (Hz)", font=dict(size=11, color="#666")),
            gridcolor=GRID_COLOR,
            zerolinecolor=GRID_COLOR,
            linecolor=AXIS_COLOR,
            tickcolor=AXIS_COLOR,
            tickfont=dict(color="#666", size=10),
        ),
        yaxis=dict(
            range=[-46, 4],
            title=dict(text="level (dB)", font=dict(size=11, color="#666")),
            gridcolor=GRID_COLOR,
            zerolinecolor="#cccccc",
            linecolor=AXIS_COLOR,
            tickcolor=AXIS_COLOR,
            tickfont=dict(color="#666", size=10),
            dtick=10,
        ),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#ffffff", font=dict(color="#333", size=11)),
    )
    if height:
        layout_args["height"] = height

    fig.update_layout(**layout_args)
    return fig
