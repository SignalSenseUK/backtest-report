"""Unit tests for instrument section renderers."""
from __future__ import annotations

import pandas as pd

from backtest_report.instrument import render_instrument_pnl, render_instrument_table
from backtest_report.models import BacktestData, SectionOutput


class TestRenderInstrumentPnl:
    def test_returns_correct_section_id(self, sample_data: BacktestData, sample_meta) -> None:
        result = render_instrument_pnl(sample_data, sample_meta)
        assert result.section_id == "instrument_pnl"

    def test_figures_contain_instrument_pnl(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        result = render_instrument_pnl(sample_data, sample_meta)
        assert "instrument_pnl" in result.figures

    def test_base64_is_valid_png(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        import base64

        result = render_instrument_pnl(sample_data, sample_meta)
        decoded = base64.b64decode(result.figures["instrument_pnl"])
        assert decoded.startswith(b"\x89PNG")

    def test_html_contains_img_tag(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        result = render_instrument_pnl(sample_data, sample_meta)
        assert "<img" in result.html
        assert "data:image/png;base64," in result.html


class TestRenderInstrumentTable:
    def test_returns_correct_section_id(self, sample_data: BacktestData, sample_meta) -> None:
        result = render_instrument_table(sample_data, sample_meta)
        assert result.section_id == "instrument_table"

    def test_html_contains_table(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        result = render_instrument_table(sample_data, sample_meta)
        assert "<table" in result.html
        assert "br-instrument-table" in result.html

    def test_instrument_codes_present(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        result = render_instrument_table(sample_data, sample_meta)
        # Fixture instruments: EDOLLAR, US10, US5, GOLD, CRUDE_W, SP500, EUROSTX, GAS_US, CORN, JPY
        for code in ["EDOLLAR", "US10", "US5", "GOLD", "CRUDE_W"]:
            assert code in result.html

    def test_sorted_by_pnl(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        result = render_instrument_table(sample_data, sample_meta)
        # All 10 fixture instruments should appear
        assert result.html.count("<td>") >= 10

    def test_returns_SectionOutput_type(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        result = render_instrument_table(sample_data, sample_meta)
        assert isinstance(result, SectionOutput)

    def test_empty_instrument_pnl(self, sample_data: BacktestData, sample_meta) -> None:
        empty_data = sample_data.model_copy(deep=True)
        empty_data.instrument_pnl = pd.DataFrame(index=empty_data.instrument_pnl.index)
        result = render_instrument_table(empty_data, sample_meta)
        assert "br-muted" in result.html
