"""End-to-end integration tests for report generation."""
from __future__ import annotations

from pathlib import Path

from backtest_report.models import BacktestData, SectionOutput
from backtest_report.portfolio import render_portfolio_pnl
from backtest_report.report import BacktestReport, generate_report


class TestBacktestReportOrchestrator:
    def test_backtest_report_init(self, sample_data: BacktestData, sample_meta) -> None:
        report = BacktestReport(data=sample_data, meta=sample_meta)
        assert report.data is not None
        assert report.meta is not None
        assert report.section_filter is None

    def test_section_filter(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        report = BacktestReport(
            data=sample_data,
            meta=sample_meta,
            section_filter=["portfolio_pnl"],
        )
        assert report.section_filter == ["portfolio_pnl"]

    def test_generate_pdf(
        self, sample_data: BacktestData, sample_meta, tmp_path: Path
    ) -> None:
        report = BacktestReport(
            data=sample_data,
            meta=sample_meta,
            section_filter=["header", "portfolio_pnl", "portfolio_stats"],
        )
        output_path = tmp_path / "report.pdf"
        result = report.generate(output_path=output_path)
        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_pdf_has_pdf_magic_bytes(
        self, sample_data: BacktestData, sample_meta, tmp_path: Path
    ) -> None:
        report = BacktestReport(
            data=sample_data,
            meta=sample_meta,
            section_filter=["portfolio_pnl"],
        )
        output_path = tmp_path / "report.pdf"
        report.generate(output_path=output_path)
        data = output_path.read_bytes()
        assert data[:4] == b"%PDF"

    def test_sections_property(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        report = BacktestReport(
            data=sample_data,
            meta=sample_meta,
            section_filter=["portfolio_pnl"],
        )
        # Trigger rendering via generate (which populates _sections)
        output_path = Path("/tmp/test_sections.pdf")
        report.generate(output_path=output_path)
        assert "portfolio_pnl" in report.sections
        assert isinstance(report.sections["portfolio_pnl"], SectionOutput)
        output_path.unlink(missing_ok=True)


class TestGenerateReportConvenience:
    def test_generate_report_from_persist(
        self, sample_data: BacktestData, sample_meta, tmp_path: Path
    ) -> None:
        # First write an experiment dir
        from backtest_report.persist import write_experiment_dir

        config = sample_meta.config
        checksums = sample_meta.data_checksums
        write_experiment_dir(tmp_path / "experiment", sample_data, config, checksums)

        # Now generate report from it
        output_path = tmp_path / "report.pdf"
        result = generate_report(
            experiment_dir=tmp_path / "experiment",
            output_path=output_path,
            section_filter=["portfolio_pnl", "portfolio_stats"],
        )
        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0


class TestSectionRenderingPipeline:
    def test_all_registered_sections_rendering(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        """Test that all currently registered sections can be rendered without error."""
        report = BacktestReport(
            data=sample_data,
            meta=sample_meta,
            # All currently implemented sections (S17: instrument sections registered)
            section_filter=[
                "header",
                "portfolio_pnl",
                "monthly_returns",
                "portfolio_stats",
                "rolling_stats",
                "instrument_pnl",
                "instrument_table",
                "position_snapshot",
                "attribution",
                "appendix",
            ],
        )
        output_path = Path("/tmp/test_all_sections.pdf")
        report.generate(output_path=output_path)
        assert output_path.exists()
        # Verify sections were populated
        for section_id in report.section_filter:
            assert section_id in report.sections
        output_path.unlink(missing_ok=True)

    def test_html_intermediate_contains_sections(
        self, sample_data: BacktestData, sample_meta
    ) -> None:
        from backtest_report.render import assemble_html

        sections = {
            "portfolio_pnl": render_portfolio_pnl(sample_data, sample_meta),
        }
        html = assemble_html(sections=sections, meta=sample_meta)
        assert "Cumulative Returns" in html
        assert "data:image/png;base64," in html
