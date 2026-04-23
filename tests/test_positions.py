"""Unit tests for position and attribution section renderers."""
from __future__ import annotations

from backtest_report.models import BacktestData, SectionOutput
from backtest_report.positions import render_attribution, render_position_snapshot


class TestRenderPositionSnapshot:
    def test_returns_correct_section_id(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        result = render_position_snapshot(sample_data, sample_meta)
        assert result.section_id == "position_snapshot"

    def test_figures_contain_heatmap(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        result = render_position_snapshot(sample_data, sample_meta)
        assert "heatmap" in result.figures

    def test_base64_is_valid_png(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        import base64

        result = render_position_snapshot(sample_data, sample_meta)
        decoded = base64.b64decode(result.figures["heatmap"])
        assert decoded.startswith(b"\x89PNG")

    def test_html_contains_img_tag(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        result = render_position_snapshot(sample_data, sample_meta)
        assert "<img" in result.html

    def test_returns_SectionOutput_type(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        result = render_position_snapshot(sample_data, sample_meta)
        assert isinstance(result, SectionOutput)


class TestRenderAttribution:
    def test_returns_correct_section_id(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        result = render_attribution(sample_data, sample_meta)
        assert result.section_id == "attribution"

    def test_figures_contain_by_instrument(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        result = render_attribution(sample_data, sample_meta)
        assert "by_instrument" in result.figures

    def test_base64_is_valid_png(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        import base64

        result = render_attribution(sample_data, sample_meta)
        decoded = base64.b64decode(result.figures["by_instrument"])
        assert decoded.startswith(b"\x89PNG")

    def test_html_contains_img_tag(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        result = render_attribution(sample_data, sample_meta)
        assert "<img" in result.html

    def test_returns_SectionOutput_type(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        result = render_attribution(sample_data, sample_meta)
        assert isinstance(result, SectionOutput)
