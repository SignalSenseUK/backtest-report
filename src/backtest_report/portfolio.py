"""Portfolio-level section renderers.

Each function: render_<section_id>(data: BacktestData, meta: BacktestMeta) -> SectionOutput.
All charts use matplotlib (not QuantStats built-in plots). QuantStats is only for metrics.
Charts are encoded as base64 PNG and returned in SectionOutput.figures.
"""
from __future__ import annotations

import logging
from io import BytesIO
from math import sqrt
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from backtest_report.models import BacktestData, BacktestMeta, SectionOutput

matplotlib.use("Agg")

logger = logging.getLogger("backtest_report")

# Chart colour constants
POSITIVE_COLOR = "#10b981"
NEGATIVE_COLOR = "#ef4444"
NEUTRAL_COLOR = "#6b7280"

# Figure dimensions
FIGURE_WIDTH = 10
FIGURE_HEIGHT = 4


def apply_report_style() -> None:
    """Apply consistent matplotlib style for all report charts."""
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.size": 8,
            "axes.grid": True,
            "grid.alpha": 0.3,
            "grid.color": "#9ca3af",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titlelocation": "left",
            "axes.titleweight": "600",
            "axes.titlepad": 10,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "legend.fontsize": 7,
            "legend.frameon": False,
        }
    )


def fig_to_base64(fig: plt.Figure) -> str:
    """Encode a matplotlib figure as a base64 PNG string."""
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    img_data = buf.getvalue()
    buf.close()
    plt.close(fig)
    import base64

    return base64.b64encode(img_data).decode("ascii")


def _format_pct(value: float) -> str:
    """Format a decimal value as percentage string."""
    return f"{value * 100:.2f}%"


def _format_date_axis(ax: plt.Axes) -> None:
    """Reformat x-axis to show year labels for readability."""
    ax.tick_params(axis="x", rotation=0)
    # Let matplotlib handle tick placement; just ensure labels are readable
    for label in ax.get_xticklabels():
        label.set_fontsize(7)


def render_portfolio_pnl(data: BacktestData, meta: BacktestMeta) -> SectionOutput:
    """Render equity curve and drawdown charts.

    Returns SectionOutput with:
        - section_id: "portfolio_pnl"
        - figures: {"equity_curve": base64_png, "drawdown": base64_png}
        - html: minimal div with img tags referencing the figures
    """
    apply_report_style()

    # Compute cumulative returns: growth of $1
    cumulative = (1 + data.portfolio_returns).cumprod()

    # Compute drawdown
    cummax = cumulative.cummax()
    drawdown = cumulative / cummax - 1

    # --- Equity Curve ---
    fig_equity, ax_equity = plt.subplots(figsize=(FIGURE_WIDTH, FIGURE_HEIGHT))
    ax_equity.plot(cumulative.index, cumulative.values, color=POSITIVE_COLOR, linewidth=1.0)
    ax_equity.axhline(y=1.0, color=NEUTRAL_COLOR, linestyle="--", linewidth=0.8, alpha=0.7)
    ax_equity.set_title("Cumulative Returns")
    ax_equity.set_ylabel("Growth of $1")
    ax_equity.set_xlabel("")
    _format_date_axis(ax_equity)
    equity_base64 = fig_to_base64(fig_equity)

    # --- Drawdown Chart ---
    fig_dd, ax_dd = plt.subplots(figsize=(FIGURE_WIDTH, FIGURE_HEIGHT))
    ax_dd.fill_between(
        drawdown.index, 0, drawdown.values, color=NEGATIVE_COLOR, alpha=0.7
    )
    ax_dd.axhline(y=0, color=NEUTRAL_COLOR, linestyle="-", linewidth=0.8)
    ax_dd.set_title("Underwater Plot (Drawdown)")
    ax_dd.set_ylabel("Drawdown %")
    ax_dd.set_xlabel("")
    ax_dd.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda x, _: f"{x * 100:.0f}%")
    )
    _format_date_axis(ax_dd)
    drawdown_base64 = fig_to_base64(fig_dd)

    html = (
        '<div class="br-portfolio-pnl">'
        f'<img src="data:image/png;base64,{equity_base64}" alt="Cumulative Returns" style="width:100%;" />'
        f'<img src="data:image/png;base64,{drawdown_base64}" alt="Drawdown" style="width:100%;" />'
        "</div>"
    )

    return SectionOutput(
        section_id="portfolio_pnl",
        html=html,
        figures={"equity_curve": equity_base64, "drawdown": drawdown_base64},
    )


