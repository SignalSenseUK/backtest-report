"""Additional CLI tests for export-parquet command."""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from backtest_report.__main__ import cli


@pytest.fixture
def cli_runner():
    return CliRunner()


class TestExportParquet:
    def test_export_parquet_help(self, cli_runner) -> None:
        result = cli_runner.invoke(cli, ["export-parquet", "--help"])
        assert result.exit_code == 0
        assert "export-parquet" in result.output

    def test_export_parquet_requires_args(self, cli_runner) -> None:
        result = cli_runner.invoke(cli, ["export-parquet"])
        assert result.exit_code == 2
