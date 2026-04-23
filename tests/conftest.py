"""Pytest fixtures for backtest-report tests."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from backtest_report.models import (
    BacktestData,
    BacktestMeta,
    InstrumentMeta,
)

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"


@pytest.fixture
def sample_portfolio_returns() -> pd.Series:
    """Load sample portfolio returns from parquet fixture."""
    df = pd.read_parquet(FIXTURES_DIR / "sample_portfolio_returns.parquet")
    return df.iloc[:, 0]


@pytest.fixture
def sample_instrument_pnl() -> pd.DataFrame:
    """Load sample instrument PnL from parquet fixture."""
    return pd.read_parquet(FIXTURES_DIR / "sample_instrument_pnl.parquet")


@pytest.fixture
def sample_positions() -> pd.DataFrame:
    """Load sample positions from parquet fixture."""
    return pd.read_parquet(FIXTURES_DIR / "sample_positions.parquet")


@pytest.fixture
def sample_meta() -> BacktestMeta:
    """Load sample BacktestMeta from JSON fixture."""
    import json

    data = json.loads((FIXTURES_DIR / "sample_meta.json").read_text())
    return BacktestMeta.model_validate(data)


@pytest.fixture
def sample_data(
    sample_portfolio_returns: pd.Series,
    sample_instrument_pnl: pd.DataFrame,
    sample_positions: pd.DataFrame,
) -> BacktestData:
    """Construct BacktestData from fixture files."""
    return BacktestData(
        portfolio_returns=sample_portfolio_returns,
        instrument_pnl=sample_instrument_pnl,
        positions=sample_positions,
    )


@pytest.fixture
def sample_instrument_meta() -> dict[str, InstrumentMeta]:
    """Instrument metadata dict for the 10 fixture instruments."""
    return {
        "EDOLLAR": InstrumentMeta(code="EDOLLAR", name="Eurodollar", sector="Interest Rate"),
        "US10": InstrumentMeta(code="US10", name="US 10-Year Note", sector="Interest Rate"),
        "US5": InstrumentMeta(code="US5", name="US 5-Year Note", sector="Interest Rate"),
        "GOLD": InstrumentMeta(code="GOLD", name="Gold", sector="Metals"),
        "CRUDE_W": InstrumentMeta(code="CRUDE_W", name="WTI Crude Oil", sector="Energy"),
        "SP500": InstrumentMeta(code="SP500", name="S&P 500", sector="Equity Index"),
        "EUROSTX": InstrumentMeta(code="EUROSTX", name="Euro Stoxx 50", sector="Equity Index"),
        "GAS_US": InstrumentMeta(
            code="GAS_US", name="Henry Hub Natural Gas", sector="Energy"
        ),
        "CORN": InstrumentMeta(code="CORN", name="Corn", sector="Agriculture"),
        "JPY": InstrumentMeta(code="JPY", name="Japanese Yen", sector="FX"),
    }
