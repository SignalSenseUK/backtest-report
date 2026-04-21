---
title: Backtest Report — Implementation Specification
domain: trading
type: infra
created: 2026-04-19
updated: 2026-04-21 12:20:00
sources:
  - wiki/trading/infra/backtest-reporting.md
  - wiki/trading/infra/pysystemtrade.md
tags: [reporting, backtest, pdf, quantstats, specification, implementation]
status: draft
---

# Backtest Report — Implementation Specification

> **Repo**: `backtest-report` (to be created on Forgejo)
> **Language**: Python 3.10+
> **License**: MIT
> **Status**: Draft — ready for implementation

## 1. Overview

A standalone Python package that generates standardised, reproducible PDF backtest reports from persisted pysystemtrade `System` objects (or plain pandas DataFrames for engine-agnostic use). Uses QuantStats for metric computation and matplotlib for all chart generation, producing self-contained tear sheets.

**Design principles:**

1. **Engine-agnostic core** — the reporting pipeline does not import pysystemtrade at runtime. It accepts pre-extracted DataFrames (returns, positions, instruments) as its primary input. A thin adapter layer converts pysystemtrade `System` objects into these DataFrames.
2. **Reproducible** — every report embeds its config snapshot, data checksums, and git commit so any historical report can be regenerated.
3. **Composable sections** — each report section is a self-contained module that produces an HTML fragment. Sections can be added, removed, or reordered without touching others.
4. **No data in git** — `System` pickles and Parquet archives live on the hc4t server only. The repo contains code and templates.

---

## 2. Repository Structure

```
backtest-report/
├── pyproject.toml
├── README.md
├── LICENSE                          # MIT
├── Makefile                         # lint, test, build, install
├── src/
│   └── backtest_report/
│       ├── __init__.py              # version (via importlib.metadata), public API re-exports
│       ├── __main__.py              # Click CLI entry point
│       ├── report.py                # BacktestReport orchestrator
│       ├── models.py                # Pydantic data models (config, metadata) + dataclasses
│       ├── portfolio.py             # Portfolio charts (matplotlib) + metrics (qs.stats) → HTML
│       ├── instrument.py            # Per-instrument analysis → HTML fragment
│       ├── attribution.py           # Return attribution (by instrument, sector, group)
│       ├── positions.py             # Position heatmap + snapshot tables
│       ├── header.py                # Header section renderer (metadata display)
│       ├── appendix.py              # Appendix section renderer (config dump, checksums)
│       ├── render.py                # Jinja2 template assembly → full HTML → PDF via WeasyPrint
│       ├── persist.py               # Read/write experiment directories on hc4t
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── pysystemtrade.py     # System → BacktestData adapter (optional dependency)
│       │   └── instrument_map.yaml  # pysystemtrade code → InstrumentMeta mapping
│       └── templates/
│           ├── report.html          # Jinja2 master template
│           ├── fonts/
│           │   ├── Inter-Regular.woff2
│           │   ├── Inter-SemiBold.woff2
│           │   ├── JetBrainsMono-Regular.woff2
│           │   └── OFL.txt          # Font license
│           ├── sections/
│           │   ├── header.html
│           │   ├── portfolio.html
│           │   ├── monthly_returns.html
│           │   ├── portfolio_stats.html
│           │   ├── rolling_stats.html
│           │   ├── instrument_pnl.html
│           │   ├── instrument_table.html
│           │   ├── position_snapshot.html
│           │   ├── attribution.html
│           │   └── appendix.html
│           └── style.css
├── scripts/
│   └── generate_fixtures.py         # Create synthetic test data
├── tests/
│   ├── conftest.py                  # Fixtures: sample BacktestData, mock System
│   ├── test_report.py
│   ├── test_portfolio.py
│   ├── test_instrument.py
│   ├── test_attribution.py
│   ├── test_positions.py
│   ├── test_render.py
│   ├── test_persist.py
│   ├── test_pysystemtrade_adapter.py
│   └── fixtures/
│       ├── sample_portfolio_returns.parquet
│       ├── sample_instrument_returns.parquet
│       ├── sample_positions.parquet
│       └── sample_meta.json
└── docs/
    ├── architecture.md               # This spec (checked in as docs, not as wiki)
    └── usage.md                      # Quick-start guide
```

---

## 3. Data Models (`models.py`)

Models that require validation and serialisation use **Pydantic v2**. Internal data-passing structures use plain **dataclasses** to avoid Pydantic's restrictions on arbitrary types.

### 3.1 `BacktestConfig`

```python
from typing import Any

class BacktestConfig(BaseModel):
    experiment_id: str                # e.g. "sg-trend-proxy_20260419_153000"
    strategy_name: str                 # e.g. "SG Trend Proxy"
    engine: str = "pysystemtrade"      # or "quantconnect", "custom"
    engine_version: str = ""           # e.g. "1.8.0"
    python_version: str = ""
    git_commit: str = ""
    instrument_universe: list[str]     # e.g. ["EDOLLAR", "US10", "GOLD", ...]
    start_date: date
    end_date: date
    capital: float                     # initial capital in account currency
    currency: str = "USD"
    risk_target_annual_pct: float      # e.g. 20.0
    data_sources: list[str] = []       # e.g. ["pysystemtrade-csv", "eodhd"]
    config_overrides: dict[str, Any] = {}  # any non-default config values
```

### 3.2 `BacktestData`

The engine-agnostic input to the report pipeline. This is what `BacktestReport` actually consumes — no pysystemtrade imports required.

Uses `arbitrary_types_allowed` to permit pandas types in Pydantic, with `@field_validator` methods to validate expected structure.

