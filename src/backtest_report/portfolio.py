"""Portfolio-level section renderers.

Each function: render_<section_id>(data: BacktestData, meta: BacktestMeta) -> SectionOutput.
All charts use matplotlib (not QuantStats built-in plots). QuantStats is only for metrics.
Charts are encoded as base64 PNG and returned in SectionOutput.figures.
"""
from __future__ import annotations

import logging
from io import BytesIO
from math import sqrt

import matplotlib
import matplotlib.pyplot as plt
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
        f'<img src="data:image/png;base64,{equity_base64}" '
        f'alt="Cumulative Returns" style="width:100%;" />'
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
        year_colour = (
            _return_to_color(year_val)
            if year_val is not None and not pd.isna(year_val)
            else "#f3f4f6"
        )
        year_text = _format_return(year_val)
        cells.append(
            f'<td style="background-color: {year_colour}; font-weight: 600">{year_text}</td>'
        )

        lines.append(f"<tr><td class='br-year-label'>{year}</td>" + "".join(cells) + "</tr>")

    lines.extend(["</tbody>", "</table>"])

    html = "\n".join(lines)
    return SectionOutput(section_id="monthly_returns", html=html, tables={"monthly_returns": pivot})


def render_portfolio_stats(data: BacktestData, meta: BacktestMeta) -> SectionOutput:
    """Render key portfolio metrics as a 2-column HTML table.

    Computes 15 metrics using qs.stats with manual pandas/numpy fallbacks.
    All qs.stats calls are wrapped in try/except with logging on fallback.

    Returns SectionOutput with:
        - section_id: "portfolio_stats"
        - html: <table class="br-portfolio-stats">...</table>
    """
    apply_report_style()
    returns = data.portfolio_returns

    # Precompute cumulative/drawdown for fallbacks
    cumulative = (1 + returns).cumprod()
    cummax = cumulative.cummax()
    drawdown = cumulative / cummax - 1
    max_dd = drawdown.min()

    def _format_metric_value(value: float, name: str) -> str:
        pct_metrics = {
            "Total Return", "CAGR", "Annualised Vol", "Max Drawdown",
            "Win Rate", "Best Day", "Worst Day",
        }
        ratio_metrics = {
            "Sharpe Ratio", "Sortino Ratio", "Calmar Ratio",
            "Profit Factor", "Avg Win / Avg Loss",
        }
        if name in pct_metrics:
            return f"{value * 100:.2f}%"
        elif name in ratio_metrics:
            return f"{value:.2f}"
        elif name == "Max DD Duration":
            return f"{int(value)} days"
        else:
            return f"{value:.2f}"

    import quantstats as qs

    metrics = []

    # Total Return
    try:
        total_ret = qs.stats.comp(returns)
    except Exception:
        total_ret = (1 + returns).prod() - 1
    metrics.append(("Total Return", _format_metric_value(total_ret, "Total Return")))

    # CAGR
    try:
        cagr = qs.stats.cagr(returns)
    except Exception:
        years = len(returns) / 252
        cagr = (1 + total_ret) ** (1 / years) - 1 if years > 0 else 0
    metrics.append(("CAGR", _format_metric_value(cagr, "CAGR")))

    # Annualised Vol
    try:
        vol = qs.stats.volatility(returns)
    except Exception:
        vol = returns.std() * sqrt(252)
    metrics.append(("Annualised Vol", _format_metric_value(vol, "Annualised Vol")))

    # Sharpe Ratio
    try:
        sharpe = qs.stats.sharpe(returns)
    except Exception:
        sharpe = cagr / vol if vol > 0 else 0
    metrics.append(("Sharpe Ratio", _format_metric_value(sharpe, "Sharpe Ratio")))

    # Sortino Ratio
    try:
        sortino = qs.stats.sortino(returns)
    except Exception:
        downside = returns[returns < 0]
        downside_std = downside.std() * sqrt(252) if len(downside) > 0 else 0
        sortino = cagr / downside_std if downside_std > 0 else 0
    metrics.append(("Sortino Ratio", _format_metric_value(sortino, "Sortino Ratio")))

    # Max Drawdown
    try:
        max_dd_val = qs.stats.max_drawdown(returns)
    except Exception:
        max_dd_val = max_dd
    metrics.append(("Max Drawdown", _format_metric_value(max_dd_val, "Max Drawdown")))

    # Calmar Ratio
    try:
        calmar = qs.stats.calmar(returns)
    except Exception:
        calmar = cagr / abs(max_dd_val) if max_dd_val != 0 else 0
    metrics.append(("Calmar Ratio", _format_metric_value(calmar, "Calmar Ratio")))

    # Max DD Duration (calendar days)
    # qs.stats.max_drawdown_duration does not exist; use drawdown_details
    try:
        dd_series = qs.stats.to_drawdown_series(returns)
        dd_details = qs.stats.drawdown_details(dd_series)
        if dd_details is not None and len(dd_details) > 0:
            dd_dur = int(dd_details["days"].max())
        else:
            dd_dur = 0
    except Exception:
        # Manual fallback: compute drawdown and find longest underwater period
        cumulative = (1 + returns).cumprod()
        cummax = cumulative.cummax()
        drawdown = cumulative / cummax - 1
        in_dd = drawdown < 0
        # Group consecutive in-DD / not-in-DD runs
        changes = in_dd != in_dd.shift(fill_value=False)
        groups = changes.cumsum()
        dd_dur = 0
        for g in groups.unique():
            mask = groups == g
            if in_dd[mask].any():
                # This group contains at least some DD days
                dd_days = in_dd[mask].sum()
                dd_dur = max(dd_dur, dd_days)
    metrics.append(("Max DD Duration", _format_metric_value(dd_dur, "Max DD Duration")))

    # Win Rate
    try:
        win_rate = qs.stats.win_rate(returns)
    except Exception:
        win_rate = (returns > 0).mean()
    metrics.append(("Win Rate", _format_metric_value(win_rate, "Win Rate")))

    # Profit Factor
    try:
        pf = qs.stats.profit_factor(returns)
    except Exception:
        gross_profit = returns[returns > 0].sum()
        gross_loss = abs(returns[returns < 0].sum())
        pf = gross_profit / gross_loss if gross_loss != 0 else 0
    metrics.append(("Profit Factor", _format_metric_value(pf, "Profit Factor")))

    # Avg Win / Avg Loss
    try:
        avg_win = qs.stats.avg_win(returns)
        avg_loss = abs(qs.stats.avg_loss(returns))
        win_loss_ratio = avg_win / avg_loss if avg_loss != 0 else 0
    except Exception:
        avg_win_val = returns[returns > 0].mean() if (returns > 0).any() else 0
        avg_loss_val = abs(returns[returns < 0].mean()) if (returns < 0).any() else 0
        win_loss_ratio = avg_win_val / avg_loss_val if avg_loss_val != 0 else 0
    metrics.append(
        ("Avg Win / Avg Loss", _format_metric_value(win_loss_ratio, "Avg Win / Avg Loss"))
    )

    # Skewness
    try:
        skew = qs.stats.skew(returns)
    except Exception:
        skew = returns.skew()
    metrics.append(("Skewness", _format_metric_value(skew, "Skewness")))

    # Kurtosis
    try:
        kurt = qs.stats.kurtosis(returns)
    except Exception:
        kurt = returns.kurtosis()
    metrics.append(("Kurtosis", _format_metric_value(kurt, "Kurtosis")))

    # Best Day
    try:
        best = qs.stats.best(returns)
    except Exception:
        best = returns.max()
    metrics.append(("Best Day", _format_metric_value(best, "Best Day")))

    # Worst Day
    try:
        worst = qs.stats.worst(returns)
    except Exception:
        worst = returns.min()
    metrics.append(("Worst Day", _format_metric_value(worst, "Worst Day")))

    # Build HTML table
    lines = [
        '<table class="br-portfolio-stats">',
        "<thead><tr><th>Metric</th><th>Value</th></tr></thead>",
        "<tbody>",
    ]
    for name, value in metrics:
        lines.append(f"<tr><td>{name}</td><td class='br-metric-value'>{value}</td></tr>")
    lines.extend(["</tbody>", "</table>"])

    html = "\n".join(lines)
    return SectionOutput(section_id="portfolio_stats", html=html)


