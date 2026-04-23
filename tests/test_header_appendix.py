"""Unit tests for header and appendix section renderers."""
from __future__ import annotations

from backtest_report.appendix import render_appendix
from backtest_report.header import render_header
from backtest_report.models import BacktestData, SectionOutput


class TestRenderHeader:
    def test_returns_correct_section_id(self, sample_data: BacktestData, sample_meta) -> None:
        result = render_header(sample_data, sample_meta)
        assert result.section_id == "header"

    def test_html_contains_experiment_id(self, sample_data: BacktestData, sample_meta) -> None:
        result = render_header(sample_data, sample_meta)
        assert sample_meta.config.experiment_id in result.html

    def test_html_contains_strategy_name(self, sample_data: BacktestData, sample_meta) -> None:
        result = render_header(sample_data, sample_meta)
        assert sample_meta.config.strategy_name in result.html

    def test_html_contains_period(self, sample_data: BacktestData, sample_meta) -> None:
        result = render_header(sample_data, sample_meta)
        assert str(sample_meta.config.start_date) in result.html
        assert str(sample_meta.config.end_date) in result.html

    def test_html_contains_capital(self, sample_data: BacktestData, sample_meta) -> None:
        result = render_header(sample_data, sample_meta)
        html = result.html
        # Should contain capital formatted
        assert str(int(sample_meta.config.capital)) in html or "1,000" in html

    def test_returns_SectionOutput(self, sample_data: BacktestData, sample_meta) -> None:
        result = render_header(sample_data, sample_meta)
        assert isinstance(result, SectionOutput)


class TestRenderAppendix:
    def test_returns_correct_section_id(self, sample_data: BacktestData, sample_meta) -> None:
        result = render_appendix(sample_data, sample_meta)
        assert result.section_id == "appendix"

    def test_html_contains_config_yaml(self, sample_data: BacktestData, sample_meta) -> None:
        result = render_appendix(sample_data, sample_meta)
        assert "experiment_id" in result.html

    def test_html_contains_checksums(self, sample_data: BacktestData, sample_meta) -> None:
        result = render_appendix(sample_data, sample_meta)
        html = result.html
        # sample_meta has sha256 checksums
        assert "sha256" in html

    def test_html_contains_environment(self, sample_data: BacktestData, sample_meta) -> None:
        result = render_appendix(sample_data, sample_meta)
        html = result.html
        # Should have python_version or platform info
        assert "python" in html.lower() or "platform" in html.lower()

    def test_returns_SectionOutput(self, sample_data: BacktestData, sample_meta) -> None:
        result = render_appendix(sample_data, sample_meta)
        assert isinstance(result, SectionOutput)
