"""Unit tests for data models."""
from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from backtest_report.models import (
    BacktestConfig,
    BacktestData,
    BacktestMeta,
    InstrumentMeta,
    SectionOutput,
)
from pydantic import BaseModel


class TestInstrumentMeta:
    def test_create_minimal(self) -> None:
        im = InstrumentMeta(code="ES")
        assert im.code == "ES"
        assert im.name == ""
        assert im.sector == ""
        assert im.point_value == 1.0
        assert im.currency == "USD"

    def test_create_full(self) -> None:
        im = InstrumentMeta(
            code="ES",
            name="E-mini S&P 500",
            sector="Equity Index",
            group="Futures",
            asset_class="Index",
            exchange="CME",
            point_value=5.0,
            currency="USD",
        )
        assert im.code == "ES"
        assert im.name == "E-mini S&P 500"
        assert im.sector == "Equity Index"
        assert im.exchange == "CME"
        assert im.point_value == 5.0

    def test_serialization(self) -> None:
        im = InstrumentMeta(code="ES", name="E-mini S&P 500", sector="Equity Index")
        data = im.model_dump()
        assert data["code"] == "ES"
        assert data["name"] == "E-mini S&P 500"


class TestBacktestConfig:
    def test_create(self) -> None:
        config = BacktestConfig(
            experiment_id="test-exp-001",
            strategy_name="Momentum",
            instrument_universe=["ES", "NQ"],
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31),
            capital=1_000_000.0,
            risk_target_annual_pct=20.0,
        )
        assert config.experiment_id == "test-exp-001"
        assert config.strategy_name == "Momentum"
        assert config.engine == "pysystemtrade"
        assert config.capital == 1_000_000.0

    def test_defaults(self) -> None:
        config = BacktestConfig(
            experiment_id="test",
            strategy_name="Test",
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31),
            capital=100_000.0,
            risk_target_annual_pct=20.0,
        )
        assert config.currency == "USD"
        assert config.engine == "pysystemtrade"
        assert config.instrument_universe == []


class TestBacktestData:
    def _make_returns(self) -> pd.Series:
        dates = pd.date_range("2020-01-01", periods=252, freq="B")
        returns = pd.Series(np.random.randn(252) * 0.01, index=dates, name="portfolio_returns")
        return returns

    def _make_instrument_pnl(self, dates: pd.DatetimeIndex) -> pd.DataFrame:
        return pd.DataFrame(
            np.random.randn(len(dates), 3) * 1000,
            index=dates,
            columns=["ES", "NQ", "YM"],
        )

    def _make_positions(self, dates: pd.DatetimeIndex) -> pd.DataFrame:
        return pd.DataFrame(
            np.random.randint(-20, 21, (len(dates), 3)),
            index=dates,
            columns=["ES", "NQ", "YM"],
        )

    def test_create_valid(self) -> None:
        dates = pd.date_range("2020-01-01", periods=252, freq="B")
        returns = pd.Series(np.random.randn(252) * 0.01, index=dates, name="portfolio_returns")
        pnl = self._make_instrument_pnl(dates)
        positions = self._make_positions(dates)

        data = BacktestData(
            portfolio_returns=returns,
            instrument_pnl=pnl,
            positions=positions,
        )
        assert len(data.portfolio_returns) == 252
        assert data.instrument_pnl.shape == (252, 3)
        assert data.positions.shape == (252, 3)

    def test_empty_portfolio_returns_raises(self) -> None:
        dates = pd.date_range("2020-01-01", periods=10, freq="B")
        empty = pd.Series([], index=dates[:0], dtype=float, name="portfolio_returns")
        pnl = self._make_instrument_pnl(dates)
        positions = self._make_positions(dates)

        with pytest.raises(ValueError, match="must not be empty"):
            BacktestData(portfolio_returns=empty, instrument_pnl=pnl, positions=positions)

    def test_non_datetime_index_raises(self) -> None:
        s = pd.Series([1, 2, 3], index=[1, 2, 3], name="portfolio_returns")
        pnl = pd.DataFrame({"a": [1, 2, 3]}, index=[1, 2, 3])
        positions = pd.DataFrame({"a": [1, 2, 3]}, index=[1, 2, 3])

        with pytest.raises(ValueError, match="DatetimeIndex"):
            BacktestData(portfolio_returns=s, instrument_pnl=pnl, positions=positions)

    def test_instrument_meta(self) -> None:
        dates = pd.date_range("2020-01-01", periods=252, freq="B")
        returns = pd.Series(np.random.randn(252) * 0.01, index=dates, name="portfolio_returns")
        pnl = self._make_instrument_pnl(dates)
        positions = self._make_positions(dates)

        meta = {
            "ES": InstrumentMeta(code="ES", name="E-mini S&P 500", sector="Equity Index"),
            "NQ": InstrumentMeta(code="NQ", name="E-mini NASDAQ", sector="Equity Index"),
        }

        data = BacktestData(
            portfolio_returns=returns,
            instrument_pnl=pnl,
            positions=positions,
            instrument_meta=meta,
        )
        assert data.instrument_meta["ES"].name == "E-mini S&P 500"

    def test_serializable_types(self) -> None:
        # Verify the model accepts pandas types (arbitrary_types_allowed=True)
        # Note: model_dump_json() will fail for pandas objects — this is expected
        dates = pd.date_range("2020-01-01", periods=252, freq="B")
        returns = pd.Series(np.random.randn(252) * 0.01, index=dates, name="portfolio_returns")
        pnl = self._make_instrument_pnl(dates)
        positions = self._make_positions(dates)

        data = BacktestData(
            portfolio_returns=returns,
            instrument_pnl=pnl,
            positions=positions,
        )
        # Verify the model was created successfully
        assert len(data.portfolio_returns) == 252


