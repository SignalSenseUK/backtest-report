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
    """Generate PDF/HTML backtest reports from trading system data.

    Subcommands:
      generate    Generate a report (PDF or HTML)
      sections    List available section IDs
      validate    Check experiment directory completeness
      upload      Upload a report to a remote server
    """
    _configure_logging(verbose)


@cli.command()
@click.argument("experiment_dir", type=click.Path(exists=False, path_type=Path))
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file path (default: <experiment_dir>/report.<pdf|html>)",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["pdf", "html"]),
    default="pdf",
    help="Output format: pdf (default) or html",
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
@click.option(
    "--remote",
    "remote_host",
    type=str,
    default=None,
    help="Download experiment from remote host via SCP before generating",
)
@click.option(
    "--remote-user",
    type=str,
    default=None,
    help="SSH username for remote download (default: from config or 'backtest')",
)
@click.option(
    "--remote-port",
    type=int,
    default=None,
    help="SSH port for remote download (default: 22)",
)
def generate(
    experiment_dir: Path,
    output_path: Path | None,
    fmt: str,
    section_filter: tuple[str, ...],
    section_filter_list: str | None,
    template_dir: Path | None,
    remote_host: str | None,
    remote_user: str | None,
    remote_port: int | None,
) -> None:
    """Generate a backtest report from an experiment directory.

    EXPERIMENT_DIR should contain Parquet files (portfolio_returns.parquet,
    instrument_pnl.parquet, positions.parquet) and a meta.json file.

    Use --remote to download experiment data from a remote server before
    generating. The remote path is used as EXPERIMENT_DIR on the server.

    Examples:
      backtest-report generate ./experiments/my-backtest
      backtest-report generate ./experiments/my-backtest --format html -o report.html
      backtest-report generate --remote qr.sheldenkar.co.uk /store/experiments/exp-001
    """
    # If --remote, download experiment data first
    if remote_host:
        from backtest_report.remote import load_remote_config, read_remote_experiment

        remote_cfg = load_remote_config()
        effective_user = remote_user or remote_cfg.get("remote_user", "backtest")
        effective_port = remote_port or remote_cfg.get("remote_port", 22)

        click.echo(
            f"Downloading experiment from {effective_user}@{remote_host}:{effective_port}..."
        )
        try:
            local_dir = read_remote_experiment(
                remote_dir=str(experiment_dir),
                remote_host=remote_host,
                remote_user=effective_user,
                remote_port=effective_port,
            )
            experiment_dir = local_dir
        except RuntimeError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

    if not experiment_dir.exists():
        click.echo(f"Error: Directory not found: {experiment_dir}", err=True)
        sys.exit(1)

    # Resolve output path
    ext = fmt if fmt == "html" else "pdf"
    if output_path is None:
        output_path = experiment_dir / f"report.{ext}"

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
    click.echo(f"Generating {fmt.upper()} report → {output_path}")
    try:
        report = BacktestReport(
            data=data,
            meta=meta,
            section_filter=sections,
            template_dir=template_dir,
        )
        result_path = report.generate(output_path=output_path, fmt=fmt)
        click.echo(f"✓ Report written: {result_path} ({result_path.stat().st_size / 1024:.1f} KB)")
    except Exception as e:
        logger.exception("Report generation failed")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def sections() -> None:
    """List all available section IDs that can be used with --sections."""
    registered = [
        ("header", "Report header banner"),
        ("portfolio_pnl", "Equity curve and drawdown charts"),
        ("monthly_returns", "Year x month returns heatmap table"),
        ("portfolio_stats", "Key metrics table"),
        ("rolling_stats", "Rolling Sharpe, 3yr return, beta charts"),
        ("instrument_pnl", "Per-instrument PnL small multiples"),
        ("instrument_table", "Per-instrument statistics table"),
        ("position_snapshot", "Time x instrument heatmap"),
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
@click.argument("report_path", type=click.Path(exists=True, path_type=Path))
@click.argument("remote_dir", type=str)
@click.option(
    "--remote-host", type=str, default=None, help="Remote SSH host (default: from config)"
)
@click.option(
    "--remote-user",
    type=str,
    default=None,
    help="SSH username (default: from config or 'backtest')",
)
@click.option("--remote-port", type=int, default=None, help="SSH port (default: 22)")
def upload(
    report_path: Path,
    remote_dir: str,
    remote_host: str | None,
    remote_user: str | None,
    remote_port: int | None,
) -> None:
    """Upload a generated report to a remote server via SCP.

    REPORT_PATH is the local PDF or HTML file to upload.
    REMOTE_DIR is the destination directory on the remote server.

    Example:
      backtest-report upload ./report.pdf /store/reports/
    """
    from backtest_report.remote import load_remote_config, write_remote_report

    remote_cfg = load_remote_config()
    effective_host = remote_host or remote_cfg.get("remote_host", "results.example.com")
    effective_user = remote_user or remote_cfg.get("remote_user", "backtest")
    effective_port = remote_port or remote_cfg.get("remote_port", 22)

    click.echo(f"Uploading {report_path} to {effective_user}@{effective_host}:{remote_dir}...")
    try:
        write_remote_report(
            local_pdf=report_path,
            remote_dir=remote_dir,
            remote_host=effective_host,
            remote_user=effective_user,
            remote_port=effective_port,
        )
        click.echo("✓ Report uploaded successfully")
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("experiment_dir", type=click.Path(exists=True, path_type=Path))
@click.argument("output_parquet", type=click.Path(path_type=Path))
def export_parquet(experiment_dir: Path, output_parquet: Path) -> None:
    """Export experiment data to a single Parquet file for portability.

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
