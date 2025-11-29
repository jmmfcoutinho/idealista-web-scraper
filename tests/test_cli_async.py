"""Tests for async CLI options.

Tests the --async and --concurrency CLI options for all scraping commands.
"""

from __future__ import annotations

from typer.testing import CliRunner

from idealista_scraper.__main__ import app

runner = CliRunner()


class TestAsyncPrescrapeCommand:
    """Tests for async prescrape command options."""

    def test_prescrape_async_help(self) -> None:
        """Test that prescrape shows async options in help."""
        result = runner.invoke(app, ["prescrape", "--help"])

        assert result.exit_code == 0
        assert "--async" in result.output or "async" in result.output.lower()
        assert "--concurrency" in result.output

    def test_prescrape_async_dry_run(self) -> None:
        """Test prescrape with --async and --dry-run."""
        result = runner.invoke(app, ["prescrape", "--async", "--dry-run"])

        assert result.exit_code == 0
        assert "[DRY RUN]" in result.output
        assert "async" in result.output.lower()

    def test_prescrape_sync_dry_run(self) -> None:
        """Test prescrape with --sync and --dry-run."""
        result = runner.invoke(app, ["prescrape", "--sync", "--dry-run"])

        assert result.exit_code == 0
        assert "[DRY RUN]" in result.output
        assert "sync" in result.output.lower()

    def test_prescrape_concurrency_in_dry_run(self) -> None:
        """Test prescrape --async with --concurrency in --dry-run."""
        result = runner.invoke(
            app, ["prescrape", "--async", "--concurrency", "10", "--dry-run"]
        )

        assert result.exit_code == 0
        assert "10" in result.output
        assert (
            "concurrency" in result.output.lower()
            or "browser sessions" in result.output.lower()
        )

    def test_prescrape_concurrency_without_async_warning(self) -> None:
        """Test that --concurrency without --async shows warning."""
        result = runner.invoke(app, ["prescrape", "--concurrency", "10", "--dry-run"])

        assert result.exit_code == 0
        # Should warn that concurrency has no effect without --async
        assert (
            "no effect" in result.output.lower() or "warning" in result.output.lower()
        )


class TestAsyncScrapeCommand:
    """Tests for async scrape command options."""

    def test_scrape_async_help(self) -> None:
        """Test that scrape shows async options in help."""
        result = runner.invoke(app, ["scrape", "--help"])

        assert result.exit_code == 0
        assert "--async" in result.output or "async" in result.output.lower()
        assert "--concurrency" in result.output

    def test_scrape_async_dry_run(self) -> None:
        """Test scrape with --async and --dry-run."""
        result = runner.invoke(
            app, ["scrape", "--concelho", "cascais", "--async", "--dry-run"]
        )

        assert result.exit_code == 0
        assert "[DRY RUN]" in result.output
        assert "async" in result.output.lower()

    def test_scrape_sync_dry_run(self) -> None:
        """Test scrape with --sync and --dry-run."""
        result = runner.invoke(
            app, ["scrape", "--concelho", "cascais", "--sync", "--dry-run"]
        )

        assert result.exit_code == 0
        assert "[DRY RUN]" in result.output
        assert "sync" in result.output.lower()

    def test_scrape_concurrency_in_dry_run(self) -> None:
        """Test scrape --async with --concurrency in --dry-run."""
        result = runner.invoke(
            app,
            [
                "scrape",
                "--concelho",
                "cascais",
                "--async",
                "--concurrency",
                "8",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "8" in result.output

    def test_scrape_concurrency_without_async_warning(self) -> None:
        """Test that --concurrency without --async shows warning."""
        result = runner.invoke(
            app,
            [
                "scrape",
                "--concelho",
                "cascais",
                "--concurrency",
                "10",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        # Should warn that concurrency has no effect without --async
        assert (
            "no effect" in result.output.lower() or "warning" in result.output.lower()
        )

    def test_scrape_concurrency_validation_min(self) -> None:
        """Test that concurrency validates minimum value."""
        result = runner.invoke(
            app,
            [
                "scrape",
                "--concelho",
                "cascais",
                "--async",
                "--concurrency",
                "0",
                "--dry-run",
            ],
        )

        # Should fail validation (min=1)
        assert result.exit_code != 0

    def test_scrape_concurrency_validation_max(self) -> None:
        """Test that concurrency validates maximum value."""
        result = runner.invoke(
            app,
            [
                "scrape",
                "--concelho",
                "cascais",
                "--async",
                "--concurrency",
                "50",
                "--dry-run",
            ],
        )

        # Should fail validation (max=20)
        assert result.exit_code != 0


class TestAsyncScrapeDetailsCommand:
    """Tests for async scrape-details command options."""

    def test_scrape_details_async_help(self) -> None:
        """Test that scrape-details shows async options in help."""
        result = runner.invoke(app, ["scrape-details", "--help"])

        assert result.exit_code == 0
        assert "--async" in result.output or "async" in result.output.lower()
        assert "--concurrency" in result.output

    def test_scrape_details_async_dry_run(self) -> None:
        """Test scrape-details with --async and --dry-run."""
        result = runner.invoke(app, ["scrape-details", "--async", "--dry-run"])

        assert result.exit_code == 0
        assert "[DRY RUN]" in result.output
        assert "async" in result.output.lower()

    def test_scrape_details_sync_dry_run(self) -> None:
        """Test scrape-details with --sync and --dry-run."""
        result = runner.invoke(app, ["scrape-details", "--sync", "--dry-run"])

        assert result.exit_code == 0
        assert "[DRY RUN]" in result.output
        assert "sync" in result.output.lower()

    def test_scrape_details_concurrency_in_dry_run(self) -> None:
        """Test scrape-details --async with --concurrency in --dry-run."""
        result = runner.invoke(
            app, ["scrape-details", "--async", "--concurrency", "12", "--dry-run"]
        )

        assert result.exit_code == 0
        assert "12" in result.output

    def test_scrape_details_with_limit_and_async(self) -> None:
        """Test scrape-details with --limit and --async."""
        result = runner.invoke(
            app,
            ["scrape-details", "--limit", "50", "--async", "--dry-run"],
        )

        assert result.exit_code == 0
        assert "50" in result.output
        assert "async" in result.output.lower()

    def test_scrape_details_concurrency_without_async_warning(self) -> None:
        """Test that --concurrency without --async shows warning."""
        result = runner.invoke(
            app, ["scrape-details", "--concurrency", "10", "--dry-run"]
        )

        assert result.exit_code == 0
        # Should warn that concurrency has no effect without --async
        assert (
            "no effect" in result.output.lower() or "warning" in result.output.lower()
        )


class TestAsyncConcurrencyDefaults:
    """Tests for async concurrency default values."""

    def test_default_concurrency_is_5(self) -> None:
        """Test that default concurrency is 5."""
        result = runner.invoke(
            app, ["scrape", "--concelho", "cascais", "--async", "--dry-run"]
        )

        assert result.exit_code == 0
        # Default should be 5
        assert "5" in result.output

    def test_concurrency_can_be_set_to_1(self) -> None:
        """Test that concurrency can be set to 1."""
        result = runner.invoke(
            app,
            [
                "scrape",
                "--concelho",
                "cascais",
                "--async",
                "--concurrency",
                "1",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "1" in result.output

    def test_concurrency_can_be_set_to_20(self) -> None:
        """Test that concurrency can be set to 20 (max)."""
        result = runner.invoke(
            app,
            [
                "scrape",
                "--concelho",
                "cascais",
                "--async",
                "--concurrency",
                "20",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "20" in result.output
