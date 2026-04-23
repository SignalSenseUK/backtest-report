import importlib.metadata
import logging

try:
    __version__ = importlib.metadata.version("backtest-report")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0-dev"

__all__ = [
    "cli",
    "report",
    "models",
    "adapters",
    "templates",
    # models
    "BacktestConfig",
    "BacktestData",
    "BacktestMeta",
    "InstrumentMeta",
    "SectionOutput",
]

logger = logging.getLogger("backtest_report")
