"""Local persistence layer for experiment directories.

Parquet-first strategy: read/write DataFrames as Parquet, metadata as JSON/YAML.
Supports optional pickle fallback via pysystemtrade adapter.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from backtest_report.models import BacktestConfig, BacktestData, BacktestMeta, InstrumentMeta

logger = logging.getLogger("backtest_report")

# Expected files in an experiment directory
EXPERIMENT_FILES = [
    "portfolio_returns.parquet",
    "instrument_pnl.parquet",
    "positions.parquet",
    "instrument_meta.json",
    "meta.json",
    "config.yaml",
    "data_checksums.json",
]


def compute_checksum(path: Path) -> str:
    """Compute SHA-256 checksum of a file.

    Returns format: "sha256:<hex>"
    """
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, default=str))


def _instrument_meta_from_dict(d: dict[str, Any]) -> dict[str, InstrumentMeta]:
    return {code: InstrumentMeta.model_validate(meta) for code, meta in d.items()}


def _instrument_meta_to_dict(meta: dict[str, InstrumentMeta]) -> dict[str, Any]:
    return {code: m.model_dump() for code, m in meta.items()}


def write_experiment_dir(
    path: Path,
    data: BacktestData,
    config: BacktestConfig,
    data_checksums: dict[str, str],
    system: Any = None,
) -> None:
    """Write an experiment directory.

    Creates the directory if it doesn't exist and writes all data files:
    - portfolio_returns.parquet
    - instrument_pnl.parquet
    - positions.parquet
    - instrument_meta.json
    - config.yaml
    - data_checksums.json
    - meta.json (auto-generated from BacktestMeta)
    - system.pkl (optional, only if system is provided)

    Args:
        path: Directory path to write to (created if missing)
        data: BacktestData instance
        config: BacktestConfig instance
        data_checksums: dict of filename → checksum strings
        system: Optional pysystemtrade System object to pickle (logged as security warning)
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    # Write DataFrames as Parquet
    portfolio_path = path / "portfolio_returns.parquet"
    data.portfolio_returns.to_frame().to_parquet(portfolio_path)
    logger.info("Written: %s", portfolio_path)

    instr_pnl_path = path / "instrument_pnl.parquet"
    data.instrument_pnl.to_parquet(instr_pnl_path)
    logger.info("Written: %s", instr_pnl_path)

    positions_path = path / "positions.parquet"
    data.positions.to_parquet(positions_path)
    logger.info("Written: %s", positions_path)

    # Write instrument metadata as JSON
    instr_meta_path = path / "instrument_meta.json"
    _write_json(instr_meta_path, _instrument_meta_to_dict(data.instrument_meta))
    logger.info("Written: %s", instr_meta_path)

    # Write config as YAML
    config_path = path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config.model_dump(), default_flow_style=False))
    logger.info("Written: %s", config_path)

    # Write data checksums
    checksums_path = path / "data_checksums.json"
    _write_json(checksums_path, data_checksums)
    logger.info("Written: %s", checksums_path)

    # Write auto-generated meta.json
    from backtest_report import __version__

    meta = BacktestMeta(
        config=config,
        generated_at=_now(),
        report_version=__version__,
        data_checksums=data_checksums,
        notes="",
    )
    meta_path = path / "meta.json"
    meta_path.write_text(json.dumps(meta.model_dump(), indent=2, default=str))
    logger.info("Written: %s", meta_path)

    # Optional pickle
    if system is not None:
        import pickle

        pickle_path = path / "system.pkl"
        pickle_path.write_bytes(pickle.dumps(system))
        logger.warning(
            "Written system pickle: %s (security note: pickle can execute arbitrary code)",
            pickle_path,
        )


