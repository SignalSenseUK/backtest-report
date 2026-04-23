"""Header section renderer."""
from __future__ import annotations

from backtest_report.models import BacktestData, BacktestMeta, SectionOutput


def render_header(data: BacktestData, meta: BacktestMeta) -> SectionOutput:
    """Render the report header — a dark banner with experiment metadata.

    Returns SectionOutput with:
        - section_id: "header"
        - html: rendered header template with metadata
    """
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    from backtest_report.render import get_template_dir

    cfg = meta.config

    # Pre-format values in Python (Jinja2 format filter uses % operator)
    engine_display = cfg.engine
    if cfg.engine_version:
        engine_display += f" v{cfg.engine_version}"

    period = f"{cfg.start_date} → {cfg.end_date}"
    capital_display = f"{cfg.currency} {cfg.capital:,.0f}"
    risk_target_display = f"{cfg.risk_target_annual_pct:.1f}% annualised"
    instrument_list = ", ".join(cfg.instrument_universe)

    template_dir = get_template_dir()
    env = Environment(
        loader=FileSystemLoader(str(template_dir / "sections")),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("header.html")

    context = {
        "strategy_name": cfg.strategy_name,
        "experiment_id": cfg.experiment_id,
        "engine_display": engine_display,
        "period": period,
        "capital_display": capital_display,
        "risk_target_display": risk_target_display,
        "instrument_list": instrument_list,
        "git_commit": cfg.git_commit,
        "generated_at": meta.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
    }
    html = template.render(**context)
    return SectionOutput(section_id="header", html=html)