```python
from pydantic import ConfigDict, field_validator

class BacktestData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Portfolio-level daily returns, zero-indexed by date
    portfolio_returns: pd.Series       # DatetimeIndex → float (daily % returns)

    # Per-instrument daily P&L in account currency
    instrument_pnl: pd.DataFrame       # DatetimeIndex × instrument_code → float

    # Per-instrument position sizes (number of contracts or notional)
    positions: pd.DataFrame             # DatetimeIndex × instrument_code → float

    # Instrument metadata (sector, group, asset class for attribution)
    instrument_meta: dict[str, InstrumentMeta]

    # Optional: per-instrument daily returns (for Sharpe/DD per instrument)
    instrument_returns: dict[str, pd.Series] = {}

    # Optional: benchmark returns for beta calculation in rolling stats
    # If None, the beta chart is omitted from the rolling stats section
    benchmark_returns: pd.Series | None = None

    @field_validator("portfolio_returns")
    @classmethod
    def validate_portfolio_returns(cls, v: pd.Series) -> pd.Series:
        if not isinstance(v.index, pd.DatetimeIndex):
            raise ValueError("portfolio_returns must have a DatetimeIndex")
        if v.empty:
            raise ValueError("portfolio_returns must not be empty")
        return v

    @field_validator("instrument_pnl", "positions")
    @classmethod
    def validate_dataframes(cls, v: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(v.index, pd.DatetimeIndex):
            raise ValueError("DataFrame must have a DatetimeIndex")
        return v

class InstrumentMeta(BaseModel):
    code: str                           # e.g. "EDOLLAR"
    name: str = ""                      # e.g. "Eurodollar"
    sector: str = ""                    # e.g. "Rates"
    group: str = ""                     # e.g. "STIR"
    asset_class: str = ""               # e.g. "Fixed Income"
    exchange: str = ""                   # e.g. "CME"
    point_value: float = 1.0
    currency: str = "USD"
```

### 3.3 `BacktestMeta`

```python
class BacktestMeta(BaseModel):
    config: BacktestConfig
    generated_at: datetime
    report_version: str                 # backtest_report package version
    data_checksums: dict[str, str] = {} # filename → "sha256:<hex_digest>"
    notes: str = ""
```

**Checksum format:** All checksums use SHA-256 and are stored in the format `"sha256:<hex_digest>"` for explicit algorithm identification and future-proofing.

### 3.4 Section Output

Each section module returns a `SectionOutput`. This is an **internal data-passing structure** that does not need Pydantic validation or serialisation, so it uses a plain `dataclass` to avoid pandas-in-Pydantic issues:

```python
from dataclasses import dataclass, field

@dataclass
class SectionOutput:
    section_id: str                     # e.g. "portfolio_pnl"
    html: str                           # rendered HTML fragment
    figures: dict[str, str] = field(default_factory=dict)        # figure_id → base64-encoded PNG
    tables: dict[str, pd.DataFrame] = field(default_factory=dict) # table_id → DataFrame (for appendix export)
```

---

## 4. Core API (`report.py`)

### 4.1 `BacktestReport` class

```python
class BacktestReport:
    """
    Main entry point. Orchestrates section generation and PDF rendering.

    Usage:
        data = BacktestData(...)
        meta = BacktestMeta(...)
        report = BacktestReport(data=data, meta=meta)
        pdf_path = report.generate()          # → Path to PDF
        html_path = report.generate(fmt="html") # → Path to HTML
    """

    def __init__(
        self,
        data: BacktestData,
        meta: BacktestMeta,
        sections: list[str] | None = None,    # None = all sections
        template_dir: Path | None = None,     # override template lookup
        custom_css: str | None = None,        # additional CSS to inject (for theming)
    ): ...

    def generate(
        self,
        output_dir: Path | str | None = None,
        fmt: str = "pdf",                     # "pdf" or "html"
        filename: str | None = None,          # default: f"{meta.config.experiment_id}_report.{fmt}"
    ) -> Path:
        """
        Generate the report. Always writes to a local path.

        1. Run each section module to get SectionOutput.
        2. Assemble all HTML fragments + figures into the master template.
        3. Render Jinja2 template with all context.
        4. If fmt="pdf", convert HTML → PDF via WeasyPrint.
        5. Write to output_dir / filename.
        6. Return Path to generated file.

        Note: Remote upload (to hc4t) is handled separately by the CLI
        layer, not by this method. generate() only produces local files.
        """
        ...

    # Section registry — maps section_id to callable
    SECTION_REGISTRY: dict[str, Callable[[BacktestData, BacktestMeta], SectionOutput]] = {
        "header": header.render_header,
        "portfolio_pnl": portfolio.render_portfolio_pnl,
        "monthly_returns": portfolio.render_monthly_returns,
        "portfolio_stats": portfolio.render_portfolio_stats,
        "rolling_stats": portfolio.render_rolling_stats,
        "instrument_pnl": instrument.render_instrument_pnl,
        "instrument_table": instrument.render_instrument_table,
        "position_snapshot": positions.render_position_snapshot,
        "attribution": attribution.render_attribution,
        "appendix": appendix.render_appendix,
    }
```

### 4.2 Convenience Functions