class TestBacktestMeta:
    def test_create(self) -> None:
        config = BacktestConfig(
            experiment_id="test",
            strategy_name="Test",
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31),
            capital=100_000.0,
            risk_target_annual_pct=20.0,
        )
        meta = BacktestMeta(
            config=config,
            generated_at=datetime(2024, 6, 1, 12, 0, 0),
            report_version="0.1.0",
            data_checksums={"portfolio_returns": "sha256:abc123"},
            notes="Test run",
        )
        assert meta.config.experiment_id == "test"
        assert meta.report_version == "0.1.0"
        assert meta.data_checksums["portfolio_returns"] == "sha256:abc123"

    def test_model_dump(self) -> None:
        config = BacktestConfig(
            experiment_id="test",
            strategy_name="Test",
            start_date=date(2020, 1, 1),
            end_date=date(2024, 12, 31),
            capital=100_000.0,
            risk_target_annual_pct=20.0,
        )
        meta = BacktestMeta(
            config=config,
            generated_at=datetime(2024, 6, 1, 12, 0, 0),
            report_version="0.1.0",
        )
        data = meta.model_dump()
        assert data["report_version"] == "0.1.0"
        assert "config" in data


class TestSectionOutput:
    def test_create_minimal(self) -> None:
        output = SectionOutput(section_id="test", html="<p>Hello</p>")
        assert output.section_id == "test"
        assert output.html == "<p>Hello</p>"
        assert output.figures == {}
        assert output.tables == {}

    def test_create_with_figures_and_tables(self) -> None:
        df = pd.DataFrame({"a": [1, 2, 3]})
        output = SectionOutput(
            section_id="test",
            html="<p>Hello</p>",
            figures={"chart1": "base64data..."},
            tables={"table1": df},
        )
        assert output.figures["chart1"] == "base64data..."
        assert output.tables["table1"].shape == (3, 1)

    def test_dataclass_not_pydantic(self) -> None:
        # SectionOutput is a plain dataclass, not a Pydantic model
        output = SectionOutput(section_id="test", html="<p>Test</p>")
        assert not isinstance(output, BaseModel)