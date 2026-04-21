"""Unit tests for persistence layer."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from backtest_report.models import BacktestData, BacktestMeta, InstrumentMeta
from backtest_report.persist import (
    compute_checksum,
    read_experiment_dir,
    validate_experiment_dir,
    write_experiment_dir,
)


def _make_backtest_data() -> BacktestData:
    """Create a minimal BacktestData for testing."""
    dates = pd.date_range("2020-01-02", periods=100, freq="B")
    returns = pd.Series(np.random.randn(100) * 0.01, index=dates, name="portfolio_returns")
    pnl = pd.DataFrame(
        np.random.randn(100, 3) * 1000,
        index=dates,
        columns=["ES", "NQ", "YM"],
    )
    positions = pd.DataFrame(
        np.random.randint(-10, 10, (100, 3)),
        index=dates,
        columns=["ES", "NQ", "YM"],
    )
    return BacktestData(
        portfolio_returns=returns,
        instrument_pnl=pnl,
        positions=positions,
        instrument_meta={
            "ES": InstrumentMeta(code="ES", name="E-mini S&P 500"),
            "NQ": InstrumentMeta(code="NQ", name="E-mini NASDAQ"),
            "YM": InstrumentMeta(code="YM", name="Dow Jones"),
        },
    )


class TestComputeChecksum:
    def test_returns_sha256_prefix(self, tmp_path: Path) -> None:
        p = tmp_path / "test.txt"
        p.write_text("hello")
        cs = compute_checksum(p)
        assert cs.startswith("sha256:")

    def test_consistent_for_same_content(self, tmp_path: Path) -> None:
        p = tmp_path / "test.txt"
        p.write_text("hello")
        cs1 = compute_checksum(p)
        cs2 = compute_checksum(p)
        assert cs1 == cs2

    def test_different_for_different_content(self, tmp_path: Path) -> None:
        p = tmp_path / "test.txt"
        p.write_text("hello")
        cs1 = compute_checksum(p)
        p.write_text("world")
        cs2 = compute_checksum(p)
        assert cs1 != cs2


class TestWriteReadExperimentDir:
    def test_roundtrip(self, tmp_path: Path) -> None:
        from backtest_report.models import BacktestConfig

        data = _make_backtest_data()
        config = BacktestConfig(
            experiment_id="test-roundtrip",
            strategy_name="TestStrategy",
            start_date=pd.Timestamp("2020-01-02").date(),
            end_date=pd.Timestamp("2020-06-01").date(),
            capital=500_000.0,
            risk_target_annual_pct=20.0,
            instrument_universe=["ES", "NQ", "YM"],
        )
        checksums = {"portfolio_returns": "sha256:abc"}

        write_experiment_dir(tmp_path, data, config, checksums)

        # Verify files exist
        assert (tmp_path / "portfolio_returns.parquet").exists()
        assert (tmp_path / "instrument_pnl.parquet").exists()
        assert (tmp_path / "positions.parquet").exists()
        assert (tmp_path / "instrument_meta.json").exists()
        assert (tmp_path / "config.yaml").exists()
        assert (tmp_path / "data_checksums.json").exists()
        assert (tmp_path / "meta.json").exists()

        # Read back
        data2, meta2 = read_experiment_dir(tmp_path)

        # Check portfolio returns
        pd.testing.assert_index_equal(data.portfolio_returns.index, data2.portfolio_returns.index)
        np.testing.assert_allclose(
            data.portfolio_returns.values, data2.portfolio_returns.values, rtol=1e-6
        )

        # Check instrument_pnl shape
        assert data2.instrument_pnl.shape == (100, 3)

        # Check positions shape
        assert data2.positions.shape == (100, 3)

        # Check instrument_meta
        assert "ES" in data2.instrument_meta
        assert data2.instrument_meta["ES"].name == "E-mini S&P 500"

        # Check meta
        assert meta2.config.experiment_id == "test-roundtrip"

    def test_config_yaml_content(self, tmp_path: Path) -> None:
        from backtest_report.models import BacktestConfig

        data = _make_backtest_data()
        config = BacktestConfig(
            experiment_id="yaml-test",
            strategy_name="YAML Test",
            start_date=pd.Timestamp("2020-01-02").date(),
            end_date=pd.Timestamp("2020-06-01").date(),
            capital=250_000.0,
            risk_target_annual_pct=15.0,
            instrument_universe=["ES"],
        )
        checksums = {}

        write_experiment_dir(tmp_path, data, config, checksums)

        yaml_content = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert yaml_content["experiment_id"] == "yaml-test"
        assert yaml_content["capital"] == 250_000.0

    def test_instrument_meta_json(self, tmp_path: Path) -> None:
        from backtest_report.models import BacktestConfig

        data = _make_backtest_data()
        config = BacktestConfig(
            experiment_id="meta-json-test",
            strategy_name="Test",
            start_date=pd.Timestamp("2020-01-02").date(),
            end_date=pd.Timestamp("2020-06-01").date(),
            capital=100_000.0,
            risk_target_annual_pct=20.0,
            instrument_universe=["ES", "NQ", "YM"],
        )
        checksums = {}

        write_experiment_dir(tmp_path, data, config, checksums)

        meta_json = json.loads((tmp_path / "instrument_meta.json").read_text())
        assert "ES" in meta_json
        assert meta_json["ES"]["name"] == "E-mini S&P 500"


class TestValidateExperimentDir:
    def test_valid_complete_dir(self, tmp_path: Path) -> None:
        from backtest_report.models import BacktestConfig

        data = _make_backtest_data()
        config = BacktestConfig(
            experiment_id="validate-test",
            strategy_name="Test",
            start_date=pd.Timestamp("2020-01-02").date(),
            end_date=pd.Timestamp("2020-06-01").date(),
            capital=100_000.0,
            risk_target_annual_pct=20.0,
            instrument_universe=["ES"],
        )
        checksums = {}
        write_experiment_dir(tmp_path, data, config, checksums)

        result = validate_experiment_dir(tmp_path)
        assert result["valid"] is True
        assert len(result["missing"]) == 0
        assert result["strategy"] == "parquet"

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = validate_experiment_dir(tmp_path)
        assert result["valid"] is False
        assert result["strategy"] == "none"

    def test_partial_directory(self, tmp_path: Path) -> None:
        (tmp_path / "portfolio_returns.parquet").write_text("dummy")
        result = validate_experiment_dir(tmp_path)
        assert result["valid"] is False
        assert "portfolio_returns.parquet" in result["found"]
        assert "instrument_pnl.parquet" in result["missing"]


class TestReadExperimentDirErrors:
    def test_missing_directory_raises(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "does_not_exist"
        with pytest.raises(FileNotFoundError) as exc_info:
            read_experiment_dir(nonexistent)
        assert "Experiment directory incomplete" in str(exc_info.value)

    def test_no_parquet_no_pickle_raises(self, tmp_path: Path) -> None:
        # Create directory with unrelated file
        (tmp_path / "random.txt").write_text("hello")
        with pytest.raises(FileNotFoundError) as exc_info:
            read_experiment_dir(tmp_path)
        assert "No parquet files and no system.pkl found" in str(exc_info.value)