def read_experiment_dir(path: Path) -> tuple[BacktestData, BacktestMeta]:
    """Read an experiment directory.

    Strategy 1 (Parquet-first): if portfolio_returns.parquet exists, read all Parquet + JSON/YAML files.

    Strategy 2 (Pickle fallback): if Parquet files are missing but system.pkl exists,
    attempt to use pysystemtrade adapter. If adapter is not installed, raise ImportError.

    Raises:
        FileNotFoundError: if neither strategy succeeds, listing found vs expected files

    Returns:
        tuple of (BacktestData, BacktestMeta)
    """
    path = Path(path)

    parquet_strategy = (path / "portfolio_returns.parquet").exists()
    pickle_strategy = (path / "system.pkl").exists()

    if parquet_strategy:
        logger.info("Reading experiment dir (Parquet strategy): %s", path)
        return _read_parquet_strategy(path)
    elif pickle_strategy:
        logger.info("Reading experiment dir (Pickle fallback strategy): %s", path)
        return _read_pickle_strategy(path)
    else:
        found = [f.name for f in path.iterdir()] if path.exists() else []
        missing = [f for f in EXPERIMENT_FILES if not (path / f).exists()]
        raise FileNotFoundError(
            f"Experiment directory incomplete: {path}\n"
            f"Found files: {found}\n"
            f"Missing files: {missing}\n"
            f"No parquet files and no system.pkl found."
        )


def _read_parquet_strategy(path: Path) -> tuple[BacktestData, BacktestMeta]:
    """Read using Parquet + JSON/YAML files."""
    # Read DataFrames
    portfolio_returns = pd.read_parquet(path / "portfolio_returns.parquet").iloc[:, 0]
    instrument_pnl = pd.read_parquet(path / "instrument_pnl.parquet")
    positions = pd.read_parquet(path / "positions.parquet")

    # Read instrument metadata
    instr_meta_raw = _read_json(path / "instrument_meta.json")
    instrument_meta = _instrument_meta_from_dict(instr_meta_raw)

    # Read meta.json
    meta_dict = _read_json(path / "meta.json")
    meta = BacktestMeta.model_validate(meta_dict)

    data = BacktestData(
        portfolio_returns=portfolio_returns,
        instrument_pnl=instrument_pnl,
        positions=positions,
        instrument_meta=instrument_meta,
    )

    return data, meta


def _read_pickle_strategy(path: Path) -> tuple[BacktestData, BacktestMeta]:
    """Read using pysystemtrade pickle fallback."""
    try:
        from backtest_report.adapters.pysystemtrade import load_system

        system = load_system(path / "system.pkl")
        from backtest_report.adapters.pysystemtrade import extract_backtest_data, extract_backtest_config

        config = extract_backtest_config(system)
        data = extract_backtest_data(system)
        meta = BacktestMeta(
            config=config,
            generated_at=_now(),
            report_version="unknown",
            data_checksums={},
            notes="Loaded from pysystemtrade pickle",
        )
        return data, meta
    except ImportError as e:
        raise ImportError(
            "pysystemtrade adapter required for pickle fallback but is not installed.\n"
            "Install with: pip install backtest-report[pysystemtrade]\n"
            f"Original error: {e}"
        ) from e


def validate_experiment_dir(path: Path) -> dict[str, Any]:
    """Check which expected files exist in an experiment directory.

    Returns:
        dict with keys:
            - valid (bool): True if all required files present
            - found (list[str]): files that exist
            - missing (list[str]): expected files not found
            - strategy (str): "parquet", "pickle", or "none"
    """
    path = Path(path)
    found = []
    missing = []

    for fname in EXPERIMENT_FILES:
        if (path / fname).exists():
            found.append(fname)
        else:
            missing.append(fname)

    parquet_ok = all((path / f).exists() for f in ["portfolio_returns.parquet", "instrument_pnl.parquet", "positions.parquet"])
    pickle_ok = (path / "system.pkl").exists()

    if parquet_ok:
        strategy = "parquet"
    elif pickle_ok:
        strategy = "pickle"
    else:
        strategy = "none"

    return {
        "valid": len(missing) == 0,
        "found": found,
        "missing": missing,
        "strategy": strategy,
    }


def _now() -> datetime:
    return datetime.now()