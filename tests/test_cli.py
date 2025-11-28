"""Smoke tests for the CLI commands.

Uses typer.testing.CliRunner to test CLI commands without making
actual network requests or modifying real data.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from idealista_scraper.__main__ import app

runner = CliRunner()


class TestCliBasic:
    """Basic CLI tests."""

    def test_cli_help(self) -> None:
        """Test that --help works."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "idealista-scraper" in result.output
        assert "prescrape" in result.output
        assert "scrape" in result.output
        assert "scrape-details" in result.output
        assert "export" in result.output

    def test_cli_no_args_shows_help(self) -> None:
        """Test that running without args shows help."""
        result = runner.invoke(app, [])

        # Typer returns exit code 0 or 2 depending on version when no_args_is_help=True
        assert result.exit_code in (0, 2)
        assert "Usage:" in result.output


class TestPrescrapeCommand:
    """Tests for the prescrape command."""

    def test_prescrape_help(self) -> None:
        """Test prescrape --help."""
        result = runner.invoke(app, ["prescrape", "--help"])

        assert result.exit_code == 0
        assert "prescrape" in result.output
        assert "--config" in result.output
        assert "--dry-run" in result.output
        assert "--verbose" in result.output

    def test_prescrape_dry_run(self) -> None:
        """Test prescrape with --dry-run flag."""
        result = runner.invoke(app, ["prescrape", "--dry-run"])

        assert result.exit_code == 0
        assert "[DRY RUN]" in result.output


class TestScrapeCommand:
    """Tests for the scrape command."""

    def test_scrape_help(self) -> None:
        """Test scrape --help."""
        result = runner.invoke(app, ["scrape", "--help"])

        assert result.exit_code == 0
        assert "scrape" in result.output
        assert "--operation" in result.output
        assert "--district" in result.output
        assert "--concelho" in result.output
        assert "--max-pages" in result.output

    def test_scrape_without_locations_fails(self) -> None:
        """Test that scrape without locations shows error."""
        result = runner.invoke(app, ["scrape"])

        # Should fail because no locations configured
        assert result.exit_code == 1
        assert "No locations configured" in result.output

    def test_scrape_dry_run_with_location(self) -> None:
        """Test scrape with --dry-run and location."""
        result = runner.invoke(app, ["scrape", "--concelho", "cascais", "--dry-run"])

        assert result.exit_code == 0
        assert "[DRY RUN]" in result.output
        assert "cascais" in result.output


class TestScrapeDetailsCommand:
    """Tests for the scrape-details command."""

    def test_scrape_details_help(self) -> None:
        """Test scrape-details --help."""
        result = runner.invoke(app, ["scrape-details", "--help"])

        assert result.exit_code == 0
        assert "scrape-details" in result.output
        assert "--limit" in result.output

    def test_scrape_details_dry_run(self) -> None:
        """Test scrape-details with --dry-run."""
        result = runner.invoke(app, ["scrape-details", "--dry-run"])

        assert result.exit_code == 0
        assert "[DRY RUN]" in result.output

    def test_scrape_details_dry_run_with_limit(self) -> None:
        """Test scrape-details with --dry-run and --limit."""
        result = runner.invoke(app, ["scrape-details", "--limit", "50", "--dry-run"])

        assert result.exit_code == 0
        assert "[DRY RUN]" in result.output
        assert "50" in result.output


class TestExportCommand:
    """Tests for the export command."""

    def test_export_help(self) -> None:
        """Test export --help."""
        result = runner.invoke(app, ["export", "--help"])

        assert result.exit_code == 0
        assert "export" in result.output
        assert "--format" in result.output
        assert "--output" in result.output
        assert "--district" in result.output
        assert "--concelho" in result.output
        assert "--since" in result.output

    def test_export_invalid_format(self) -> None:
        """Test export with invalid format."""
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.txt"
            result = runner.invoke(
                app, ["export", "--format", "invalid", "--output", str(output)]
            )

            assert result.exit_code == 1
            assert "Invalid format" in result.output

    def test_export_invalid_date(self) -> None:
        """Test export with invalid date format."""
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.csv"
            result = runner.invoke(
                app, ["export", "--since", "not-a-date", "--output", str(output)]
            )

            assert result.exit_code == 1
            assert "Invalid date format" in result.output

    def test_export_csv(self) -> None:
        """Test export to CSV with valid parameters."""
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.csv"
            result = runner.invoke(app, ["export", "--output", str(output)])

            # Will succeed (may export 0 listings from empty DB)
            assert result.exit_code == 0
            assert "Exported" in result.output or "listings" in result.output


class TestBalanceCommand:
    """Tests for the balance command."""

    def test_balance_help(self) -> None:
        """Test balance --help."""
        result = runner.invoke(app, ["balance", "--help"])

        assert result.exit_code == 0
        assert "balance" in result.output
        assert "--verbose" in result.output