def render_rolling_stats(data: BacktestData, meta: BacktestMeta) -> SectionOutput:
    """Render rolling statistics charts.

    - Rolling 252-day (1-year) Sharpe ratio
    - Rolling 756-day (3-year) annualised return (only if >= 756 days of data)
    - Conditional beta chart (only if benchmark_returns provided)

    Returns SectionOutput with:
        - section_id: "rolling_stats"
        - figures: dict of available chart base64 PNGs
        - html: div with img tags
    """
    apply_report_style()
    returns = data.portfolio_returns

    # Short-history warning
    if len(returns) < 252:
        warning_html = (
            "<div class='br-warning-banner'>"
            "⚠ Insufficient history for rolling statistics (minimum 1 year required)"
            "</div>"
        )
        return SectionOutput(section_id="rolling_stats", html=warning_html)

    figures = {}
    html_parts = []

    # --- Rolling 1-Year Sharpe ---
    rolling_mean = returns.rolling(252).mean()
    rolling_vol = returns.rolling(252).std()
    rolling_sharpe = (rolling_mean * 252) / (rolling_vol * sqrt(252))

    fig_sharpe, ax_sharpe = plt.subplots(figsize=(FIGURE_WIDTH, FIGURE_HEIGHT))
    ax_sharpe.plot(rolling_sharpe.index, rolling_sharpe.values, color=POSITIVE_COLOR, linewidth=0.8)
    ax_sharpe.axhline(y=0, color=NEUTRAL_COLOR, linestyle="--", linewidth=0.8, alpha=0.7)
    ax_sharpe.set_title("Rolling 1-Year Sharpe Ratio")
    ax_sharpe.set_ylabel("Sharpe")
    ax_sharpe.set_xlabel("")
    ax_sharpe.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:.2f}"))
    _format_date_axis(ax_sharpe)
    sharpe_base64 = fig_to_base64(fig_sharpe)
    figures["rolling_sharpe"] = sharpe_base64
    html_parts.append(
        f'<div class="br-figure"><img src="data:image/png;base64,{sharpe_base64}" '
        'alt="Rolling 1-Year Sharpe Ratio" style="width:100%;" /></div>'
    )

    # --- Rolling 3-Year Annualised Return (only if >= 756 days) ---
    if len(returns) >= 756:
        def _compound_annualised(x):
            if len(x) < 2:
                return float("nan")
            return (1 + x).prod() ** (252 / len(x)) - 1

        rolling_3y = returns.rolling(756).apply(_compound_annualised)

        fig_3y, ax_3y = plt.subplots(figsize=(FIGURE_WIDTH, FIGURE_HEIGHT))
        ax_3y.plot(rolling_3y.index, rolling_3y.values * 100, color=POSITIVE_COLOR, linewidth=0.8)
        ax_3y.axhline(y=0, color=NEUTRAL_COLOR, linestyle="--", linewidth=0.8, alpha=0.7)
        ax_3y.set_title("Rolling 3-Year Annualised Return")
        ax_3y.set_ylabel("Return %")
        ax_3y.set_xlabel("")
        ax_3y.yaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:.1f}%")
        )
        _format_date_axis(ax_3y)
        ret_3y_base64 = fig_to_base64(fig_3y)
        figures["rolling_3y_return"] = ret_3y_base64
        html_parts.append(
            f'<div class="br-figure"><img src="data:image/png;base64,{ret_3y_base64}" '
            'alt="Rolling 3-Year Annualised Return" style="width:100%;" /></div>'
        )

    # --- Beta to Benchmark (conditional) ---
    if data.benchmark_returns is not None:
        bm = data.benchmark_returns.reindex(returns.index).dropna()
        # Align portfolio to benchmark index for covariance calculation
        port_aligned = returns.reindex(bm.index)
        rolling_cov = port_aligned.rolling(252).cov(bm)
        rolling_var = bm.rolling(252).var()
        rolling_beta = rolling_cov / rolling_var

        fig_beta, ax_beta = plt.subplots(figsize=(FIGURE_WIDTH, FIGURE_HEIGHT))
        ax_beta.plot(rolling_beta.index, rolling_beta.values, color=POSITIVE_COLOR, linewidth=0.8)
        ax_beta.axhline(y=0, color=NEUTRAL_COLOR, linestyle="--", linewidth=0.8, alpha=0.7)
        ax_beta.set_title("Rolling 1-Year Beta")
        ax_beta.set_ylabel("Beta")
        ax_beta.set_xlabel("")
        ax_beta.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:.2f}"))
        _format_date_axis(ax_beta)
        beta_base64 = fig_to_base64(fig_beta)
        figures["rolling_beta"] = beta_base64
        html_parts.append(
            f'<div class="br-figure"><img src="data:image/png;base64,{beta_base64}" '
            'alt="Rolling 1-Year Beta" style="width:100%;" /></div>'
        )

    html = '<div class="br-rolling-stats">' + "".join(html_parts) + "</div>"
    return SectionOutput(section_id="rolling_stats", html=html, figures=figures)