```python
def generate_report(
    experiment_dir: Path | str,
    sections: list[str] | None = None,
    fmt: str = "pdf",
) -> Path:
    """
    Load data from an experiment directory and generate report.

    Reads from experiment_dir using Parquet-first loading strategy:
      1. Try: portfolio_returns.parquet, instrument_pnl.parquet,
              positions.parquet, instrument_meta.json (no pysystemtrade needed)
      2. Fallback: system.pkl (via adapter, requires pysystemtrade)
    Also reads: config.yaml, meta.json

    Writes: experiment_dir/report.pdf (or .html)
    """

def from_pysystemtrade(
    system_path: Path | str,   # path to system.pkl
    config_path: Path | str,   # path to config.yaml
    meta_path: Path | str,     # path to meta.json
    sections: list[str] | None = None,
) -> BacktestReport:
    """
    High-level: load a persisted pysystemtrade System object and return
    a ready-to-generate BacktestReport.

    This is the only code path that imports pysystemtrade (optional dep).
    """
```

---

## 5. Section Specifications

Each section is a pure function with signature:

```python
def render_<section_id>(data: BacktestData, meta: BacktestMeta) -> SectionOutput
```

### 5.1 Header (`header.py` → `sections/header.html`)

**Data source:** `meta.config`

| Field | Display |
|-------|---------|
| experiment_id | Large, top-left |
| strategy_name | Subtitle |
| engine + version | Small grey text |
| Date range | `start_date → end_date` |
| Capital | Formatted with currency symbol |
| Risk target | `XX% annual` |
| Generated at | Timestamp, small grey |
| Git commit | Short hash, monospace |

### 5.2 Portfolio PnL (`portfolio.py` → `sections/portfolio.html`)

**Data source:** `data.portfolio_returns`

- Cumulative return curve (equity curve starting at 1.0)
- Underwater drawdown plot (percentage drawdown from peak)
- Both plots generated **directly using matplotlib**, styled to match the report design system

**Implementation:**
1. Compute cumulative returns: `(1 + data.portfolio_returns).cumprod()`
2. Compute drawdown: `cumulative / cumulative.cummax() - 1`
3. Generate equity curve figure with matplotlib (styled per §9)
4. Generate drawdown figure with matplotlib (styled per §9)
5. Apply custom CSS class `br-portfolio-pnl` and `br-portfolio-drawdown`
6. Encode figures as base64 PNG via `io.BytesIO` → return in `SectionOutput.figures`

**Note on QuantStats:** QuantStats is used exclusively via its `qs.stats` module for metric computation (see §5.4). Its `qs.reports.html()` function is **not** used for chart generation, as it produces a complete standalone page with no stable API for fragment extraction. All charts are generated with matplotlib for full control over styling, DPI, sizing, and page-break behaviour.

### 5.3 Monthly Returns (`portfolio.py` → `sections/monthly_returns.html`)

**Data source:** `data.portfolio_returns`

- Monthly return table: rows = years, columns = months + full-year total
- Cells coloured: green (positive, intensity by magnitude), red (negative, intensity by magnitude), grey (zero)
- Worst month highlighted; best month highlighted

**Implementation:**
1. Resample daily returns to monthly: `data.portfolio_returns.resample('ME').apply(lambda x: (1 + x).prod() - 1)`
2. Pivot into year × month table with annual total column
3. Render as HTML `<table>` with inline `background-color` styles for conditional formatting
4. Colour intensity scales linearly with return magnitude (cap at ±10% for palette range)

### 5.4 Portfolio Stats (`portfolio.py` → `sections/portfolio_stats.html`)

**Data source:** `data.portfolio_returns`

Key metrics table (2 columns: metric, value). Uses `qs.stats` for computation where available, with manual fallbacks:

| Metric | Computation |
|--------|-------------|
| Total Return | `qs.stats.comp(returns)` or `cumulative_returns[-1] - 1` |
| CAGR | `qs.stats.cagr(returns)` or `((1 + total_return) ** (252/n_days) - 1)` |
| Annualised Vol | `qs.stats.volatility(returns)` or `returns.std() * sqrt(252)` |
| Sharpe Ratio | `qs.stats.sharpe(returns)` or `annualised_return / annualised_vol` |
| Sortino Ratio | `qs.stats.sortino(returns)` or `annualised_return / downside_deviation` |
| Calmar Ratio | `qs.stats.calmar(returns)` or `CAGR / abs(max_drawdown)` |
| Max Drawdown | `qs.stats.max_drawdown(returns)` |
| Max DD Duration | longest period below peak (calendar days) |
| Win Rate | `qs.stats.win_rate(returns)` or `% of positive return days` |
| Profit Factor | `qs.stats.profit_factor(returns)` |
| Avg Win / Avg Loss | `qs.stats.avg_win(returns) / abs(qs.stats.avg_loss(returns))` |
| Skewness | `qs.stats.skew(returns)` or `returns.skew()` |
| Kurtosis | `qs.stats.kurtosis(returns)` or `returns.kurtosis()` |
| Best Day | `qs.stats.best(returns)` or `returns.max()` |
| Worst Day | `qs.stats.worst(returns)` or `returns.min()` |

### 5.5 Rolling Stats (`portfolio.py` → `sections/rolling_stats.html`)

**Data source:** `data.portfolio_returns`, `data.benchmark_returns` (optional)

- Rolling 1-year Sharpe ratio (252-day window)
- Rolling 3-year annualised return (756-day window)
- Beta to benchmark — **only shown if `data.benchmark_returns` is provided**; omitted entirely otherwise (trend-following beta to a default equity index is misleading)

Plots as matplotlib figures → base64 PNG.

### 5.6 Instrument PnL (`instrument.py` → `sections/instrument_pnl.html`)

**Data source:** `data.instrument_pnl`

- **Small multiples grid**: 4-column layout of per-instrument cumulative PnL curves
- Each subplot: instrument code + name, cumulative PnL line, Sharpe annotation
- Instruments sorted by total PnL (best → worst)
- Grid fills left→right, top→bottom
- Matplotlib figure → base64 PNG

