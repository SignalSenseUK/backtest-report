"""Data models for backtest-report."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator


class InstrumentMeta(BaseModel):
    """Metadata for a single instrument."""

    code: str
    name: str = ""
    sector: str = ""
    group: str = ""
    asset_class: str = ""
    exchange: str = ""
    point_value: float = 1.0
    currency: str = "USD"


class BacktestConfig(BaseModel):
    """Configuration metadata for a backtest experiment."""

    experiment_id: str
    strategy_name: str
    engine: str = "pysystemtrade"
    engine_version: str = ""
    python_version: str = ""
    git_commit: str = ""
    instrument_universe: list[str] = Field(default_factory=list)
    start_date: date
    end_date: date
    capital: float
    currency: str = "USD"
    risk_target_annual_pct: float
    data_sources: list[str] = Field(default_factory=list)
    config_overrides: dict[str, Any] = Field(default_factory=dict)


class BacktestData(BaseModel):
    """Core backtest data — portfolio returns, instrument PnL, and positions."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    portfolio_returns: pd.Series
    instrument_pnl: pd.DataFrame
    positions: pd.DataFrame
    instrument_meta: dict[str, InstrumentMeta] = Field(default_factory=dict)
    instrument_returns: dict[str, pd.Series] = Field(default_factory=dict)
    benchmark_returns: pd.Series | None = None

    @field_validator("portfolio_returns")
    @classmethod
    def _validate_portfolio_returns(cls, v: pd.Series) -> pd.Series:
        if not isinstance(v.index, pd.DatetimeIndex):
            raise ValueError("portfolio_returns must have a DatetimeIndex")
        if v.empty:
            raise ValueError("portfolio_returns must not be empty")
        return v

    @field_validator("instrument_pnl")
    @classmethod
    def _validate_instrument_pnl(cls, v: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(v.index, pd.DatetimeIndex):
            raise ValueError("instrument_pnl must have a DatetimeIndex")
        return v

    @field_validator("positions")
    @classmethod
    def _validate_positions(cls, v: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(v.index, pd.DatetimeIndex):
            raise ValueError("positions must have a DatetimeIndex")
        return v


class BacktestMeta(BaseModel):
    """Metadata about a backtest report generation."""

    config: BacktestConfig
    generated_at: datetime
    report_version: str
    data_checksums: dict[str, str] = Field(default_factory=dict)
    notes: str = ""


@dataclass
class SectionOutput:
    """Output from a section renderer — HTML fragment and embedded assets."""

    section_id: str
    html: str
    figures: dict[str, str] = field(default_factory=dict)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
