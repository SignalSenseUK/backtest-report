"""Unit tests for remote persistence layer."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from backtest_report.remote import (
    DEFAULT_REMOTE_HOST,
    DEFAULT_REMOTE_PORT,
    DEFAULT_REMOTE_USER,
    load_remote_config,
    read_remote_experiment,
    write_remote_report,
)


class TestLoadRemoteConfig:
    def test_defaults_when_no_file_or_env(self) -> None:
        cfg = load_remote_config()
        assert cfg["remote_host"] == DEFAULT_REMOTE_HOST
        assert cfg["remote_user"] == DEFAULT_REMOTE_USER
        assert cfg["remote_port"] == DEFAULT_REMOTE_PORT

    def test_env_var_overrides(self) -> None:
        with patch.dict(os.environ, {
            "BACKTEST_REMOTE_HOST": "custom.example.com",
            "BACKTEST_REMOTE_USER": "myuser",
            "BACKTEST_REMOTE_PORT": "2222",
        }):
            cfg = load_remote_config()
            assert cfg["remote_host"] == "custom.example.com"
            assert cfg["remote_user"] == "myuser"
            assert cfg["remote_port"] == 2222


class TestReadRemoteExperiment:
    def test_scp_called_with_correct_args(self, tmp_path: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = None
            read_remote_experiment(
                "/remote/dir", tmp_path,
                remote_host="myhost", remote_user="myuser", remote_port=2222,
            )
            args = mock_run.call_args[0][0]
            assert args[0] == "scp"
            assert args[1] == "-P"
            assert args[2] == "2222"
            assert "-r" in args
            assert "myuser@myhost:/remote/dir/*" in args
            assert str(tmp_path) + "/" in args

    def test_scp_failure_raises_runtime_error(self, tmp_path: Path) -> None:
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                255, ["scp"], stderr="connection refused"
            )
            with pytest.raises(RuntimeError, match="connection refused"):
                read_remote_experiment("/remote/dir", tmp_path)


class TestWriteRemoteReport:
    def test_scp_upload_called_correctly(self, tmp_path: Path) -> None:
        pdf = tmp_path / "report.pdf"
        pdf.write_text("%PDF-fake")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = None
            write_remote_report(
                pdf, "/remote/dir",
                remote_host="myhost", remote_user="myuser", remote_port=2222,
            )
            args = mock_run.call_args[0][0]
            assert args[0] == "scp"
            assert args[1] == "-P"
            assert args[2] == "2222"
            assert str(pdf) in args
            assert "myuser@myhost:/remote/dir/" in args

    def test_scp_failure_raises_runtime_error(self, tmp_path: Path) -> None:
        import subprocess

        pdf = tmp_path / "report.pdf"
        pdf.write_text("%PDF-fake")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                255, ["scp"], stderr="upload failed"
            )
            with pytest.raises(RuntimeError, match="upload failed"):
                write_remote_report(pdf, "/remote/dir")