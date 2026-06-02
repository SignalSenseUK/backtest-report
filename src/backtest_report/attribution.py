"""Return attribution section renderers (by instrument and by sector)."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from backtest_report.models import BacktestData, BacktestMeta, SectionOutput
from backtest_report.portfolio import apply_report_style, fig_to_base64


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
        monthly_pnl = data.instrument_pnl.resample("ME").sum()

        # Sum across instruments to get total monthly
        total_monthly = monthly_pnl.sum(axis=1)

        # For each instrument, fraction of total monthly PnL
        # Show top 10 instruments by cumulative PnL
        cum_pnl = data.instrument_pnl.sum().sort_values(ascending=False)
        top_instruments = cum_pnl.head(10).index.tolist()

        n = len(monthly_pnl)
        bottom = np.zeros(n)

        fig_attr, ax_attr = plt.subplots(figsize=(12, 4))
        colors = plt.get_cmap("tab10").colors  # type: ignore[attr-defined]

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
            ax_attr.bar(
                range(n), other_vals, bottom=bottom, label="Other", color="#cccccc", width=0.8
            )
            bottom += other_vals

        # Overlay total line
        ax_attr.plot(
            range(n),
            total_monthly.values,
            color="black",
            linewidth=1.5,
            label="Total",
            linestyle="--",
        )

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
            f'<img src="data:image/png;base64,{instr_base64}" '
            f'alt="Attribution by Instrument" style="width:100%;" />'
            f'<figcaption class="br-figure-caption">'
            f"Return attribution by instrument (top 10 + Other)"
            f"</figcaption>\n"
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

        monthly_pnl = data.instrument_pnl.resample("ME").sum()

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
            sector_colors = plt.get_cmap("Set2").colors  # type: ignore[attr-defined]
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
            ax_sect.plot(
                range(n), total_monthly.values, color="black", linewidth=1.5, linestyle="--"
            )

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
                f'<img src="data:image/png;base64,{sect_base64}" '
                f'alt="Attribution by Sector" style="width:100%;" />'
                f'<figcaption class="br-figure-caption">Return attribution by sector</figcaption>'
                f"</figure>"
            )

    if not figures:
        html = (
            '<div class="br-attribution">'
            '<p class="br-muted">Attribution data not available.</p>'
            "</div>"
        )
    else:
        html = '<div class="br-attribution">' + "".join(html_parts) + "</div>"

    return SectionOutput(section_id="attribution", html=html, figures=figures)
