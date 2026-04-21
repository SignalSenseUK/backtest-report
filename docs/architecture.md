# Architecture

## Overview

`backtest-report` is a Python package that generates standardised PDF backtest reports. It follows a layered architecture:

```
CLI (Click)
    ↓
BacktestReport orchestrator
    ↓
Section renderers (portfolio.py, instrument.py, positions.py, header.py, appendix.py)
    ↓
Render pipeline (render.py → Jinja2 + WeasyPrint → PDF)
    ↓
Persistence (persist.py → Parquet files)
```

## Data Models (`models.py`)

- `BacktestConfig` — experiment metadata (strategy, dates, capital, etc.)
- `BacktestData` — core data (portfolio returns, instrument PnL, positions)
- `BacktestMeta` — report generation metadata (checksums, timestamps)
- `InstrumentMeta` — per-instrument metadata (sector, exchange, etc.)
- `SectionOutput` — output from each section renderer (HTML + base64 figures)

## Section Renderers

Each section is a pure function: `(BacktestData, BacktestMeta) → SectionOutput`

| Module | Sections |
|--------|----------|
| `portfolio.py` | `portfolio_pnl`, `monthly_returns`, `portfolio_stats`, `rolling_stats` |
| `instrument.py` | `instrument_pnl`, `instrument_table` |
| `positions.py` | `position_snapshot`, `attribution` |
| `header.py` | `header` |
| `appendix.py` | `appendix` |

## Persistence (`persist.py`)

Parquet-first strategy:

1. **Write**: DataFrames → Parquet, metadata → JSON/YAML, checksums computed
2. **Read**: Parquet first; if missing, fall back to pysystemtrade pickle (requires adapter)

## Rendering (`render.py`)

1. `assemble_html()` — Jinja2 template → complete HTML document
2. `html_to_pdf()` — WeasyPrint HTML(string=) → PDF file

## Template System

- `templates/style.css` — CSS design system with custom properties
- `templates/report.html` — master Jinja2 template
- `templates/sections/*.html` — section-level fragments

## CLI (`__main__.py`)

- `generate` — generate PDF from experiment directory
- `sections` — list available section IDs
- `validate` — check experiment directory completeness
- `export-parquet` — bundle to portable Parquet

## Remote Persistence (`remote.py`)

SCP-based read/write for remote experiment directories. Config cascade: CLI flags → YAML config → environment variables → defaults.

## Adapters (`adapters/`)

- `pysystemtrade.py` — converts System pickle → BacktestData/BacktestConfig
- `instrument_map.yaml` — instrument metadata mappings