**Sizing:** Each subplot approximately 3" wide × 2" tall. Max 20 instruments per page; paginate if more.

### 5.7 Instrument Table (`instrument.py` → `sections/instrument_table.html`)

**Data source:** `data.instrument_pnl`, `data.positions`, `data.instrument_returns`

Per-instrument statistics table (sortable by any column):

| Column | Computation |
|--------|-------------|
| Instrument | code (name) |
| Sharpe | `annualised_return / annualised_vol` per instrument |
| P&L | cumulative PnL in account currency |
| Max DD | max drawdown for that instrument's PnL curve |
| Avg Position | `positions[instrument].mean()` (absolute value) |
| Turnover | `positions[instrument].diff().abs().sum() / len(positions)` |
| Win Rate | `% of days with positive PnL` |

Rendered as an HTML `<table>` with `br-instrument-table` class. Alternating row colours. Column headers clickable for sort (static PDF → pre-sorted by P&L descending).

### 5.8 Position Snapshot (`positions.py` → `sections/position_snapshot.html`)

**Data source:** `data.positions`

- **Heatmap**: x-axis = time (sampled at weekly or monthly frequency depending on date range), y-axis = instruments, colour = position size (diverging colourmap: red = short, white = flat, blue = long)
- Matplotlib `imshow` or `pcolormesh` → base64 PNG
- Colour bar legend on the right
- Instruments on y-axis sorted by average absolute position size (most active at top)

### 5.9 Attribution (`attribution.py` → `sections/attribution.html`)

**Data source:** `data.instrument_pnl`, `data.instrument_meta`

**Two views:**

1. **By instrument**: Stacked bar chart (or horizontal bars) showing each instrument's contribution to portfolio return per period (monthly). Top 10 instruments individually, rest grouped as "Other".
2. **By sector/group**: Aggregate P&L by `instrument_meta.sector` and `instrument_meta.group`. Stacked bars by sector per month.

Charts as matplotlib → base64 PNG.

### 5.10 Appendix (`appendix.py` → `sections/appendix.html`)

**Data source:** `meta.config`, `meta.data_checksums`

- Full config YAML dump (syntax-highlighted in a `<pre>` block with monospace font)
- Data checksums table (filename → SHA-256)
- Python environment: `python_version`, `engine_version`, package versions
- Git commit short hash

---

## 6. PySystemTrade Adapter (`adapters/pysystemtrade.py`)

This is the **only** module that imports pysystemtrade. It is an **optional dependency** — the rest of the package works without it.

```python
def extract_backtest_data(system: "System") -> BacktestData:
    """
    Extract all data from a pysystemtrade System object into
    engine-agnostic BacktestData.

    Verified against pysystemtrade v1.8.x. Method names vary between
    versions — if upgrading pysystemtrade, re-verify these calls:

    Steps:
    1. Get instrument list from system.get_instrument_list()
    2. Get portfolio returns from system.accounts.portfolio().percent
    3. For each instrument:
       a. PnL: system.accounts.pandl_for_subsystem(instrument)
       b. Positions: system.portfolio.get_notional_position(instrument)
       c. Returns: derived from PnL / notional_exposure
    4. Get instrument metadata from external mapping (instrument_map.yaml)
    5. Return BacktestData with all fields populated

    NOTE: Before relying on these calls, run:
        help(system.accounts.portfolio)
        dir(system.accounts)
    to confirm method signatures for your installed version.
    """

def extract_backtest_config(system: "System", config_path: Path) -> BacktestConfig:
    """
    Build BacktestConfig from System config + external config file.

    Reads: instrument_universe, start/end dates, capital, risk target,
           data sources, config overrides.
    """

def load_system(pickle_path: Path) -> "System":
    """
    Load a pickled System object. Handles pysystemtrade version
    compatibility warnings and deserialisation.
    """
```

**Instrument metadata mapping:** pysystemtrade uses instrument codes like `"EDOLLAR"`, `"US10"`, `"GOLD"`. The adapter includes a built-in mapping file (`adapters/instrument_map.yaml`) that maps codes to `InstrumentMeta` (name, sector, group, asset_class). This file is maintained in the repo, loaded via `importlib.resources`, and can be overridden by the user.

### 6.1 `instrument_map.yaml`

Located at `src/backtest_report/adapters/instrument_map.yaml`:

```yaml
# Maps pysystemtrade instrument codes to metadata
EDOLLAR:
  name: Eurodollar
  sector: Rates
  group: STIR
  asset_class: Fixed Income
  exchange: CME
  point_value: 25.0
  currency: USD

US10:
  name: US 10-Year Note
  sector: Rates
  group: Bonds
  asset_class: Fixed Income
  exchange: CBOT
  point_value: 1000.0
  currency: USD

GOLD:
  name: Gold
  sector: Commodities
  group: Metals
  asset_class: Commodities
  exchange: COMEX
  point_value: 100.0
  currency: USD

# ... extended as universe grows
```

---

## 7. Persistence Layer (`persist.py`)

Handles reading and writing experiment directories. Works both locally and via SSH to hc4t.

### 7.1 Local filesystem

