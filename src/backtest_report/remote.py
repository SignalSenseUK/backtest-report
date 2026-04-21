"""Remote persistence layer — SCP/rsync read/write operations."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("backtest_report")

DEFAULT_REMOTE_USER = "backtest"
DEFAULT_REMOTE_HOST = "results.example.com"
DEFAULT_REMOTE_PORT = 22


def read_remote_experiment(
    remote_dir: str,
    local_tmp: Path | None = None,
    remote_host: str = DEFAULT_REMOTE_HOST,
    remote_user: str = DEFAULT_REMOTE_USER,
    remote_port: int = DEFAULT_REMOTE_PORT,
) -> Path:
    """Download experiment files from remote via SCP to a local temp directory.

    Args:
        remote_dir: absolute path on remote host
        local_tmp: local temporary directory (created if None)
        remote_host: SSH hostname
        remote_user: SSH username
        remote_port: SSH port

    Returns:
        Path to local temp directory containing downloaded files
    """
    import tempfile

    if local_tmp is None:
        local_tmp = Path(tempfile.mkdtemp())

    scp_cmd = [
        "scp",
        "-P", str(remote_port),
        "-r",
        f"{remote_user}@{remote_host}:{remote_dir}/*",
        str(local_tmp) + "/",
    ]

    try:
        subprocess.run(scp_cmd, capture_output=True, text=True, check=True)
        logger.info("Downloaded remote experiment to: %s", local_tmp)
    except subprocess.CalledProcessError as e:
        logger.error("SCP download failed: %s", e.stderr)
        raise RuntimeError(
            f"Failed to download from remote: {e.stderr}\n"
            f"Hint: Check SSH connectivity and that {remote_dir} exists on {remote_host}"
        ) from e
    except FileNotFoundError:
        raise RuntimeError(
            "'scp' command not found. Ensure OpenSSH is installed and in PATH."
        )

    return local_tmp


def write_remote_report(
    local_pdf: Path,
    remote_dir: str,
    remote_host: str = DEFAULT_REMOTE_HOST,
    remote_user: str = DEFAULT_REMOTE_USER,
    remote_port: int = DEFAULT_REMOTE_PORT,
) -> None:
    """Upload a generated PDF report to a remote directory via SCP.

    Args:
        local_pdf: path to local PDF file
        remote_dir: absolute path on remote host
        remote_host: SSH hostname
        remote_user: SSH username
        remote_port: SSH port
    """
    scp_cmd = [
        "scp",
        "-P", str(remote_port),
        str(local_pdf),
        f"{remote_user}@{remote_host}:{remote_dir}/",
    ]

    try:
        subprocess.run(scp_cmd, capture_output=True, text=True, check=True)
        logger.info("Report uploaded successfully")
    except subprocess.CalledProcessError as e:
        logger.error("SCP upload failed: %s", e.stderr)
        raise RuntimeError(
            f"Failed to upload report: {e.stderr}\n"
            f"Hint: Check SSH connectivity and that {remote_dir} exists on {remote_host}"
        ) from e
    except FileNotFoundError:
        raise RuntimeError(
            "'scp' command not found. Ensure OpenSSH is installed and in PATH."
        )


def load_remote_config() -> dict[str, Any]:
    """Load remote settings from config cascade.

    Priority (highest to lowest):
    1. Environment variables: BACKTEST_REMOTE_HOST, BACKTEST_REMOTE_USER, etc.
    2. .backtest-report.yaml in current directory or home directory
    3. Defaults

    Returns:
        dict with remote connection settings
    """
    import os

    config: dict[str, Any] = {
        "remote_host": DEFAULT_REMOTE_HOST,
        "remote_user": DEFAULT_REMOTE_USER,
        "remote_port": DEFAULT_REMOTE_PORT,
        "remote_dir": "",
    }

    # Load from YAML config file if present
    for config_file in [Path.cwd() / ".backtest-report.yaml", Path.home() / ".backtest-report.yaml"]:
        if config_file.exists():
            import yaml

            with config_file.open() as f:
                remote_cfg = yaml.safe_load(f) or {}
            config.update(remote_cfg.get("remote", {}))
            break

    # Override with environment variables
    for key in ("remote_host", "remote_user", "remote_port", "remote_dir"):
        env_key = f"BACKTEST_{key.upper()}"
        if env_key in os.environ:
            value = os.environ[env_key]
            if key == "remote_port":
                value = int(value)
            config[key] = value

    return config
