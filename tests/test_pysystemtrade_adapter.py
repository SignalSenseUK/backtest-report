"""Unit tests for pysystemtrade adapter."""
from __future__ import annotations

import pickle
from pathlib import Path

import pytest

from backtest_report.adapters.pysystemtrade import (
    PySystemTradeNotInstalled,
    load_instrument_map,
)


class TestCheckPySystemTrade:
    def test_raises_when_not_installed(self) -> None:
        # Since pysystemtrade is NOT installed, _check_pysystemtrade should raise
        with pytest.raises(PySystemTradeNotInstalled) as exc_info:
            from backtest_report.adapters.pysystemtrade import _check_pysystemtrade

            _check_pysystemtrade()
        assert "pip install backtest-report[pysystemtrade]" in str(exc_info.value)


class TestLoadInstrumentMap:
    def test_returns_dict(self) -> None:
        result = load_instrument_map()
        assert isinstance(result, dict)

    def test_contains_known_instruments(self) -> None:
        result = load_instrument_map()
        for code in ["EDOLLAR", "US10", "GOLD", "SP500"]:
            if code in result:
                assert "name" in result[code]
                assert "sector" in result[code]


class TestLoadSystemErrors:
    def test_raises_when_not_installed(self, tmp_path: Path) -> None:
        from backtest_report.adapters.pysystemtrade import load_system

        # Create a dummy pickle file (a simple built-in type)
        pkl_path = tmp_path / "system.pkl"
        pkl_path.write_bytes(pickle.dumps({"test": "data"}))

        # Should raise PySystemTradeNotInstalled since pysystemtrade isn't installed
        with pytest.raises(PySystemTradeNotInstalled):
            load_system(pkl_path)