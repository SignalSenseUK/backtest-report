"""HTML assembly and PDF rendering.

- assemble_html(): build complete HTML from section outputs using Jinja2 templates
- html_to_pdf(): convert HTML string to PDF using WeasyPrint
"""
from __future__ import annotations

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from backtest_report.models import BacktestMeta, SectionOutput

logger = logging.getLogger("backtest_report")

# Default template directory (package-relative)
_DEFAULT_TEMPLATE_DIR = Path(__file__).parent / "templates"


def get_template_dir() -> Path:
    """Return the path to the package's templates/ directory."""
    return _DEFAULT_TEMPLATE_DIR


def assemble_html(
    sections: dict[str, SectionOutput],
    meta: BacktestMeta,
    template_dir: Path | None = None,
    custom_css: str | None = None,
) -> str:
    """Assemble a complete HTML document from section outputs.

    Args:
        sections: dict mapping section_id → SectionOutput
        meta: BacktestMeta for the report
        template_dir: override for templates directory (default: package templates/)
        custom_css: optional additional CSS string to inject

    Returns:
        Complete HTML string ready for PDF rendering
    """
    if template_dir is None:
        template_dir = get_template_dir()

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )

    # Build a sections dict with the structure expected by templates
    # Template-accessible: sections.<id>.html, sections.<id>.figures
    template_sections = {}
    for section_id, output in sections.items():
        template_sections[section_id] = output

    # Prepare context
    context = {
        "meta": meta,
        "sections": template_sections,
        "custom_css": custom_css,
    }

    template = env.get_template("report.html")
    html = template.render(**context)
    return html


def html_to_pdf(
    html: str,
    output_path: Path,
    template_dir: Path | None = None,
) -> Path:
    """Convert HTML string to PDF using WeasyPrint.

    Args:
        html: complete HTML document string
        output_path: destination PDF file path
        template_dir: base URL for resolving relative resources (fonts, images)

    Returns:
        Path to the written PDF file
    """
    import weasyprint

    if template_dir is None:
        template_dir = get_template_dir()

    logger.info("Rendering HTML → PDF (%s bytes) to %s", len(html), output_path)

    doc = weasyprint.HTML(string=html, base_url=str(template_dir))
    doc.write_pdf(
        target=str(output_path),
        optimize_images=True,
        jpeg_quality=85,
    )

    logger.info("PDF written: %s (%.1f KB)", output_path, output_path.stat().st_size / 1024)
    return output_path
