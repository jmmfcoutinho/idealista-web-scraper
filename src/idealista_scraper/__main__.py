"""CLI entry point for the Idealista scraper."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from idealista_scraper.config.settings import load_config
from idealista_scraper.db import get_session_factory, init_db
from idealista_scraper.scraping import (
    AsyncDetailsScraper,
    AsyncListingsScraper,
    AsyncPreScraper,
    DetailsScraper,
    ListingsScraper,
    PreScraper,
    create_async_client,
    create_client,
)
from idealista_scraper.utils.billing import CostTracker, get_balance
from idealista_scraper.utils.logging import get_logger, setup_logging

app = typer.Typer(
    name="idealista-scraper",
    help="Scrape real estate listings from Idealista Portugal.",
    no_args_is_help=True,
)

logger = get_logger(__name__)


# Common CLI options
ConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        "-c",
        help="Path to YAML configuration file.",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
]

OperationOption = Annotated[
    str | None,
    typer.Option(
        "--operation",
        "-o",
        help="Operation type: comprar, arrendar, or both.",
    ),
]

DistrictOption = Annotated[
    list[str] | None,
    typer.Option(
        "--district",
        "-d",
        help="District slugs to scrape (can be repeated).",
    ),
]

ConcelhoOption = Annotated[
    list[str] | None,
    typer.Option(
        "--concelho",
        help="Concelho slugs to scrape (can be repeated).",
    ),
]

DryRunOption = Annotated[
    bool,
    typer.Option(
        "--dry-run",
        help="Show what would be done without making changes.",
    ),
]

VerboseOption = Annotated[
    bool,
    typer.Option(
        "--verbose",
        "-v",
        help="Enable verbose logging.",
    ),
]

TrackCostOption = Annotated[
    bool,
    typer.Option(
        "--track-cost",
        help="Track and report Bright Data API costs for this operation.",
    ),
]

AsyncOption = Annotated[
    bool,
    typer.Option(
        "--async/--sync",
        help="Use async concurrent scraping (faster but higher cost).",
    ),
]

ConcurrencyOption = Annotated[
    int,
    typer.Option(
        "--concurrency",
        help="Number of concurrent browser sessions (only with --async).",
        min=1,
        max=20,
    ),
]


def _build_cli_overrides(
    operation: str | None = None,
    districts: list[str] | None = None,
    concelhos: list[str] | None = None,
    max_pages: int | None = None,
) -> dict[str, object]:
    """Build CLI overrides dictionary from command arguments.

    Args:
        operation: Operation type override.
        districts: List of district slugs.
        concelhos: List of concelho slugs.
        max_pages: Maximum pages to scrape.

    Returns:
        Dictionary of CLI overrides for config loading.
    """
    overrides: dict[str, object] = {}

    if operation:
        overrides["operation"] = operation

    if districts:
        overrides["locations"] = districts
        overrides["geographic_level"] = "distrito"
    elif concelhos:
        overrides["locations"] = concelhos
        overrides["geographic_level"] = "concelho"

    if max_pages is not None:
        overrides["max_pages"] = max_pages

    return overrides


@app.command()
def balance(verbose: VerboseOption = False) -> None:
    """Check Bright Data account balance.

    Displays current balance, pending charges, and available credits.
    Requires BRIGHTDATA_API_KEY environment variable.
    """
    setup_logging(level="DEBUG" if verbose else "INFO")

    try:
        account_balance = get_balance()
        typer.echo("\n💰 Bright Data Account Balance")
        typer.echo(f"   Balance:       ${account_balance.balance:.2f}")
        typer.echo(f"   Pending costs: ${account_balance.pending_costs:.2f}")
        typer.echo(f"   Available:     ${account_balance.available:.2f}\n")
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        raise typer.Exit(code=1) from e
    except RuntimeError as e:
        logger.error("API error: %s", e)
        raise typer.Exit(code=1) from e


@app.command()
def prescrape(
    config: ConfigOption = None,
    verbose: VerboseOption = False,
    dry_run: DryRunOption = False,
    track_cost: TrackCostOption = False,
    use_async: AsyncOption = False,
    concurrency: ConcurrencyOption = 5,
) -> None:
    """Scrape districts and concelhos from the Idealista homepage.

    This populates the districts and concelhos tables with location
    data and listing counts.
    """
    setup_logging(level="DEBUG" if verbose else "INFO")

    run_config = load_config(config_path=config)
    logger.info("Loaded configuration: %s", run_config.model_dump())

    # Warn if concurrency is set without async mode
    if concurrency != 5 and not use_async:
        logger.warning(
            "--concurrency has no effect without --async. "
            "Use --async to enable concurrent scraping."
        )

    if dry_run:
        logger.info("[DRY RUN] Would run pre-scraper")
        logger.info("[DRY RUN] Mode: %s", "async" if use_async else "sync")
        if use_async:
            logger.info("[DRY RUN] Concurrency: %d browser sessions", concurrency)
        logger.info("[DRY RUN] Database URL: %s", run_config.database.url)
        logger.info(
            "[DRY RUN] Using Bright Data: %s", run_config.scraping.use_brightdata
        )
        return

    # Initialize database
    logger.info("Initializing database at %s", run_config.database.url)
    init_db(run_config.database.url)

    # Create session factory
    session_factory = get_session_factory(run_config.database.url)

    try:
        if use_async:
            # Use async pre-scraper
            async def run_async_prescraper() -> dict[str, int]:
                client = create_async_client(run_config.scraping)
                scraper = AsyncPreScraper(
                    client=client,
                    session_factory=session_factory,
                    concurrency=concurrency,
                )
                return await scraper.run()

            if track_cost:
                with CostTracker() as tracker:
                    stats = asyncio.run(run_async_prescraper())
                if tracker.report:
                    typer.echo(f"\n💰 {tracker.report}")
            else:
                stats = asyncio.run(run_async_prescraper())
        else:
            # Use sync pre-scraper
            client = create_client(run_config.scraping)
            pre_scraper = PreScraper(client=client, session_factory=session_factory)

            def run_prescraper() -> dict[str, int]:
                return pre_scraper.run()

            if track_cost:
                with CostTracker() as tracker:
                    stats = run_prescraper()
                if tracker.report:
                    typer.echo(f"\n💰 {tracker.report}")
            else:
                stats = run_prescraper()

        logger.info(
            "Pre-scrape completed successfully: "
            "%d districts created, %d updated, %d concelhos created, %d updated",
            stats["districts_created"],
            stats["districts_updated"],
            stats["concelhos_created"],
            stats["concelhos_updated"],
        )
    except RuntimeError as e:
        logger.error("Pre-scrape failed: %s", e)
        raise typer.Exit(code=1) from e


@app.command()
def scrape(
    config: ConfigOption = None,
    operation: OperationOption = None,
    district: DistrictOption = None,
    concelho: ConcelhoOption = None,
    max_pages: Annotated[
        int | None,
        typer.Option("--max-pages", help="Maximum pages to scrape per search."),
    ] = None,
    verbose: VerboseOption = False,
    dry_run: DryRunOption = False,
    track_cost: TrackCostOption = False,
    use_async: AsyncOption = False,
    concurrency: ConcurrencyOption = 5,
) -> None:
    """Scrape listing cards from search results.

    Iterates through configured locations and operations, extracting
    listing information from search result pages.
    """
    setup_logging(level="DEBUG" if verbose else "INFO")

    cli_overrides = _build_cli_overrides(
        operation=operation,
        districts=district,
        concelhos=concelho,
        max_pages=max_pages,
    )

    run_config = load_config(config_path=config, cli_overrides=cli_overrides)
    logger.info("Loaded configuration: %s", run_config.model_dump())

    if not run_config.locations:
        logger.error("No locations configured. Use --district or --concelho.")
        raise typer.Exit(code=1)

    # Warn if concurrency is set without async mode
    if concurrency != 5 and not use_async:
        logger.warning(
            "--concurrency has no effect without --async. "
            "Use --async to enable concurrent scraping."
        )

    if dry_run:
        logger.info("[DRY RUN] Would scrape listings for: %s", run_config.locations)
        logger.info("[DRY RUN] Mode: %s", "async" if use_async else "sync")
        if use_async:
            logger.info("[DRY RUN] Concurrency: %d browser sessions", concurrency)
        logger.info("[DRY RUN] Operations: %s", run_config.operation)
        logger.info("[DRY RUN] Property types: %s", run_config.property_types)
        logger.info("[DRY RUN] Database URL: %s", run_config.database.url)
        logger.info(
            "[DRY RUN] Using Bright Data: %s", run_config.scraping.use_brightdata
        )
        logger.info("[DRY RUN] Max pages per search: %s", run_config.scraping.max_pages)
        return

    # Initialize database
    logger.info("Initializing database at %s", run_config.database.url)
    init_db(run_config.database.url)

    # Create session factory
    session_factory = get_session_factory(run_config.database.url)

    try:
        if use_async:
            # Use async listings scraper
            async def run_async_scraper() -> dict[str, int]:
                client = create_async_client(run_config.scraping)
                scraper = AsyncListingsScraper(
                    client=client,
                    session_factory=session_factory,
                    config=run_config,
                    concurrency=concurrency,
                )
                return await scraper.run()

            if track_cost:
                with CostTracker() as tracker:
                    stats = asyncio.run(run_async_scraper())
                if tracker.report:
                    typer.echo(f"\n💰 {tracker.report}")
            else:
                stats = asyncio.run(run_async_scraper())
        else:
            # Use sync listings scraper
            client = create_client(run_config.scraping)
            scraper = ListingsScraper(
                client=client,
                session_factory=session_factory,
                config=run_config,
            )

            def run_scraper() -> dict[str, int]:
                return scraper.run()

            if track_cost:
                with CostTracker() as tracker:
                    stats = run_scraper()
                if tracker.report:
                    typer.echo(f"\n💰 {tracker.report}")
            else:
                stats = run_scraper()

        logger.info(
            "Scrape completed successfully: "
            "%d listings processed (%d created, %d updated), "
            "%d pages scraped, %d segments",
            stats["listings_processed"],
            stats["listings_created"],
            stats["listings_updated"],
            stats["pages_scraped"],
            stats["segments_scraped"],
        )
    except RuntimeError as e:
        logger.error("Scrape failed: %s", e)
        raise typer.Exit(code=1) from e


@app.command("scrape-details")
def scrape_details(
    config: ConfigOption = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-l", help="Maximum number of listings to process."),
    ] = None,
    verbose: VerboseOption = False,
    dry_run: DryRunOption = False,
    track_cost: TrackCostOption = False,
    use_async: AsyncOption = False,
    concurrency: ConcurrencyOption = 5,
) -> None:
    """Scrape detailed information for individual listings.

    Visits listing detail pages to enrich the database with additional
    information like descriptions, energy ratings, and features.
    """
    setup_logging(level="DEBUG" if verbose else "INFO")

    run_config = load_config(config_path=config)
    logger.info("Loaded configuration: %s", run_config.model_dump())

    # Warn if concurrency is set without async mode
    if concurrency != 5 and not use_async:
        logger.warning(
            "--concurrency has no effect without --async. "
            "Use --async to enable concurrent scraping."
        )

    if dry_run:
        logger.info("[DRY RUN] Would scrape details for up to %s listings", limit)
        logger.info("[DRY RUN] Mode: %s", "async" if use_async else "sync")
        if use_async:
            logger.info("[DRY RUN] Concurrency: %d browser sessions", concurrency)
        logger.info("[DRY RUN] Database URL: %s", run_config.database.url)
        logger.info(
            "[DRY RUN] Using Bright Data: %s", run_config.scraping.use_brightdata
        )
        return

    # Initialize database
    logger.info("Initializing database at %s", run_config.database.url)
    init_db(run_config.database.url)

    # Create session factory
    session_factory = get_session_factory(run_config.database.url)

    try:
        if use_async:
            # Use async details scraper
            async def run_async_details_scraper() -> dict[str, int]:
                client = create_async_client(run_config.scraping)
                scraper = AsyncDetailsScraper(
                    client=client,
                    session_factory=session_factory,
                    max_listings=limit,
                    concurrency=concurrency,
                )
                return await scraper.run()

            if track_cost:
                with CostTracker() as tracker:
                    stats = asyncio.run(run_async_details_scraper())
                if tracker.report:
                    typer.echo(f"\n💰 {tracker.report}")
            else:
                stats = asyncio.run(run_async_details_scraper())
        else:
            # Use sync details scraper
            client = create_client(run_config.scraping)
            scraper = DetailsScraper(
                client=client,
                session_factory=session_factory,
                max_listings=limit,
            )

            def run_scraper() -> dict[str, int]:
                return scraper.run()

            if track_cost:
                with CostTracker() as tracker:
                    stats = run_scraper()
                if tracker.report:
                    typer.echo(f"\n💰 {tracker.report}")
            else:
                stats = run_scraper()

        logger.info(
            "Scrape details completed successfully: "
            "%d listings processed, %d enriched, %d failed",
            stats["listings_processed"],
            stats["listings_enriched"],
            stats["listings_failed"],
        )
    except RuntimeError as e:
        logger.error("Scrape details failed: %s", e)
        raise typer.Exit(code=1) from e


@app.command()
def export(
    config: ConfigOption = None,
    format_: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: csv or parquet.",
        ),
    ] = "csv",
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            help="Output file path.",
        ),
    ] = Path("listings.csv"),
    district: DistrictOption = None,
    concelho: ConcelhoOption = None,
    operation: OperationOption = None,
    since: Annotated[
        str | None,
        typer.Option(
            "--since", help="Export listings seen since this date (YYYY-MM-DD)."
        ),
    ] = None,
    active_only: Annotated[
        bool,
        typer.Option(
            "--active-only/--include-inactive",
            help="Only export active listings (default: active only).",
        ),
    ] = True,
    verbose: VerboseOption = False,
) -> None:
    """Export listings to CSV or Parquet format.

    Exports listing data from the database with optional filters.
    """
    setup_logging(level="DEBUG" if verbose else "INFO")

    run_config = load_config(config_path=config)
    logger.info("Loaded configuration: %s", run_config.model_dump())

    # Validate format
    format_lower = format_.lower()
    if format_lower not in {"csv", "parquet"}:
        logger.error("Invalid format: %s. Use 'csv' or 'parquet'.", format_)
        raise typer.Exit(code=1)

    # Parse since date
    since_datetime: datetime | None = None
    if since:
        try:
            since_datetime = datetime.strptime(since, "%Y-%m-%d")
        except ValueError as e:
            logger.error("Invalid date format: %s. Use YYYY-MM-DD.", since)
            raise typer.Exit(code=1) from e

    # Build filters
    from idealista_scraper.export import ExportFilters

    filters = ExportFilters(
        districts=list(district) if district else [],
        concelhos=list(concelho) if concelho else [],
        operation=operation,
        since=since_datetime,
        active_only=active_only,
    )

    logger.info(
        "Export parameters: format=%s, output=%s, filters=%s",
        format_lower,
        output,
        filters,
    )

    # Initialize database
    logger.info("Initializing database at %s", run_config.database.url)
    init_db(run_config.database.url)

    # Create session factory
    session_factory = get_session_factory(run_config.database.url)

    # Adjust output path extension if needed
    output_path = output
    if format_lower == "parquet" and not str(output).endswith(".parquet"):
        output_path = output.with_suffix(".parquet")
    elif format_lower == "csv" and not str(output).endswith(".csv"):
        output_path = output.with_suffix(".csv")

    # Export based on format
    try:
        from idealista_scraper.export import (
            export_listings_to_csv,
            export_listings_to_parquet,
        )

        if format_lower == "csv":
            count = export_listings_to_csv(session_factory, output_path, filters)
        else:
            count = export_listings_to_parquet(session_factory, output_path, filters)

        logger.info("Export completed successfully: %d listings exported", count)
        typer.echo(f"✅ Exported {count} listings to {output_path}")

    except Exception as e:
        logger.error("Export failed: %s", e)
        raise typer.Exit(code=1) from e


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
