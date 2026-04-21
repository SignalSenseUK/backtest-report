"""Unit tests for portfolio section renderers."""
from __future__ import annotations

import pytest

from backtest_report.models import BacktestData, SectionOutput
from backtest_report.portfolio import (
    apply_report_style,
    fig_to_base64,
    render_portfolio_pnl,
)


class TestApplyReportStyle:
    def test_no_exceptions(self) -> None:
        apply_report_style()


class TestFigToBase64:
    def test_returns_non_empty_string(self) -> None:
        import matplotlib.pyplot as plt

        apply_report_style()
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [1, 2, 3])
        result = fig_to_base64(fig)
        assert isinstance(result, str)
        assert len(result) > 1000

    def test_is_valid_base64(self) -> None:
        import base64

        import matplotlib.pyplot as plt

        apply_report_style()
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [1, 2, 3])
        result = fig_to_base64(fig)
        decoded = base64.b64decode(result)
        assert decoded.startswith(b"\x89PNG")


class TestRenderPortfolioPnl:
    def test_returns_correct_section_id(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_portfolio_pnl(sample_backtest_data, sample_meta)
        assert result.section_id == "portfolio_pnl"

    def test_figures_contain_equity_and_drawdown(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_portfolio_pnl(sample_backtest_data, sample_meta)
        assert "equity_curve" in result.figures
        assert "drawdown" in result.figures

    def test_figures_are_non_empty_base64(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_portfolio_pnl(sample_backtest_data, sample_meta)
        for key in ("equity_curve", "drawdown"):
            assert len(result.figures[key]) > 1000
            # Each base64 character maps to 6 bits; PNG start bytes verify decoding
            import base64

            decoded = base64.b64decode(result.figures[key])
            assert decoded.startswith(b"\x89PNG")

    def test_html_contains_img_tags(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_portfolio_pnl(sample_backtest_data, sample_meta)
        assert "<img" in result.html
        assert "data:image/png;base64," in result.html

    def test_html_references_both_figures(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_portfolio_pnl(sample_backtest_data, sample_meta)
        html = result.html
        # Both equity_curve and drawdown should be embedded
        assert html.count("data:image/png;base64,") == 2

    def test_returns_SectionOutput_type(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_portfolio_pnl(sample_backtest_data, sample_meta)
        assert isinstance(result, SectionOutput)
        assert result.figures is not None
        assert result.tables == {}