```python
def read_experiment_dir(path: Path) -> tuple[BacktestData, BacktestMeta]:
    """
    Read a local experiment directory. Uses a Parquet-first loading
    strategy to maintain engine-agnostic design:

    Strategy 1 — Parquet mode (preferred, no pysystemtrade needed):
      Reads: portfolio_returns.parquet, instrument_pnl.parquet,
             positions.parquet, instrument_meta.json
      Also: config.yaml, meta.json, data_checksums.json

    Strategy 2 — Pickle fallback (requires pysystemtrade):
      Reads: system.pkl (via adapter)
      Also: config.yaml, meta.json, data_checksums.json

    Falls back from Strategy 1 → Strategy 2 if Parquet files are missing.
    Raises ImportError with a clear message if pickle mode is needed
    but pysystemtrade is not installed.
    """

def write_experiment_dir(
    path: Path,
    data: BacktestData,
    config: BacktestConfig,
    data_checksums: dict[str, str],
    system: "System | None" = None,   # optional: also persist the System pickle
) -> None:
    """
    Write experiment directory. Always writes Parquet exports as standard
    to enable engine-agnostic reading:
      - portfolio_returns.parquet
      - instrument_pnl.parquet
      - positions.parquet
      - instrument_meta.json
      - config.yaml
      - data_checksums.json
      - meta.json (auto-generated)
      - system.pkl (only if system object is provided)
    """
```

### 7.2 Remote (hc4t server)

Remote connection details are resolved from a config cascade (highest priority first):

1. CLI flags (`--host`, `--remote-base`)
2. `.backtest-report.yaml` config file (`remote.host`, `remote.base_path`)
3. Environment variables (`BACKTEST_REPORT_HOST`, `BACKTEST_REPORT_REMOTE_BASE`)
4. Hardcoded defaults (last resort)

Uses `subprocess` + `scp`/`rsync` for file transfer (relies on SSH config for authentication). No additional Python SSH library required.

```python
def read_remote_experiment(
    experiment_id: str,
    host: str | None = None,           # resolved from config cascade
    remote_base: str | None = None,    # resolved from config cascade
) -> tuple[BacktestData, BacktestMeta]:
    """
    SCP experiment files from remote server to a local temp directory,
    then read locally using read_experiment_dir().

    Default host: quant@hc4t.sheldenkar.com
    Default remote_base: /store/backtests
    """

def write_remote_report(
    pdf_path: Path,
    experiment_id: str,
    host: str | None = None,           # resolved from config cascade
    remote_base: str | None = None,    # resolved from config cascade
) -> None:
    """
    SCP generated report.pdf to remote experiment directory.
    """
```

### 7.3 Naming Convention

```
<strategy_slug>_<YYYYMMDD_HHMMSS>

Examples:
  sg-trend-proxy_20260419_153000
  ewmac-trend_20260420_090000
  carry-standalone_20260421_110000
```

### 7.4 Directory Structure (on hc4t)

Parquet exports are written as **standard** (not optional) to enable engine-agnostic loading:

```
/store/backtests/
├── sg-trend-proxy_20260419_153000/
│   ├── system.pkl                    # pysystemtrade System object (optional)
│   ├── portfolio_returns.parquet     # standard — always written
│   ├── instrument_pnl.parquet        # standard — always written
│   ├── positions.parquet             # standard — always written
│   ├── instrument_meta.json          # standard — always written
│   ├── config.yaml
│   ├── data_checksums.json
│   ├── meta.json
│   └── report.pdf
├── ewmac-trend_20260420_090000/
│   └── ...
└── ...
```

---

## 8. Rendering Pipeline (`render.py`)

### 8.1 Template Assembly

```python
def assemble_html(
    sections: dict[str, SectionOutput],
    meta: BacktestMeta,
    template_dir: Path | None = None,
    custom_css: str | None = None,     # additional CSS to inject after style.css
) -> str:
    """
    1. Load Jinja2 environment from templates/
    2. Render report.html with:
       - meta (config, timestamps, etc.)
       - sections (dict of section_id → html fragment)
       - figures (dict of figure_id → base64 PNG data URIs)
    3. If custom_css provided, inject after the main style.css
    4. Return complete HTML string
    """
```

### 8.2 PDF Generation

```python
def html_to_pdf(html: str, output_path: Path) -> Path:
    """
    Convert HTML to PDF using WeasyPrint.

    Settings:
    - Page size: A4
    - Margins: 15mm all sides
    - Header/footer: implemented via CSS @page margin boxes (see §9.4)
    - CSS: loaded from templates/style.css, includes @font-face for bundled fonts
    - DPI: 150 for rasterised matplotlib figures
    - Optimisation: optimize_images=True, jpeg_quality=85

    Implementation:
        from weasyprint import HTML
        HTML(
            string=html,
            base_url=str(template_dir),  # resolves relative font/image paths
        ).write_pdf(
            str(output_path),
            optimize_images=True,
            jpeg_quality=85,
        )
    """
```

### 8.3 Template Structure

`report.html` is a Jinja2 master template:

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{{ meta.config.experiment_id }} — Backtest Report</title>
    <style>{% include "style.css" %}</style>
    {% if custom_css %}<style>{{ custom_css }}</style>{% endif %}
</head>
<body>
    <!-- Running elements for @page margin boxes (positioned via CSS) -->
    <div class="br-running-header">
        <span style="string-set: experiment-id '{{ meta.config.experiment_id }}'"></span>
        <span style="string-set: report-version '{{ meta.report_version }}'"></span>
        <span style="string-set: generated-at '{{ meta.generated_at.strftime("%Y-%m-%d %H:%M") }}'"></span>
    </div>

    {% if sections.header %}{{ sections.header.html | safe }}{% endif %}

    <div class="br-page-break"></div>
    {% if sections.portfolio_pnl %}{{ sections.portfolio_pnl.html | safe }}{% endif %}

    <div class="br-page-break"></div>
    {% if sections.monthly_returns %}{{ sections.monthly_returns.html | safe }}{% endif %}

    <div class="br-page-break"></div>
    {% if sections.portfolio_stats %}{{ sections.portfolio_stats.html | safe }}{% endif %}

    <div class="br-page-break"></div>
    {% if sections.rolling_stats %}{{ sections.rolling_stats.html | safe }}{% endif %}

    <div class="br-page-break"></div>
    {% if sections.instrument_pnl %}{{ sections.instrument_pnl.html | safe }}{% endif %}

    <div class="br-page-break"></div>
    {% if sections.instrument_table %}{{ sections.instrument_table.html | safe }}{% endif %}

    <div class="br-page-break"></div>
    {% if sections.position_snapshot %}{{ sections.position_snapshot.html | safe }}{% endif %}

    <div class="br-page-break"></div>
    {% if sections.attribution %}{{ sections.attribution.html | safe }}{% endif %}

    <div class="br-page-break"></div>
    {% if sections.appendix %}{{ sections.appendix.html | safe }}{% endif %}
