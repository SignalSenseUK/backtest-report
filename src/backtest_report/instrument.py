"""Instrument-level section renderers.

Each function: render_<section_id>(data: BacktestData, meta: BacktestMeta) -> SectionOutput.
"""
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

# Maximum instruments per page for PnL chart pagination
MAX_INSTRUMENTS_PER_PAGE = 20


def _render_instrument_page(
    instruments: list[str],
    cum_pnl: pd.DataFrame,
    data: BacktestData,
    page_num: int,
) -> tuple[str, str]:
    """Render a single page of instrument PnL small multiples.

    Args:
        instruments: list of instrument codes for this page
        cum_pnl: cumulative PnL DataFrame
        data: BacktestData for Sharpe lookup
        page_num: 1-based page number

    Returns:
        tuple of (base64_png, html_fragment)
    """
    ncols = 4
    nrows = int(np.ceil(len(instruments) / ncols))

    fig, axes = plt.subplots(
        nrows=nrows,
        ncols=ncols,
        figsize=(12, 2.5 * nrows),
    )
    if nrows == 1:
        axes = axes.reshape(1, -1)
    axes = axes.flatten()

    for i, code in enumerate(instruments):
        ax = axes[i]
        series = cum_pnl[code].dropna()

        if series.empty:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(code, fontsize=7)
            continue

        # Colour by total PnL sign
        total = series.iloc[-1]
        color = POSITIVE_COLOR if total >= 0 else NEGATIVE_COLOR

        ax.plot(series.index, series.values, color=color, linewidth=0.8)
        ax.axhline(y=0, color=NEUTRAL_COLOR, linestyle="--", linewidth=0.5, alpha=0.5)
        ax.set_title(f"{code}", fontsize=7, fontweight="600")

        # Sharpe annotation
        if len(series) > 20:
            rets = data.instrument_pnl[code].dropna()
            if len(rets) > 0:
                mean_ret = rets.mean() * 252
                vol = rets.std() * sqrt(252)
                sharpe = mean_ret / vol if vol > 0 else 0
                ax.annotate(
                    f"Sharpe: {sharpe:.2f}",
                    xy=(0.98, 0.95),
                    xycoords="axes fraction",
                    ha="right",
                    va="top",
                    fontsize=6,
                    color=color,
                )

        ax.tick_params(axis="x", labelsize=5)
        ax.tick_params(axis="y", labelsize=5)
        ax.set_xlabel("")
        ax.yaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}")
        )

    # Hide unused axes
    for j in range(len(instruments), len(axes)):
        axes[j].set_visible(False)

    plt.tight_layout(pad=0.5)
    fig_base64 = fig_to_base64(fig)

    page_label = f" (page {page_num})" if page_num > 1 else ""
    html = (
        '<div class="br-instrument-pnl">'
        f'<img src="data:image/png;base64,{fig_base64}" '
        f'alt="Instrument PnL{page_label}" style="width:100%;" />'
        "</div>"
    )

    return fig_base64, html


def render_instrument_pnl(data: BacktestData, meta: BacktestMeta) -> SectionOutput:
    """Render per-instrument cumulative PnL as a 4-column small-multiples grid.

    Instruments are sorted by total PnL (best → worst). Each subplot shows the
    instrument code, cumulative PnL curve, and Sharpe ratio annotation.

    If more than MAX_INSTRUMENTS_PER_PAGE (20) instruments are present, they
    are paginated across multiple chart pages to keep each figure legible.

    Returns SectionOutput with:
        - section_id: "instrument_pnl"
        - figures: {"instrument_pnl": base64_png} or {"instrument_pnl_p1": ..., "instrument_pnl_p2": ...}
        - html: div with img tag(s)
    """
    apply_report_style()

    if data.instrument_pnl.empty:
        html = (
            '<div class="br-instrument-pnl">'
            '<p class="br-muted">No instrument PnL data available.</p>'
            "</div>"
        )
        return SectionOutput(section_id="instrument_pnl", html=html, figures={})

    # Sort instruments by total PnL (best → worst)
    totals = data.instrument_pnl.sum().sort_values(ascending=False)
    instruments = totals.index.tolist()

    # Compute cumulative PnL for each instrument
    cum_pnl = data.instrument_pnl.cumsum()

    # Paginate if more than MAX_INSTRUMENTS_PER_PAGE
    n = len(instruments)
    if n <= MAX_INSTRUMENTS_PER_PAGE:
        # Single page — original behaviour
        fig_base64, html = _render_instrument_page(instruments, cum_pnl, data, page_num=1)
        return SectionOutput(
            section_id="instrument_pnl",
            html=html,
            figures={"instrument_pnl": fig_base64},
        )

    # Multiple pages
    figures = {}
    html_parts = []
    total_pages = int(np.ceil(n / MAX_INSTRUMENTS_PER_PAGE))

    for page_num in range(total_pages):
        start = page_num * MAX_INSTRUMENTS_PER_PAGE
        end = min(start + MAX_INSTRUMENTS_PER_PAGE, n)
        page_instruments = instruments[start:end]

        fig_key = f"instrument_pnl_p{page_num + 1}"
        fig_base64, html_frag = _render_instrument_page(page_instruments, cum_pnl, data, page_num + 1)

        figures[fig_key] = fig_base64
        html_parts.append(html_frag)

    html = "\n".join(html_parts)
    return SectionOutput(
        section_id="instrument_pnl",
        html=html,
        figures=figures,
    )


