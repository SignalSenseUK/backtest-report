"""Appendix section renderer."""
from __future__ import annotations

from backtest_report.models import BacktestData, BacktestMeta, SectionOutput


def render_appendix(data: BacktestData, meta: BacktestMeta) -> SectionOutput:
    """Render the appendix section — config YAML dump, checksums, environment info.

    Returns SectionOutput with:
        - section_id: "appendix"
        - html: rendered appendix template
    """
    import yaml  # type: ignore[import-untyped]
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    from backtest_report.render import get_template_dir

    # Serialize config as YAML
    config_yaml = yaml.safe_dump(
        meta.config.model_dump(), default_flow_style=False, sort_keys=False
    )

    # Environment info
    import platform
    import sys

    environment = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "report_version": meta.report_version,
        "generated_at": meta.generated_at.isoformat(),
    }

    template_dir = get_template_dir()
    env = Environment(
        loader=FileSystemLoader(str(template_dir / "sections")),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("appendix.html")

    context = {
        "config_yaml": config_yaml,
        "checksums": meta.data_checksums,
        "environment": environment,
    }
    html = template.render(**context)
    return SectionOutput(section_id="appendix", html=html)
