# backtest-report

Generate standardised PDF backtest reports from trading system data.

## Installation

```bash
pip install backtest-report
# or with optional dependencies:
pip install backtest-report[pysystemtrade]  # pysystemtrade System pickle support
pip install backtest-report[parquet]        # PyArrow integration
pip install backtest-report[dev]            # development tools
```

Or install from source:

```bash
git clone https://github.com/samirsheldenkar/backtest-report.git
cd backtest-report
make install
```

## Quick Start

### From experiment directory (Parquet files)

```python
from backtest_report import generate_report

generate_report(
    experiment_dir="./my-backtest",
    output_path="./report.pdf",
)
```

Or via CLI:

```bash
backtest-report generate ./my-backtest -o report.pdf
```

### From a pysystemtrade System pickle

```python
from backtest_report import from_pysystemtrade

from_pysystemtrade(
    system_path="./system.pkl",
    output_path="./report.pdf",
)
```

## CLI Commands

```bash
backtest-report generate <experiment-dir>    # Generate PDF report
backtest-report sections                      # List available sections
backtest-report validate <experiment-dir>     # Check directory completeness
backtest-report export-parquet <dir> <file>   # Export to portable Parquet
```

### Section Filtering

```bash
backtest-report generate ./my-backtest \
    --sections header portfolio_pnl monthly_returns portfolio_stats \
    -o report.pdf
```

## Project Structure

```
src/backtest_report/
├── __init__.py          # Package init, version
├── __main__.py          # Click CLI entry point
├── models.py            # Pydantic models: BacktestConfig, BacktestData, etc.
├── persist.py           # Parquet-first persistence layer
├── portfolio.py         # Portfolio sections (equity curve, drawdown, etc.)
├── instrument.py        # Per-instrument sections
├── positions.py         # Position heatmap and attribution
├── header.py            # Report header section
├── appendix.py          # Appendix section (config dump, checksums)
├── render.py           # Jinja2 HTML assembly + WeasyPrint PDF
├── report.py           # BacktestReport orchestrator
├── remote.py            # Remote SCP persistence
├── adapters/
│   ├── pysystemtrade.py   # pysystemtrade System → BacktestData
│   └── instrument_map.yaml # Instrument metadata
└── templates/
    ├── style.css           # CSS design system
    ├── report.html         # Jinja2 master template
    └── sections/           # Section templates
```

## Development

```bash
make install    # pip install -e ".[dev,parquet]"
make lint       # ruff check
make format     # ruff format
make typecheck  # mypy
make test       # pytest -v --cov=backtest_report
make clean      # remove build artifacts
```

Run all checks:

```bash
make lint typecheck test
```

## Report Sections

| Section | Description |
|---------|-------------|
| `header` | Dark banner with experiment metadata |
| `portfolio_pnl` | Equity curve + drawdown charts |
| `monthly_returns` | Year × month returns heatmap table |
| `portfolio_stats` | 15 key metrics (Sharpe, max DD, etc.) |
| `rolling_stats` | Rolling Sharpe, 3yr return, beta charts |
| `instrument_pnl` | Per-instrument PnL small multiples |
| `instrument_table` | Per-instrument statistics table |
| `position_snapshot` | Time × instrument position heatmap |
| `attribution` | Return attribution by instrument/sector |
| `appendix` | Config dump, checksums, environment info |

## Configuration

Remote settings can be configured via:

- Environment variables: `BACKTEST_REMOTE_HOST`, `BACKTEST_REMOTE_USER`, etc.
- `.backtest-report.yaml` in your home or project directory

## Requirements

- Python 3.10+
- pandas >= 2.0
- matplotlib >= 3.7
- quantstats >= 0.0.62
- jinja2 >= 3.1
- weasyprint >= 60
- pydantic >= 2.0
- click >= 8.0