def _return_to_color(value: float) -> str:
    """Map a return value to an rgba background-color string.

    Linearly interpolates between white and green (positive) or red (negative).
    Caps colour scaling at ±10%.
    """
    cap = 0.10
    clamped = max(-cap, min(cap, value))
    intensity = abs(clamped) / cap  # 0 → 1

    if value > 0:
        r = int(255 * (1 - intensity * 0.6))
        g = int(255 * (1 - intensity * 0.0))
        b = int(255 * (1 - intensity * 0.6))
        alpha = 0.3 + 0.5 * intensity
        return f"rgba({r},{g},{b},{alpha:.2f})"
    else:
        r = int(255 * (1 - intensity * 0.0))
        g = int(255 * (1 - intensity * 0.6))
        b = int(255 * (1 - intensity * 0.6))
        alpha = 0.3 + 0.5 * intensity
        return f"rgba({r},{g},{b},{alpha:.2f})"


def _format_return(value: float | None) -> str:
    """Format a return as a percentage string, handling None/NaN."""
    if value is None or pd.isna(value):
        return "—"
    return f"{value * 100:+.1f}%"


def render_monthly_returns(data: BacktestData, meta: BacktestMeta) -> SectionOutput:
    """Render monthly returns as a year × month heatmap table with conditional colouring.

    Resamples daily returns to monthly, pivots into year rows × month columns,
    adds an annual total column, and renders as an HTML table with background
    colour intensity reflecting return magnitude.

    Returns SectionOutput with:
        - section_id: "monthly_returns"
        - html: <table class="br-monthly-returns">...</table>
        - tables: {"monthly_returns": pivot_dataframe}
    """
    # Resample to monthly using month-end frequency
    monthly = data.portfolio_returns.resample("ME").apply(lambda x: (1 + x).prod() - 1)

    # Build year × month pivot table
    df = monthly.to_frame("return")
    df["year"] = df.index.year
    df["month"] = df.index.month
    pivot = df.pivot_table(index="year", columns="month", values="return", aggfunc="first")

    # Add annual total column (compound monthly returns for each year)
    pivot["Year"] = pivot.apply(lambda row: (1 + row.dropna()).prod() - 1, axis=1)

    # Identify best and worst months globally
    flat = pivot.drop(columns="Year").values.flatten()
    flat = flat[~pd.isna(flat)]
    best_month_val = flat.max() if len(flat) > 0 else None
    worst_month_val = flat.min() if len(flat) > 0 else None

    months = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    col_labels = months + ["Year"]

    # Build HTML table
    lines = [
        '<table class="br-monthly-returns">',
        "<thead><tr><th>Year</th>" + "".join(f"<th>{m}</th>" for m in col_labels) + "</tr></thead>",
        "<tbody>",
    ]

    for year, row in pivot.iterrows():
        cells = []
        for m in range(1, 13):
            val = row.get(m, None)
            colour = _return_to_color(val) if val is not None and not pd.isna(val) else "#f3f4f6"
            text = _format_return(val)
            is_best = val is not None and not pd.isna(val) and val == best_month_val
            is_worst = val is not None and not pd.isna(val) and val == worst_month_val
            style = f"background-color: {colour}"
            if is_best:
                style += "; font-weight: bold; border: 2px solid #10b981"
            elif is_worst:
                style += "; font-weight: bold; border: 2px solid #ef4444"
            cells.append(f'<td style="{style}">{text}</td>')

        # Year total cell
        year_val = row.get("Year", None)
        year_colour = _return_to_color(year_val) if year_val is not None and not pd.isna(year_val) else "#f3f4f6"
        year_text = _format_return(year_val)
        cells.append(f'<td style="background-color: {year_colour}; font-weight: 600">{year_text}</td>')

        lines.append(f"<tr><td class='br-year-label'>{year}</td>" + "".join(cells) + "</tr>")

    lines.extend(["</tbody>", "</table>"])

    html = "\n".join(lines)
    return SectionOutput(section_id="monthly_returns", html=html, tables={"monthly_returns": pivot})