def render_instrument_table(data: BacktestData, meta: BacktestMeta) -> SectionOutput:
    """Render per-instrument statistics as an HTML table.

    Computes: Sharpe, cumulative PnL, max drawdown, avg position, turnover, win rate.
    Sorted by PnL descending. Uses .br-instrument-table CSS class.

    Returns SectionOutput with:
        - section_id: "instrument_table"
        - html: <table class="br-instrument-table">...</table>
    """
    if data.instrument_pnl.empty:
        html = (
            '<div class="br-instrument-table-wrapper">'
            '<p class="br-muted">No instrument data available.</p>'
            "</div>"
        )
        return SectionOutput(section_id="instrument_table", html=html)

    instruments = list(data.instrument_pnl.columns)
    rows = []

    for code in instruments:
        pnl_series = data.instrument_pnl[code].dropna()
        if pnl_series.empty:
            continue

        # Compute metrics
        total_pnl = pnl_series.sum()
        max_dd = ((pnl_series).cumsum().cummax() - (pnl_series).cumsum()).max()
        win_rate = (pnl_series > 0).mean()

        # Sharpe
        if len(pnl_series) > 20:
            mean_annual = pnl_series.mean() * 252
            vol_annual = pnl_series.std() * sqrt(252)
            sharpe = mean_annual / vol_annual if vol_annual > 0 else 0
        else:
            sharpe = float("nan")

        # Average position (from positions df if available)
        if code in data.positions.columns:
            avg_position = data.positions[code].mean()
            turnover = data.positions[code].diff().abs().mean()
        else:
            avg_position = float("nan")
            turnover = float("nan")

        # Instrument name: use meta if available, fallback to code
        instr_meta = data.instrument_meta.get(code)
        name = instr_meta.name if instr_meta and instr_meta.name else code

        rows.append(
            {
                "code": code,
                "name": name,
                "total_pnl": total_pnl,
                "max_drawdown": max_dd,
                "win_rate": win_rate,
                "sharpe": sharpe,
                "avg_position": avg_position,
                "turnover": turnover,
            }
        )

    # Sort by total PnL descending
    rows.sort(key=lambda r: r["total_pnl"], reverse=True)

    # Build HTML table
    lines = [
        '<table class="br-instrument-table">',
        "<thead><tr>",
        "<th>Instrument</th>",
        "<th>Name</th>",
        "<th>Total P&amp;L</th>",
        "<th>Sharpe</th>",
        "<th>Max DD</th>",
        "<th>Win Rate</th>",
        "<th>Avg Position</th>",
        "<th>Turnover</th>",
        "</tr></thead>",
        "<tbody>",
    ]

    def _fmt_pnl(v: float) -> str:
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:,.0f}"

    def _fmt_ratio(v: float) -> str:
        if pd.isna(v):
            return "—"
        return f"{v:.2f}"

    def _fmt_pct(v: float) -> str:
        if pd.isna(v):
            return "—"
        return f"{v:.1%}"

    for r in rows:
        lines.append("<tr>")
        lines.append(f"<td><strong>{r['code']}</strong></td>")
        lines.append(f"<td>{r['name']}</td>")
        pnl_color = POSITIVE_COLOR if r["total_pnl"] >= 0 else NEGATIVE_COLOR
        lines.append(f"<td style='color:{pnl_color}'>{_fmt_pnl(r['total_pnl'])}</td>")
        lines.append(f"<td>{_fmt_ratio(r['sharpe'])}</td>")
        lines.append(f"<td>{_fmt_pnl(-r['max_drawdown'])}</td>")
        lines.append(f"<td>{_fmt_pct(r['win_rate'])}</td>")
        avg_pos = r["avg_position"]
        lines.append(f"<td>{_fmt_ratio(avg_pos) if not pd.isna(avg_pos) else '—'}</td>")
        turn = r["turnover"]
        lines.append(f"<td>{_fmt_ratio(turn) if not pd.isna(turn) else '—'}</td>")
        lines.append("</tr>")

    lines.extend(["</tbody>", "</table>"])

    html = "\n".join(lines)
    return SectionOutput(section_id="instrument_table", html=html)