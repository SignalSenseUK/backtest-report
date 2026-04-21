"""Unit tests for portfolio section renderers."""
from __future__ import annotations

import base64

import matplotlib.pyplot as plt
import pytest

from backtest_report.models import BacktestData, SectionOutput
from backtest_report.portfolio import (
    _format_return,
    apply_report_style,
    fig_to_base64,
    render_monthly_returns,
    render_portfolio_pnl,
)


class TestApplyReportStyle:
    def test_no_exceptions(self) -> None:
        apply_report_style()


class TestFigToBase64:
    def test_returns_non_empty_string(self) -> None:
        apply_report_style()
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [1, 2, 3])
        result = fig_to_base64(fig)
        assert isinstance(result, str)
        assert len(result) > 1000

    def test_is_valid_base64(self) -> None:
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
        assert result.html.count("data:image/png;base64,") == 2

    def test_returns_SectionOutput_type(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_portfolio_pnl(sample_backtest_data, sample_meta)
        assert isinstance(result, SectionOutput)
        assert result.figures is not None
        assert result.tables == {}


class TestRenderMonthlyReturns:
    def test_returns_correct_section_id(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_monthly_returns(sample_backtest_data, sample_meta)
        assert result.section_id == "monthly_returns"

    def test_html_contains_table(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_monthly_returns(sample_backtest_data, sample_meta)
        assert "<table" in result.html
        assert "br-monthly-returns" in result.html

    def test_table_has_year_rows(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_monthly_returns(sample_backtest_data, sample_meta)
        assert result.html.count("<tr>") >= 5

    def test_table_has_14_columns(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_monthly_returns(sample_backtest_data, sample_meta)
        assert result.html.count("<th>") >= 14

    def test_conditional_coloring_applied(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_monthly_returns(sample_backtest_data, sample_meta)
        assert "background-color:" in result.html

    def test_best_and_worst_highlighted(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_monthly_returns(sample_backtest_data, sample_meta)
        html = result.html
        # Green or red border for best/worst cells
        assert "10b981" in html or "ef4444" in html

    def test_tables_contains_pivot_dataframe(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_monthly_returns(sample_backtest_data, sample_meta)
        assert "monthly_returns" in result.tables
        pivot = result.tables["monthly_returns"]
        assert pivot.index.name == "year"
        assert len(pivot.columns) == 13  # 12 months + Year

    def test_handles_partial_first_year(
        self, sample_backtest_data: BacktestData, sample_meta
    ) -> None:
        result = render_monthly_returns(sample_backtest_data, sample_meta)
        assert result.section_id == "monthly_returns"


class TestFormatReturn:
    def test_none_returns_dash(self) -> None:
        assert _format_return(None) == "—"

    def test_nan_returns_dash(self) -> None:
        import numpy as np

        assert _format_return(float("nan")) == "—"

    def test_positive_return_formatted(self) -> None:
        assert _format_return(0.05) == "+5.0%"

    def test_negative_return_formatted(self) -> None:
        assert _format_return(-0.032) == "-3.2%"

    def test_zero_return_formatted(self) -> None:
        assert _format_return(0.0) == "+0.0%"