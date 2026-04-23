"""Click CLI for backtest-report."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from backtest_report import __version__
from backtest_report.persist import read_experiment_dir, validate_experiment_dir
from backtest_report.report import BacktestReport

logger = logging.getLogger("backtest_report")


def _configure_logging(verbose: bool) -> None:
    """Configure root logger based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.version_option(version=__version__)
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def cli(verbose: bool) -> None:
    """Generate PDF backtest reports from trading system data.

    Run with subcommands:
      backtest-report generate    Generate a PDF report
      backtest-report sections    List available section IDs
      backtest-report validate    Check experiment directory completeness
    """
    _configure_logging(verbose)


@cli.command()
@click.argument("experiment_dir", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Output PDF path (default: <experiment_dir>/report.pdf)",
)
@click.option(
    "--sections",
    "section_filter",
    multiple=True,
    help="Section IDs to include (can be repeated). Omit to include all.",
)
@click.option(
    "--filter",
    "section_filter_list",
    type=str,
    default=None,
    help="Comma-separated section IDs (alternative to --sections)",
)
@click.option(
    "--template-dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Override template directory",
)
def generate(
    experiment_dir: Path,
    output_path: Path | None,
    section_filter: tuple[str, ...],
    section_filter_list: str | None,
    template_dir: Path | None,
) -> None:
    """Generate a PDF backtest report from an experiment directory.

    EXPERIMENT_DIR should contain Parquet files (portfolio_returns.parquet,
    instrument_pnl.parquet, positions.parquet) and a meta.json file.

    Example:
      backtest-report generate ./experiments/my-backtest -o report.pdf
    """
    # Resolve output path
    if output_path is None:
        output_path = experiment_dir / "report.pdf"

    # Resolve section filter
    sections: list[str] | None = None
    if section_filter:
        sections = list(section_filter)
    elif section_filter_list:
        sections = [s.strip() for s in section_filter_list.split(",") if s.strip()]

    # Load experiment
    logger.info("Loading experiment from: %s", experiment_dir)
    try:
        data, meta = read_experiment_dir(experiment_dir)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Generate report
    click.echo(f"Generating report → {output_path}")
    try:
        report = BacktestReport(
            data=data,
            meta=meta,
            section_filter=sections,
            template_dir=template_dir,
        )
        result_path = report.generate(output_path=output_path)
        click.echo(f"✓ Report written: {result_path} ({result_path.stat().st_size / 1024:.1f} KB)")
    except Exception as e:
        logger.exception("Report generation failed")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def sections() -> None:
    """List all available section IDs that can be used with --sections.

    Currently registered sections:
      header            Report header banner
      portfolio_pnl     Equity curve and drawdown charts
      monthly_returns   Year × month returns heatmap table
      portfolio_stats   Key metrics table
      rolling_stats     Rolling Sharpe, 3yr return, beta charts
      instrument_pnl     Per-instrument PnL small multiples
      instrument_table  Per-instrument statistics table
      position_snapshot Time × instrument heatmap
      attribution       Return attribution charts
      appendix         Config dump, checksums, environment info
    """
    registered = [
        ("header", "Report header banner"),
        ("portfolio_pnl", "Equity curve and drawdown charts"),
        ("monthly_returns", "Year × month returns heatmap table"),
        ("portfolio_stats", "Key metrics table"),
        ("rolling_stats", "Rolling Sharpe, 3yr return, beta charts"),
        ("instrument_pnl", "Per-instrument PnL small multiples"),
        ("instrument_table", "Per-instrument statistics table"),
        ("position_snapshot", "Time × instrument heatmap"),
        ("attribution", "Return attribution charts"),
        ("appendix", "Config dump, checksums, environment info"),
    ]

    click.echo("Available section IDs:\n")
    for section_id, description in registered:
        click.echo(f"  {section_id:<20} {description}")


@cli.command()
@click.argument("experiment_dir", type=click.Path(exists=True, path_type=Path))
def validate(experiment_dir: Path) -> None:
    """Check an experiment directory for completeness.

    Validates that all required files are present and detects whether
    the Parquet or pickle strategy is being used.

    Example:
      backtest-report validate ./experiments/my-backtest
    """
    result = validate_experiment_dir(experiment_dir)

    click.echo(f"Experiment directory: {experiment_dir}")
    click.echo(f"Strategy: {result['strategy']}")
    click.echo(f"Valid: {'✓' if result['valid'] else '✗'}")

    if result["found"]:
        click.echo(f"\nFound files ({len(result['found'])}):")
        for f in sorted(result["found"]):
            click.echo(f"  ✓ {f}")

    if result["missing"]:
        click.echo(f"\nMissing files ({len(result['missing'])}):")
        for f in sorted(result["missing"]):
            click.echo(f"  ✗ {f}")

    if not result["valid"]:
        sys.exit(1)


@cli.command()
@click.argument("experiment_dir", type=click.Path(exists=True, path_type=Path))
@click.argument("output_parquet", type=click.Path(path_type=Path))
def export_parquet(experiment_dir: Path, output_parquet: Path) -> None:
    """Export experiment data to a single Parquet file for portability.

    This is useful for creating a portable backtest bundle.

    Example:
      backtest-report export-parquet ./my-backtest ./backtest.parquet
    """
    import pandas as pd

    click.echo(f"Loading experiment from: {experiment_dir}")
    try:
        data, meta = read_experiment_dir(experiment_dir)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Combine into a single dict of DataFrames
    combined = {
        "portfolio_returns": data.portfolio_returns.to_frame(),
        "instrument_pnl": data.instrument_pnl,
        "positions": data.positions,
    }

    # Write as Parquet dataset
    click.echo(f"Writing Parquet: {output_parquet}")
    pd.io.parquet._logger.setLevel(logging.WARNING)
    combined_df = pd.concat(combined.values(), keys=combined.keys(), names=["stream"])
    combined_df.to_parquet(output_parquet)
    click.echo(f"✓ Exported: {output_parquet} ({output_parquet.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    cli()
