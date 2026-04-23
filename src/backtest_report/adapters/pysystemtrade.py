"""PySystemTrade adapter — convert System objects to BacktestData.

This module provides functions to extract backtest data and configuration
from a pysystemtrade System object.
"""
from __future__ import annotations

import logging
import pickle
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("backtest_report")


class PySystemTradeNotInstalled(ImportError):
    """Raised when pysystemtrade is not installed."""
    pass


def _check_pysystemtrade() -> None:
    """Verify pysystemtrade is installed."""
    try:
        import pysystemtrade  # noqa: F401
    except ImportError:
        raise PySystemTradeNotInstalled(
            "pysystemtrade is required for this function.\n"
            "Install with: pip install backtest-report[pysystemtrade]"
        ) from None


def load_system(pickle_path: Path) -> Any:
    """Load a pysystemtrade System object from a pickle file.

    Handles compatibility across pysystemtrade versions.

    Args:
        pickle_path: path to system.pkl

    Returns:
        System object
    """
    _check_pysystemtrade()


    logger.info("Loading pysystemtrade System from: %s", pickle_path)
    raw = pickle_path.read_bytes()

    # Try current protocol, then fall back to older protocols
    for protocol in range(pickle.HIGHEST_PROTOCOL, pickle.DEFAULT_PROTOCOL - 1, -1):
        try:
            system = pickle.loads(raw)
            logger.info("System loaded successfully (protocol %s)", protocol)
            return system
        except Exception:
            continue

    # Last resort: try with encoding
    try:
        system = pickle.loads(raw, encoding="latin1")
    except Exception as e:
        raise RuntimeError(f"Failed to unpickle system after trying all protocols: {e}") from e

    return system


def extract_backtest_config(system: Any, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extract BacktestConfig-compatible dict from a pysystemtrade System object.

    Args:
        system: pysystemtrade System object
        overrides: optional dict to override extracted values

    Returns:
        dict suitable for BacktestConfig.model_validate()
    """
    _check_pysystemtrade()

    from pysystemtrade.data.data import Data

    # Get backtest period from the system's data
    try:
        data = system.data
        if isinstance(data, Data):
            date_range = data.dates()
            start_date = date_range[0]
            end_date = date_range[-1]
        else:
            start_date = None
            end_date = None
    except Exception:
        start_date = None
        end_date = None

    # Strategy name
    try:
        strategy_name = getattr(system, "name", "pysystemtrade_strategy")
    except Exception:
        strategy_name = "pysystemtrade_strategy"

    # Instrument universe
    try:
        instrument_list = system.config.instruments
    except Exception:
        instrument_list = []

    config = {
        "experiment_id": f"pysystemtrade_{id(system)}",
        "strategy_name": strategy_name,
        "engine": "pysystemtrade",
        "engine_version": _get_pysystemtrade_version(),
        "python_version": (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
        "git_commit": "",
        "instrument_universe": instrument_list,
        "start_date": start_date,
        "end_date": end_date,
        "capital": 100_000.0,  # Default; override via overrides
        "currency": "USD",
        "risk_target_annual_pct": 20.0,
        "data_sources": ["pysystemtrade"],
        "config_overrides": overrides or {},
    }

    if overrides:
        config.update(overrides)

    return config


def _get_pysystemtrade_version() -> str:
    """Get installed pysystemtrade version."""
    try:
        import pysystemtrade

        return getattr(pysystemtrade, "__version__", "unknown")
    except Exception:
        return "unknown"


def extract_backtest_data(system: Any) -> dict[str, Any]:
    """Extract BacktestData-compatible dict from a pysystemtrade System object.

    Extracts portfolio_returns, instrument_pnl, positions from the system's
    backtest results.

    Args:
        system: pysystemtrade System object

    Returns:
        dict suitable for BacktestData.model_validate()
    """
    _check_pysystemtrade()

    import pandas as pd

    # Try to get results from system
    # pysystemtrade stores results in system.backtest or system.result
    backtest = getattr(system, "backtest", None)
    if backtest is None:
        backtest = getattr(system, "result", None)

    # Portfolio returns
    if backtest is not None:
        try:
            portfolio_returns = backtest.portfolio.returns()
        except Exception:
            portfolio_returns = _extract_from_system_results(system, "portfolio_returns")

        if portfolio_returns is not None and not isinstance(
            portfolio_returns.index, pd.DatetimeIndex
        ):
            portfolio_returns = None
    else:
        portfolio_returns = None

    # Instrument PnL
    instrument_pnl = _extract_from_system_results(system, "instrument_pnl")

    # Positions
    positions = _extract_from_system_results(system, "positions")

    # Instrument metadata
    instrument_meta = _extract_instrument_meta(system)

    result = {
        "portfolio_returns": portfolio_returns,
        "instrument_pnl": instrument_pnl if instrument_pnl is not None else pd.DataFrame(),
        "positions": positions if positions is not None else pd.DataFrame(),
        "instrument_meta": instrument_meta,
        "instrument_returns": {},
        "benchmark_returns": None,
    }

    return result


def _extract_from_system_results(system: Any, key: str) -> Any:
    """Try to extract a result from the system using various attribute paths."""

    # Try direct backtest attribute
    backtest = getattr(system, "backtest", None) or getattr(system, "result", None)

    if backtest is not None:
        # Try .get() dict-like access
        if hasattr(backtest, "get"):
            try:
                val = backtest.get(key)
                if val is not None:
                    return val
            except Exception:
                pass

        # Try direct attribute
        try:
            val = getattr(backtest, key, None)
            if val is not None:
                return val
        except Exception:
            pass

    # Try system-level attributes
    for attr in ["raw_data", "data", "results"]:
        try:
            obj = getattr(system, attr, None)
            if obj is not None and hasattr(obj, "get"):
                val = obj.get(key)
                if val is not None:
                    return val
        except Exception:
            continue

    logger.warning("Could not extract %s from pysystemtrade System", key)
    return None


def _extract_instrument_meta(system: Any) -> dict[str, dict[str, Any]]:
    """Extract instrument metadata from system config."""
    instrument_meta = {}

    try:
        instruments = getattr(system.config, "instruments", [])
    except Exception:
        instruments = []

    for code in instruments:
        instrument_meta[code] = {
            "code": code,
            "name": code,
            "sector": "",
            "group": "",
            "asset_class": "",
            "exchange": "",
            "point_value": 1.0,
            "currency": "USD",
        }

    return instrument_meta


def load_instrument_map() -> dict[str, dict[str, str]]:
    """Load the instrument metadata YAML map.

    Returns:
        dict mapping instrument code → metadata dict
    """
    try:
        import yaml  # type: ignore[import-untyped]

        from backtest_report.render import get_template_dir

        yaml_path = get_template_dir().parent / "adapters" / "instrument_map.yaml"
        if yaml_path.exists():
            with yaml_path.open() as f:
                return yaml.safe_load(f) or {}
    except Exception:
        pass

    return {}


def system_to_backtest_data(system: Any) -> tuple[Any, Any]:
    """Convert a pysystemtrade System to BacktestData and BacktestConfig.

    Returns:
        tuple of (BacktestData, BacktestConfig)
    """
    _check_pysystemtrade()

    from backtest_report.models import BacktestConfig, BacktestData

    config_dict = extract_backtest_config(system)
    config = BacktestConfig.model_validate(config_dict)

    data_dict = extract_backtest_data(system)
    data = BacktestData.model_validate(data_dict)

    return data, config
