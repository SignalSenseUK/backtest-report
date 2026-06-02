"""Position heatmap section renderer."""
from __future__ import annotations

import logging

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from backtest_report.models import BacktestData, BacktestMeta, SectionOutput
from backtest_report.portfolio import apply_report_style, fig_to_base64

matplotlib.use("Agg")

logger = logging.getLogger("backtest_report")

POSITIVE_COLOR = "#10b981"
NEGATIVE_COLOR = "#ef4444"
NEUTRAL_COLOR = "#6b7280"


def render_position_snapshot(data: BacktestData, meta: BacktestMeta) -> SectionOutput:
    """Render time × instrument position heatmap with diverging colourmap.

    Samples positions at monthly or weekly frequency (auto-detect based on date range).
    Instruments sorted by average absolute position (most active at top).

    Returns SectionOutput with:
        - section_id: "position_snapshot"
        - figures: {"heatmap": base64_png}
        - html: div with img tag
    """
    apply_report_style()

    if data.positions.empty:
        html = '<div class="br-heatmap"><p class="br-muted">No position data available.</p></div>'
        return SectionOutput(section_id="position_snapshot", html=html, figures={})

    # Determine sampling frequency based on date range
    date_range_days = (data.positions.index[-1] - data.positions.index[0]).days
    if date_range_days > 365 * 2:
        freq = "ME"  # Monthly for > 2 years
    else:
        freq = "W"  # Weekly for shorter periods

    # Resample positions
    try:
        positions_resampled = data.positions.resample(freq).last()
    except Exception:
        positions_resampled = data.positions.iloc[::5]

    # Sort instruments by average absolute position (most active at top)
    avg_abs = positions_resampled.abs().mean().sort_values(ascending=False)
    sorted_instruments = avg_abs.index.tolist()
    positions_sorted = positions_resampled[sorted_instruments]

    # Transpose so instruments are rows (y-axis), dates are columns (x-axis)
    matrix = positions_sorted.T

    fig, ax = plt.subplots(figsize=(12, max(3, len(sorted_instruments) * 0.3)))

    # Diverging colormap: red for short, blue for long (RdBu)
    vmax = max(abs(matrix.values.max()), abs(matrix.values.min()))
    vmax = max(vmax, 1.0)  # minimum range of 1 contract

    im = ax.imshow(
        matrix.values,
        aspect="auto",
        cmap="RdBu",
        vmin=-vmax,
        vmax=vmax,
    )

    # Colour bar
    cbar = plt.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    cbar.set_label("Position (contracts)", fontsize=7)
    cbar.ax.tick_params(labelsize=6)

    # Labels
    ax.set_yticks(range(len(sorted_instruments)))
    ax.set_yticklabels(sorted_instruments, fontsize=7)
    ax.set_xticks(range(0, len(matrix.columns), max(1, len(matrix.columns) // 8)))
    date_labels = [matrix.columns[i].strftime("%Y-%m") for i in ax.get_xticks()]
    ax.set_xticklabels(date_labels, rotation=45, ha="right", fontsize=6)
    ax.set_title("Position Snapshot — Diverging Colour Scale (Long=Blue, Short=Red)", fontsize=8)
    plt.tight_layout()

    fig_base64 = fig_to_base64(fig)

    html = (
        '<div class="br-heatmap">'
        f'<img src="data:image/png;base64,{fig_base64}" '
        f'alt="Position Snapshot" style="width:100%;" />'
        "</div>"
    )

    return SectionOutput(
        section_id="position_snapshot",
        html=html,
        figures={"heatmap": fig_base64},
    )