</body>
</html>
```

Each section partial (e.g. `sections/portfolio.html`) receives its data and figures via Jinja2 context variables.

---

## 9. Styling (`templates/style.css`)

### 9.1 Font Embedding

Fonts are bundled in `templates/fonts/` and loaded via `@font-face`. This ensures the report renders correctly in offline and CI environments without relying on external CDN requests.

```css
@font-face {
    font-family: 'Inter';
    src: url('fonts/Inter-Regular.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}

@font-face {
    font-family: 'Inter';
    src: url('fonts/Inter-SemiBold.woff2') format('woff2');
    font-weight: 600;
    font-style: normal;
}

@font-face {
    font-family: 'JetBrains Mono';
    src: url('fonts/JetBrainsMono-Regular.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}
```

**Fallback:** If font files are missing (e.g. in a minimal Docker environment), the system font stack (`-apple-system, 'Segoe UI', sans-serif`) is used. The report still generates correctly, just with different typography.

### 9.2 Design System

```css
:root {
    --br-font-body: 'Inter', -apple-system, 'Segoe UI', sans-serif;
    --br-font-mono: 'JetBrains Mono', 'Fira Code', monospace;
    --br-font-data: 'Inter', -apple-system, sans-serif;

    --br-col-bg: #ffffff;
    --br-col-text: #1a1a1a;
    --br-col-muted: #6b7280;
    --br-col-border: #e5e7eb;

    --br-col-positive: #10b981;    /* green - positive returns */
    --br-col-negative: #ef4444;    /* red - negative returns */
    --br-col-neutral: #6b7280;    /* grey - zero/flat */

    --br-col-header: #111827;      /* dark header bar */
    --br-col-header-text: #f9fafb;

    --br-col-table-stripe: #f9fafb;
    --br-col-table-hover: #f3f4f6;

    --br-spacing-xs: 4px;
    --br-spacing-sm: 8px;
    --br-spacing-md: 16px;
    --br-spacing-lg: 24px;
    --br-spacing-xl: 32px;

    --br-page-width: 210mm;        /* A4 */
    --br-page-margin: 15mm;
}
```

### 9.3 Typography

- **Headers**: Inter, 600 weight
- **Body**: Inter, 400 weight, 10pt, line-height 1.5
- **Data tables**: Inter, 400 weight, 8pt, line-height 1.3
- **Code/config dumps**: JetBrains Mono, 400 weight, 7.5pt

### 9.4 Page Rules (WeasyPrint CSS Paged Media)

WeasyPrint implements headers, footers, and page numbers via CSS `@page` margin boxes, not programmatically. These rules must be in `style.css`:

```css
@page {
    size: A4;
    margin: 15mm;

    @top-right {
        content: string(experiment-id) "  |  Page " counter(page) " of " counter(pages);
        font-family: var(--br-font-body);
        font-size: 7pt;
        color: var(--br-col-muted);
    }

    @bottom-center {
        content: "Generated by backtest-report v" string(report-version) " | " string(generated-at);
        font-family: var(--br-font-body);
        font-size: 6.5pt;
        color: var(--br-col-muted);
    }
}

/* First page has no header (the header section serves as the title page) */
@page :first {
    @top-right {
        content: none;
    }
}
```

### 9.5 Print Rules

```css
.br-page-break {
    page-break-after: always;
    break-after: page;
}

/* Prevent orphan headings */
h2, h3 {
    page-break-after: avoid;
    break-after: avoid;
}

/* Keep tables and figures together */
table, figure, .br-figure {
    page-break-inside: avoid;
    break-inside: avoid;
}

/* Figure captions */
figcaption,
.br-figure-caption {
    text-align: center;
    font-size: 8pt;
    color: var(--br-col-muted);
    margin-top: var(--br-spacing-xs);
}
```

---

## 10. CLI Interface

The package installs a `backtest-report` CLI command using **Click** (`click ≥8.0`):

**Entry point** (in `pyproject.toml`):

```toml
[project.scripts]
backtest-report = "backtest_report.__main__:cli"
```

```bash
# Generate report from a local experiment directory
backtest-report generate /path/to/experiment_dir

# Generate from a remote experiment on hc4t
backtest-report generate --remote sg-trend-proxy_20260419_153000

# Specify output format
backtest-report generate /path/to/experiment_dir --format html

# Generate from raw DataFrames (no System object)
backtest-report generate \
    --portfolio-returns returns.parquet \
    --instrument-pnl pnl.parquet \
    --positions positions.parquet \
    --meta meta.json \
    --output-dir ./reports/

# Upload a locally-generated report to hc4t
backtest-report upload /path/to/report.pdf --experiment-id sg-trend-proxy_20260419_153000

# List available sections
backtest-report sections

# Validate an experiment directory
backtest-report validate /path/to/experiment_dir

# Export System object to Parquet (for archival)
backtest-report export-parquet /path/to/experiment_dir
```

### 10.1 Argument Details

```
backtest-report generate [PATH] [OPTIONS]

Arguments:
  PATH                    Local experiment directory containing
                          Parquet files (or system.pkl), config.yaml, meta.json

Options:
  --remote EXPERIMENT_ID  Pull from hc4t server instead of local path
  --host TEXT             Remote host (overrides config cascade)
  --remote-base TEXT      Remote base path (overrides config cascade)
  --sections TEXT         Comma-separated section IDs to include
                          (default: all)
  --format TEXT           Output format: pdf, html (default: pdf)
  --output-dir PATH       Output directory (default: experiment directory)
  --filename TEXT         Output filename (default: auto-generated)
  --verbose               Log section generation progress (DEBUG level)

Raw DataFrame options (mutually exclusive with PATH):
  --portfolio-returns PATH   Parquet/CSV file with portfolio returns series
  --instrument-pnl PATH     Parquet/CSV file with instrument PnL DataFrame
  --positions PATH           Parquet/CSV file with positions DataFrame
  --meta PATH                JSON file with BacktestMeta

backtest-report upload PDF_PATH [OPTIONS]

Arguments:
  PDF_PATH                Path to the generated report PDF

Options:
  --experiment-id TEXT    Experiment ID for remote directory (required)
  --host TEXT             Remote host (overrides config cascade)
  --remote-base TEXT      Remote base path (overrides config cascade)
```

---

## 11. Dependencies

### 11.1 Core (required)

| Package | Version | Purpose |
|---------|---------|---------|
| python | ≥3.10 | Minimum runtime |
| pandas | ≥2.0 | DataFrame handling |
| numpy | ≥1.24 | Numerical computation |
| matplotlib | ≥3.7 | Figure generation (all charts) |
| quantstats | ≥0.0.62 | Portfolio metrics via `qs.stats` |
| jinja2 | ≥3.1 | Template rendering |
| weasyprint | ≥60 | HTML → PDF |
| pydantic | ≥2.0 | Data model validation |
| pyyaml | ≥6.0 | Config file handling (pysystemtrade configs are YAML) |
| click | ≥8.0 | CLI framework |

### 11.2 Optional

| Package | Version | Purpose |
|---------|---------|---------|
| pysystemtrade | ≥1.8 | System object adapter (optional) |
| pyarrow | ≥12.0 | Parquet read/write (optional, faster than CSV) |

### 11.3 Dev dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| pytest | ≥7.0 | Testing |
| pytest-cov | ≥4.0 | Coverage |
| ruff | ≥0.1 | Linting + formatting |
| mypy | ≥1.5 | Type checking |

---

## 12. Logging

The package uses Python's `logging` module with a root logger named `backtest_report`.

**Log levels:**
- `WARNING` (default) — only errors and warnings surfaced
- `DEBUG` (via `--verbose` CLI flag) — detailed timing and progress

**Key log points:**
- Section generation start/end with elapsed time
- QuantStats metric computation timing
- WeasyPrint rendering timing
- Remote SCP operations (start, success, failure)
- Graceful degradation events (missing data, QuantStats failures, benchmark omission)

```python
import logging

logger = logging.getLogger("backtest_report")

# In report.py
logger.info("Generating section: %s", section_id)
logger.debug("Section %s completed in %.2fs", section_id, elapsed)

# In portfolio.py (graceful degradation)
logger.warning("qs.stats.sharpe() failed, falling back to manual computation: %s", err)
```

---

## 13. Versioning

The package version is managed via a **single source of truth** in `pyproject.toml`:

```toml
[project]
name = "backtest-report"
version = "0.1.0"
```

At runtime, the version is read via `importlib.metadata`:

```python
# __init__.py
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("backtest-report")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
```

This version string is used in:
- `BacktestMeta.report_version`
- PDF footer (`"Generated by backtest-report v{version}"`)
- CLI `--version` flag

---

## 14. Testing Strategy

### 14.1 Unit Tests

Each module has corresponding unit tests in `tests/`:

- `test_portfolio.py` — portfolio metrics computation, chart generation, monthly returns table
- `test_instrument.py` — per-instrument PnL curves, small multiples layout
- `test_attribution.py` — sector/group aggregation, top-N + "Other" grouping
- `test_positions.py` — heatmap generation, sampling frequency
- `test_render.py` — template assembly, PDF generation (snapshot testing)
- `test_persist.py` — experiment directory read/write (both Parquet and pickle modes), naming validation
- `test_pysystemtrade_adapter.py` — System → BacktestData extraction (mocked System)
- `test_report.py` — end-to-end: BacktestReport with sample data → PDF file

### 14.2 Test Fixtures

`tests/fixtures/` contains:

- `sample_portfolio_returns.parquet` — 5 years of synthetic daily returns (Sharpe ~1.0, 15% vol)
- `sample_instrument_returns.parquet` — 10 instruments, correlated with portfolio
- `sample_positions.parquet` — realistic position sizes
- `sample_meta.json` — complete BacktestMeta example

**How to generate fixtures:** The `scripts/generate_fixtures.py` script creates synthetic but realistic backtest data using numpy (random walk with drift, controlled correlation structure).

### 14.3 Integration Test

```python
def test_end_to_end_report_generation():
    """Generate a complete PDF from fixture data and verify:
    1. PDF file is created and non-empty
    2. PDF contains expected section headers
    3. All figures are embedded
    4. Config appendix is included
    """
```

### 14.4 Snapshot Testing

For PDF output, we don't binary-diff. Instead:
1. Generate HTML output
2. Assert HTML contains expected section markers
3. Assert all `data:image/png;base64,...` figure embeddings exist
4. Assert key metric values appear in the HTML (Sharpe, MaxDD, etc.)

---

## 15. Error Handling

### 15.1 Missing Data

- If an instrument has no position data, the instrument PnL and position sections skip it gracefully
- If `instrument_meta` is incomplete, default sector/group to `"Unknown"`
- If `instrument_returns` dict is empty, compute approximate returns from PnL

### 15.2 Short History

- If backtest period < 1 year: rolling stats sections show a warning banner instead of a chart
- If < 30 days: report still generates but header shows `"⚠ Short history (N days)"`

### 15.3 QuantStats Failures

- Wrap `qs.stats.*` calls in try/except
- On failure: fall back to manual computation (pandas/numpy) and log a warning
- If manual computation also fails: display `"N/A"` for that metric
- Never let a QuantStats failure prevent the entire report from generating

### 15.4 Remote Access Failures

- If SCP to hc4t fails: clear error message with connection troubleshooting hints
- If `system.pkl` is corrupt or incompatible pysystemtrade version: error message with version info
- If required file is missing from experiment directory: list which files were found vs expected

---

## 16. Configuration Override

Users can override report behaviour via a `.backtest-report.yaml` file or CLI flags:

```yaml
# .backtest-report.yaml (in experiment directory or home directory)
report:
  sections:
    - header
    - portfolio_pnl
    - portfolio_stats
    - instrument_pnl
    - instrument_table
    - attribution
    - appendix
    # Omit sections to exclude them

  style:
    theme: light          # light | dark
    font_scale: 1.0
    color_positive: "#10b981"
    color_negative: "#ef4444"

  heatmap:
    max_instruments: 30    # paginate if more
    sample_freq: W         # W=weekly, M=monthly

  attribution:
    top_n: 10              # top N instruments shown individually
    group_other: true      # group remaining as "Other"

  output:
    format: pdf            # pdf | html | both
    dpi: 150
    page_size: A4
    margins_mm: 15

# Remote connection settings (lowest priority after CLI flags and env vars)
remote:
  host: "quant@hc4t.sheldenkar.com"
  base_path: "/store/backtests"
```

---

## 17. QuantConnect / LEAN Adapter (Future)

The architecture explicitly supports future adapters. When QuantConnect backtests are needed:

```python
# adapters/quantconnect.py (future)
def extract_backtest_data(lean_result: "LeanResult") -> BacktestData:
    """Convert LEAN backtest results to BacktestData."""
    ...
```

This requires no changes to any other module — `BacktestReport` only sees `BacktestData`.

---

## 18. Implementation Order

| Phase | Items | Description |
|-------|-------|-------------|
| **P1** | `models.py`, `persist.py` (local only) | Data models + experiment directory read/write (Parquet-first) |
| **P2** | `portfolio.py` | Matplotlib charts + qs.stats metrics — portfolio PnL, monthly returns, stats, rolling stats |
| **P3** | `render.py` + templates + style.css | Jinja2 template assembly + WeasyPrint PDF generation + @page rules + font embedding |
| **P4** | `report.py`, `header.py`, `appendix.py` | BacktestReport orchestrator + header/appendix renderers |
| **P5** | `instrument.py` | Per-instrument PnL curves, instrument stats table |
| **P6** | `positions.py` | Position heatmap |
| **P7** | `attribution.py` | Return attribution by instrument and sector |
| **P8** | `adapters/pysystemtrade.py` | System → BacktestData adapter (verify API against installed version) |
| **P9** | CLI (`__main__.py`) | Click CLI interface with subcommands |
| **P10** | `persist.py` (remote) | SCP read/write for hc4t via subprocess |
| **P11** | Tests, docs, CI | Full test coverage, README, GitHub Actions |

Each phase should produce a working, testable increment. P1–P4 produce a minimal end-to-end report (portfolio sections only). P5–P7 add instrument-level detail. P8–P10 add integration with pysystemtrade and remote server.

---

## 19. Acceptance Criteria

The implementation is complete when:

1. ✅ `backtest-report generate /path/to/experiment_dir` produces a valid PDF from a local experiment directory containing Parquet files (or `system.pkl`), `config.yaml`, and `meta.json`
2. ✅ `backtest-report generate --portfolio-returns returns.parquet --instrument-pnl pnl.parquet --positions positions.parquet --meta meta.json` produces a PDF from raw DataFrames (no pysystemtrade)
3. ✅ All 10 report sections render correctly with fixture data
4. ✅ PDF contains: header with metadata, equity curve, drawdown, monthly returns, portfolio stats, rolling Sharpe, instrument small multiples, instrument table, position heatmap, attribution, appendix
5. ✅ Report page breaks are correct (no orphan headers, no mid-table splits)
6. ✅ Report styling is consistent (embedded fonts, colours, spacing per design system)
7. ✅ Remote experiment loading via `--remote` works against hc4t
8. ✅ `backtest-report upload` uploads reports to hc4t
9. ✅ `backtest-report validate <dir>` checks experiment directory completeness
10. ✅ `backtest-report sections` lists available section IDs
11. ✅ Test coverage ≥ 80% for all modules
12. ✅ Short history (< 30 days, < 1 year) handled gracefully with warnings
13. ✅ Missing instrument metadata defaults to "Unknown" sector/group without crashing
14. ✅ QuantStats `qs.stats` failures are caught with manual fallbacks; report still generates with partial content
15. ✅ Experiment directories use Parquet-first storage; `read_experiment_dir()` works without pysystemtrade when Parquet files exist