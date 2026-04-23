"""Position heatmap and attribution section renderers."""
from __future__ import annotations

import logging
from math import sqrt

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

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
        freq = "M"  # Monthly for > 2 years
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
        f'<img src="data:image/png;base64,{fig_base64}" alt="Position Snapshot" style="width:100%;" />'
        "</div>"
    )

    return SectionOutput(
        section_id="position_snapshot",
        html=html,
        figures={"heatmap": fig_base64},
    )


def render_attribution(data: BacktestData, meta: BacktestMeta) -> SectionOutput:
    """Render return attribution by instrument and by sector.

    - By-instrument: monthly P&L contribution per instrument, top 10 + "Other"
    - By-sector: stacked bars per month using instrument_meta.sector groupings

    Returns SectionOutput with:
        - section_id: "attribution"
        - figures: {"by_instrument": base64_png, "by_sector": base64_png}
        - html: div with img tags
    """
    apply_report_style()

    figures = {}
    html_parts = []

    # ── By-instrument attribution ───────────────────────────────────────────
    if not data.instrument_pnl.empty:
        # Monthly instrument PnL
        monthly_pnl = data.instrument_pnl.resample("M").sum()

        # Sum across instruments to get total monthly
        total_monthly = monthly_pnl.sum(axis=1)

        # For each instrument, fraction of total monthly PnL
        # Show top 10 instruments by cumulative PnL
        cum_pnl = data.instrument_pnl.sum().sort_values(ascending=False)
        top_instruments = cum_pnl.head(10).index.tolist()

        n = len(monthly_pnl)
        bottom = np.zeros(n)

        fig_attr, ax_attr = plt.subplots(figsize=(12, 4))
        colors = plt.cm.tab10.colors

        for i, instr in enumerate(top_instruments):
            vals = monthly_pnl[instr].values
            ax_attr.bar(
                range(n),
                vals,
                bottom=bottom,
                label=instr,
                color=colors[i % 10],
                width=0.8,
            )
            bottom += vals

        # "Other" category
        other_instr = [c for c in monthly_pnl.columns if c not in top_instruments]
        if other_instr:
            other_vals = monthly_pnl[other_instr].sum(axis=1).values
            ax_attr.bar(range(n), other_vals, bottom=bottom, label="Other", color="#cccccc", width=0.8)
            bottom += other_vals

        # Overlay total line
        ax_attr.plot(range(n), total_monthly.values, color="black", linewidth=1.5, label="Total", linestyle="--")

        ax_attr.set_xticks(range(0, n, max(1, n // 12)))
        date_labels = [monthly_pnl.index[i].strftime("%Y-%m") for i in ax_attr.get_xticks()]
        ax_attr.set_xticklabels(date_labels, rotation=45, ha="right", fontsize=6)
        ax_attr.tick_params(axis="y", labelsize=7)
        ax_attr.set_title("Return Attribution by Instrument (Monthly)", fontsize=8)
        ax_attr.legend(fontsize=6, ncol=min(6, len(top_instruments) + 2), loc="upper left")
        ax_attr.axhline(y=0, color="black", linewidth=0.5)
        plt.tight_layout()

        instr_base64 = fig_to_base64(fig_attr)
        figures["by_instrument"] = instr_base64
        html_parts.append(
            f'<figure class="br-figure">'
            f'<img src="data:image/png;base64,{instr_base64}" alt="Attribution by Instrument" style="width:100%;" />'
            f'<figcaption class="br-figure-caption">Return attribution by instrument (top 10 + Other)</figcaption>'
            f"</figure>"
        )

    # ── By-sector attribution ───────────────────────────────────────────────
    if not data.instrument_pnl.empty and data.instrument_meta:
        # Get sector for each instrument
        sector_map = {}
        for code in data.instrument_pnl.columns:
            meta_info = data.instrument_meta.get(code)
            if meta_info and meta_info.sector:
                sector_map[code] = meta_info.sector
            else:
                sector_map[code] = "Unknown"

        monthly_pnl = data.instrument_pnl.resample("M").sum()

        # Group by sector
        sector_pnl = {}
        for code, sector in sector_map.items():
            if sector not in sector_pnl:
                sector_pnl[sector] = monthly_pnl[code]
            else:
                sector_pnl[sector] = sector_pnl[sector] + monthly_pnl[code]

        if sector_pnl:
            sector_df = pd.DataFrame(sector_pnl)
            n = len(sector_df)

            fig_sect, ax_sect = plt.subplots(figsize=(12, 4))
            bottom = np.zeros(n)
            sector_colors = plt.cm.Set2.colors
            sectors = list(sector_df.columns)

            for i, sector in enumerate(sectors):
                vals = sector_df[sector].values
                ax_sect.bar(
                    range(n),
                    vals,
                    bottom=bottom,
                    label=sector,
                    color=sector_colors[i % len(sector_colors)],
                    width=0.8,
                )
                bottom += vals

            total_monthly = sector_df.sum(axis=1)
            ax_sect.plot(range(n), total_monthly.values, color="black", linewidth=1.5, linestyle="--")

            ax_sect.set_xticks(range(0, n, max(1, n // 12)))
            date_labels = [sector_df.index[i].strftime("%Y-%m") for i in ax_sect.get_xticks()]
            ax_sect.set_xticklabels(date_labels, rotation=45, ha="right", fontsize=6)
            ax_sect.tick_params(axis="y", labelsize=7)
            ax_sect.set_title("Return Attribution by Sector (Monthly)", fontsize=8)
            ax_sect.legend(fontsize=6, ncol=min(4, len(sectors)), loc="upper left")
            ax_sect.axhline(y=0, color="black", linewidth=0.5)
            plt.tight_layout()

            sect_base64 = fig_to_base64(fig_sect)
            figures["by_sector"] = sect_base64
            html_parts.append(
                f'<figure class="br-figure">'
                f'<img src="data:image/png;base64,{sect_base64}" alt="Attribution by Sector" style="width:100%;" />'
                f'<figcaption class="br-figure-caption">Return attribution by sector</figcaption>'
                f"</figure>"
            )

    if not figures:
        html = '<div class="br-attribution"><p class="br-muted">Attribution data not available.</p></div>'
    else:
        html = '<div class="br-attribution">' + "".join(html_parts) + "</div>"

    return SectionOutput(section_id="attribution", html=html, figures=figures)