# Usage Guide

## Installation

```bash
pip install backtest-report
```

With optional dependencies:

```bash
pip install backtest-report[pysystemtrade]  # pysystemtrade integration
pip install backtest-report[parquet]         # PyArrow for Parquet files
pip install backtest-report[dev]             # testing + linting
```

## Generating a Report

### From Parquet Files

Place the following files in an experiment directory:

- `portfolio_returns.parquet` — pd.Series with DatetimeIndex (daily returns)
- `instrument_pnl.parquet` — pd.DataFrame with DatetimeIndex × instrument_code
- `positions.parquet` — pd.DataFrame with DatetimeIndex × instrument_code
- `instrument_meta.json` — dict of instrument metadata (optional)
- `meta.json` — BacktestMeta JSON (optional, auto-generated if missing)
- `config.yaml` — BacktestConfig YAML (optional, required fields only)

Then:

```bash
backtest-report generate ./experiments/my-backtest -o report.pdf
```

Or programmatically:

```python
from backtest_report import generate_report

generate_report(
    experiment_dir="./experiments/my-backtest",
    output_path="report.pdf",
)
```

### From a Python Session

```python
from backtest_report import BacktestReport
from backtest_report.models import BacktestData, BacktestMeta

# Build BacktestData from your data
data = BacktestData(
    portfolio_returns=my_returns,
    instrument_pnl=my_pnl,
    positions=my_positions,
)

meta = BacktestMeta(
    config=my_config,
    generated_at=datetime.now(),
    report_version="0.1.0",
)

report = BacktestReport(data=data, meta=meta)
report.generate(output_path="report.pdf")
```

### From pysystemtrade

```python
from backtest_report import from_pysystemtrade

from_pysystemtrade(
    system_path="./system.pkl",
    output_path="report.pdf",
)
```

## CLI Commands

### `generate`

```bash
backtest-report generate <experiment-dir> [OPTIONS]

Options:
  -o, --output PATH          Output PDF path
  --sections NAME...         Include specific sections only
  --filter TEXT              Comma-separated section IDs
  --template-dir PATH         Override template directory
  -v, --verbose              Enable debug logging
```

### `sections`

Lists all available section IDs.

```bash
backtest-report sections
```

### `validate`

Checks an experiment directory for completeness.

```bash
backtest-report validate ./experiments/my-backtest
```

### `export-parquet`

Bundles experiment data into a single portable Parquet file.

```bash
backtest-report export-parquet ./my-backtest ./backup.parquet
```

## Section Filtering

Generate only specific sections:

```bash
backtest-report generate ./my-backtest \
    --sections header portfolio_pnl portfolio_stats appendix \
    -o summary.pdf
```

Available sections: `header`, `portfolio_pnl`, `monthly_returns`, `portfolio_stats`, `rolling_stats`, `instrument_pnl`, `instrument_table`, `position_snapshot`, `attribution`, `appendix`.

## Remote Persistence

Configure remote SCP settings via:

**Environment variables:**
```bash
export BACKTEST_REMOTE_HOST=results.example.com
export BACKTEST_REMOTE_USER=backtest
export BACKTEST_REMOTE_PORT=22
export BACKTEST_REMOTE_DIR=/var/results
```

**Or via `~/.backtest-report.yaml`:**
```yaml
remote:
  remote_host: results.example.com
  remote_user: backtest
  remote_port: 22
  remote_dir: /var/results
```
