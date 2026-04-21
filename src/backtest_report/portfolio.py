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