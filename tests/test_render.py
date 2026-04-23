"""Unit tests for render module."""
from __future__ import annotations

from pathlib import Path

from backtest_report.models import SectionOutput
from backtest_report.render import assemble_html, get_template_dir, html_to_pdf


class TestGetTemplateDir:
    def test_returns_path(self) -> None:
        result = get_template_dir()
        assert isinstance(result, Path)
        assert result.name == "templates"

    def test_contains_report_html(self) -> None:
        result = get_template_dir()
        assert (result / "report.html").exists()


class TestAssembleHtml:
    def test_returns_non_empty_html_string(
        self, sample_data, sample_meta
    ) -> None:
        sections = {
            "portfolio_pnl": SectionOutput(
                section_id="portfolio_pnl",
                html="<div>test</div>",
                figures={},
            ),
        }
        html = assemble_html(sections, sample_meta)
        assert isinstance(html, str)
        assert len(html) > 1000
        assert "<!DOCTYPE html>" in html

    def test_contains_experiment_id(self, sample_data, sample_meta) -> None:
        sections = {}
        html = assemble_html(sections, sample_meta)
        assert sample_meta.config.experiment_id in html

    def test_includes_section_html(self, sample_data, sample_meta) -> None:
        sections = {
            "portfolio_pnl": SectionOutput(
                section_id="portfolio_pnl",
                html='<div id="test-section">Hello</div>',
                figures={},
            ),
        }
        html = assemble_html(sections, sample_meta)
        assert "test-section" in html
        assert "Hello" in html

    def test_custom_css_injected(self, sample_data, sample_meta) -> None:
        sections = {}
        html = assemble_html(sections, sample_meta, custom_css=".custom { color: red; }")
        assert "custom" in html

    def test_template_dir_override(self, tmp_path: Path, sample_data, sample_meta) -> None:
        # Create minimal template override
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "style.css").write_text("/* custom */")
        (template_dir / "report.html").write_text(
            "<!DOCTYPE html><html><head><style>{% include 'style.css' %}</style></head>"
            "<body>OVERRIDE</body></html>"
        )
        sections = {}
        html = assemble_html(sections, sample_meta, template_dir=template_dir)
        assert "OVERRIDE" in html


class TestHtmlToPdf:
    def test_writes_pdf_file(self, tmp_path: Path) -> None:
        html = "<!DOCTYPE html><html><head></head><body><p>Test</p></body></html>"
        output_path = tmp_path / "report.pdf"
        result = html_to_pdf(html, output_path)
        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_pdf_has_pdf_magic_bytes(self, tmp_path: Path) -> None:
        html = "<!DOCTYPE html><html><head></head><body><p>Test</p></body></html>"
        output_path = tmp_path / "report.pdf"
        html_to_pdf(html, output_path)
        data = output_path.read_bytes()
        assert data[:4] == b"%PDF"
