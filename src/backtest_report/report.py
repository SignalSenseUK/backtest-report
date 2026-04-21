"""Report orchestrator — wires section renderers to the rendering pipeline."""
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from backtest_report.models import BacktestConfig, BacktestData, BacktestMeta, SectionOutput

logger = logging.getLogger("backtest_report")

# Section renderers — registered functions: (data, meta) -> SectionOutput
SECTION_REGISTRY: dict[str, callable] = {}


def _register_default_sections() -> None:
    """Register all known section renderers."""
    # Portfolio sections
    from backtest_report import portfolio

    SECTION_REGISTRY["portfolio_pnl"] = portfolio.render_portfolio_pnl
    SECTION_REGISTRY["monthly_returns"] = portfolio.render_monthly_returns
    SECTION_REGISTRY["portfolio_stats"] = portfolio.render_portfolio_stats
    SECTION_REGISTRY["rolling_stats"] = portfolio.render_rolling_stats

    # Header and appendix
    from backtest_report import header, appendix

    SECTION_REGISTRY["header"] = header.render_header
    SECTION_REGISTRY["appendix"] = appendix.render_appendix

    # Instrument sections
    from backtest_report import instrument

    SECTION_REGISTRY["instrument_pnl"] = instrument.render_instrument_pnl
    SECTION_REGISTRY["instrument_table"] = instrument.render_instrument_table

    # Position and attribution sections
    from backtest_report import positions

    SECTION_REGISTRY["position_snapshot"] = positions.render_position_snapshot
    SECTION_REGISTRY["attribution"] = positions.render_attribution


_register_default_sections()


class BacktestReport:
    """Central orchestrator for backtest report generation.

    Usage:
        report = BacktestReport(
            data=backtest_data,
            meta=backtest_meta,
            section_filter=["portfolio_pnl", "monthly_returns", "portfolio_stats"],
            template_dir=Path("./templates"),
        )
        pdf_path = report.generate(output_path=Path("report.pdf"))
    """

    def __init__(
        self,
        data: BacktestData,
        meta: BacktestMeta,
        section_filter: list[str] | None = None,
        template_dir: Path | None = None,
        custom_css: str | None = None,
    ) -> None:
        """Initialize the report orchestrator.

        Args:
            data: BacktestData with portfolio returns, instrument PnL, positions
            meta: BacktestMeta with config and checksums
            section_filter: optional list of section IDs to include (None = all)
            template_dir: override for templates directory
            custom_css: optional additional CSS string
        """
        self.data = data
        self.meta = meta
        self.section_filter = section_filter
        self.template_dir = template_dir
        self.custom_css = custom_css
        self._sections: dict[str, SectionOutput] = {}

    def _render_section(self, section_id: str) -> SectionOutput:
        """Render a single section by ID."""
        if section_id not in SECTION_REGISTRY:
            logger.warning("Unknown section: %s", section_id)
            return SectionOutput(section_id=section_id, html="")

        renderer = SECTION_REGISTRY[section_id]
        logger.info("Rendering section: %s", section_id)
        t0 = time.time()
        output = renderer(self.data, self.meta)
        elapsed = time.time() - t0
        logger.info("  → %s done (%.2fs)", section_id, elapsed)
        return output

    def generate(self, output_path: Path) -> Path:
        """Generate the full PDF report.

        Args:
            output_path: destination PDF file path

        Returns:
            Path to the written PDF file
        """
        from backtest_report.render import assemble_html, html_to_pdf

        # Determine which sections to render
        if self.section_filter is not None:
            section_ids = self.section_filter
        else:
            section_ids = list(SECTION_REGISTRY.keys())

        # Render all sections
        logger.info("Rendering %d sections...", len(section_ids))
        for section_id in section_ids:
            self._sections[section_id] = self._render_section(section_id)

        # Assemble HTML
        logger.info("Assembling HTML...")
        html = assemble_html(
            sections=self._sections,
            meta=self.meta,
            template_dir=self.template_dir,
            custom_css=self.custom_css,
        )

        # Render PDF
        logger.info("Rendering PDF → %s", output_path)
        return html_to_pdf(html=html, output_path=output_path, template_dir=self.template_dir)

    @property
    def sections(self) -> dict[str, SectionOutput]:
        """Return rendered sections dict."""
        return self._sections


def generate_report(
    experiment_dir: Path,
    output_path: Path,
    section_filter: list[str] | None = None,
    template_dir: Path | None = None,
    custom_css: str | None = None,
) -> Path:
    """Convenience function: load experiment dir and generate report.

    Args:
        experiment_dir: path to experiment directory (Parquet files)
        output_path: destination PDF path
        section_filter: optional section IDs to include
        template_dir: optional template directory override
        custom_css: optional additional CSS

    Returns:
        Path to the written PDF
    """
    from backtest_report.persist import read_experiment_dir

    logger.info("Loading experiment from: %s", experiment_dir)
    data, meta = read_experiment_dir(experiment_dir)

    report = BacktestReport(
        data=data,
        meta=meta,
        section_filter=section_filter,
        template_dir=template_dir,
        custom_css=custom_css,
    )
    return report.generate(output_path=output_path)


def from_pysystemtrade(
    system_path: Path,
    output_path: Path,
    section_filter: list[str] | None = None,
    template_dir: Path | None = None,
    custom_css: str | None = None,
) -> Path:
    """Generate report from a pysystemtrade System pickle.

    Args:
        system_path: path to pickled System object
        output_path: destination PDF path
        section_filter: optional section IDs to include
        template_dir: optional template directory override
        custom_css: optional additional CSS

    Returns:
        Path to the written PDF
    """
    from backtest_report.adapters.pysystemtrade import load_system, system_to_backtest_data

    system = load_system(system_path)
    data, config = system_to_backtest_data(system)

    from backtest_report.models import BacktestMeta

    meta = BacktestMeta(
        config=config,
        generated_at=datetime.now(),
        report_version="0.1.0",
        data_checksums={},
        notes="Loaded from pysystemtrade System pickle",
    )

    report = BacktestReport(
        data=data,
        meta=meta,
        section_filter=section_filter,
        template_dir=template_dir,
        custom_css=custom_css,
    )
    return report.generate(output_path=output_path)