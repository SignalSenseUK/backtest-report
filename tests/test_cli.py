"""Unit tests for CLI commands."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from backtest_report.__main__ import cli, generate, sections, validate


@pytest.fixture
def cli_runner():
    return CliRunner()


class TestCli:
    def test_cli_version(self, cli_runner) -> None:
        result = cli_runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_cli_verbose_flag(self, cli_runner) -> None:
        result = cli_runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "--verbose" in result.output


class TestSections:
    def test_sections_lists_all(self, cli_runner) -> None:
        result = cli_runner.invoke(sections, [])
        assert result.exit_code == 0
        for section in [
            "header", "portfolio_pnl", "monthly_returns", "portfolio_stats",
            "rolling_stats", "instrument_pnl", "instrument_table",
            "position_snapshot", "attribution", "appendix",
        ]:
            assert section in result.output


class TestValidate:
    def test_validate_complete_dir(self, cli_runner, tmp_path: Path) -> None:
        # Create a complete experiment directory
        from backtest_report.persist import write_experiment_dir
        from tests.conftest import FIXTURES_DIR

        import pandas as pd
        from backtest_report.models import BacktestConfig

        dates = pd.date_range("2020-01-02", periods=100, freq="B")
        returns = pd.Series([0.01] * 100, index=dates, name="portfolio_returns")
        pnl = pd.DataFrame([[1.0] * 3] * 100, index=dates, columns=["A", "B", "C"])
        positions = pd.DataFrame([[1] * 3] * 100, index=dates, columns=["A", "B", "C"])

        config = BacktestConfig(
            experiment_id="test",
            strategy_name="Test",
            start_date=dates[0].date(),
            end_date=dates[-1].date(),
            capital=100_000.0,
            risk_target_annual_pct=20.0,
            instrument_universe=["A", "B", "C"],
        )

        from backtest_report.models import BacktestData

        data = BacktestData(
            portfolio_returns=returns,
            instrument_pnl=pnl,
            positions=positions,
        )
        write_experiment_dir(tmp_path, data, config, {})
        result = cli_runner.invoke(validate, [str(tmp_path)])
        assert result.exit_code == 0
        assert "Valid: ✓" in result.output

    def test_validate_missing_dir(self, cli_runner, tmp_path: Path) -> None:
        result = cli_runner.invoke(validate, [str(tmp_path / "nonexistent")])
        assert result.exit_code == 2  # Click's usage error


class TestGenerate:
    def test_generate_requires_experiment_dir(self, cli_runner) -> None:
        result = cli_runner.invoke(generate, [])
        assert result.exit_code == 2

    def test_generate_nonexistent_dir(self, cli_runner, tmp_path: Path) -> None:
        result = cli_runner.invoke(
            generate,
            [str(tmp_path / "nonexistent"), "-o", str(tmp_path / "out.pdf")],
        )
        # Exit code 1 or 2 indicates an error condition
        assert result.exit_code in (1, 2)
