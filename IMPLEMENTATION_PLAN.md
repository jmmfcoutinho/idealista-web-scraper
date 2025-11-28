# Idealista Scraper – Phased Implementation Plan

This document describes a complete, phased plan to implement the Idealista scraper.
It is standalone and assumes only basic familiarity with Python.

Design goals:
- Modern Python best practices (type hints, `logging`, `pathlib`, dependency injection where useful).
- Google style docstrings.
- Strong typing (mypy-friendly) without overengineering.
- Simple, modular structure: clear separation of config, scraping, persistence, and export.
- SQLite + SQLAlchemy for storage, easy to migrate to a production DB.

The plan is organized in phases. Each phase can be merged independently and builds on the previous ones.

---

## Phase 0 – Repository & Tooling Baseline

**Goal:** Ensure a clean Python project skeleton and tooling for type checking, formatting, and testing.

### 0.1. Project Layout

Target structure (some files may already exist; adapt as needed):

```text
idealista-web-scraper/
├── src/
│   └── idealista_scraper/
│       ├── __init__.py
│       ├── __main__.py          # CLI entry point
│       ├── config/
│       │   ├── __init__.py
│       │   └── settings.py
│       ├── db/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── models.py
│       ├── scraping/
│       │   ├── __init__.py
│       │   ├── client.py        # Zyte / HTTP client abstraction
│       │   ├── selectors.py     # Parsing helpers based on 
│       │   ├── pre_scraper.py   # Phase 1 logic
│       │   ├── listings_scraper.py
│       │   └── details_scraper.py
│       ├── export/
│       │   ├── __init__.py
│       │   └── exporters.py
│       └── utils/
│           ├── __init__.py
│           ├── logging.py
│           └── time_utils.py
├── config.yaml
├── config.example.yaml
├── .env
├── .env.example
├── IMPLEMENTATION_PLAN.md
├── pyproject.toml
├── README.md
└── tests/
    └── ...
```

### 0.2. Dependencies

Use `pyproject.toml` (PEP 621) with `uv`/`pip`/`poetry` – implementation detail is flexible. Required libs:

- Core
  - `sqlalchemy>=2.0`
  - `alembic` (optional but recommended later for migrations)
  - `pydantic>=2` (for config objects and validation)
  - `python-dotenv` (load `.env`)
  - `typer` or `click` (CLI – plan assumes `typer`)
- Scraping
  - `playwright` (for Bright Data Scraping Browser connection)
  - `brightdata-sdk` (optional, for SDK features)
  - `requests` or `httpx` (for simple HTTP requests)
- Export
  - `pandas`
  - `pyarrow` (for Parquet)

Dev tooling:
- `mypy` (type checking)
- `ruff` or `flake8` (linting)
- `black` (formatting)
- `pytest` (tests)

### 0.3. Conventions

- Use `pathlib.Path` for paths.
- Use `logging` for logs, configured centrally in `utils/logging.py`.
- Use Google style docstrings:

  ```python
  def foo(bar: str) -> int:
      """Short summary.

      Args:
          bar: Description.

      Returns:
          Description.
      """
  ```

- Strict-ish typing: `from __future__ import annotations`, avoid `Any`.

---

## Phase 1 – Configuration Layer

**Goal:** Single, well-typed configuration source combining YAML, environment variables, and CLI flags.

### 1.1. Config Data Models

Use `pydantic` models in `config/settings.py`:

- `DatabaseConfig`
  - `url: str` (from `DATABASE_URL` or `config.yaml`)
- `ScrapingConfig`
  - `delay_seconds: float`
  - `max_retries: int`
  - `use_zyte: bool`
  - `max_pages: int | None` (for test runs)
- `FilterConfig`
  - `min_price: int | None`
  - `max_price: int | None`
  - `min_size: int | None`
  - `max_size: int | None`
  - `typology: str | None`  # e.g. "t3"
- `RunConfig`
  - `operation: Literal["comprar", "arrendar", "both"]`
  - `geographic_level: Literal["concelho", "distrito"]`
  - `locations: list[str]`  # slugs
  - `property_types: list[str]`
  - `scraping: ScrapingConfig`
  - `filters: FilterConfig`
  - `database: DatabaseConfig`

Expose a function:

```python
def load_config(config_path: Path | None = None, cli_overrides: dict[str, Any] | None = None) -> RunConfig:
    """Load configuration from YAML, env vars, and optional CLI overrides.

    Precedence: CLI > ENV > YAML > defaults.
    """
```

### 1.2. YAML and ENV Handling

- Load `.env` via `dotenv.load_dotenv()` in `settings.py` or early in `__main__.py`.
- Read YAML (`config.yaml`) with `yaml.safe_load`.
- Map ENV variables for secrets and production DB (e.g. `DATABASE_URL`, `ZYTE_API_KEY`).

### 1.3. CLI

Implement CLI in `__main__.py` using `typer`:

Commands:
- `prescrape` – Phase 2.
- `scrape` – Phase 3.
- `scrape-details` – Phase 4.
- `export` – Phase 5.

Each command:
- Accepts `--config` (path), `--operation`, `--district`, `--concelho`, `--dry-run`, etc.
- Builds `cli_overrides` dict passed into `load_config`.

---

## Phase 2 – Database Models and Session Management

**Goal:** Define SQLAlchemy models and a simple session factory for SQLite by default.

### 2.1. SQLAlchemy Base and Engine (`db/base.py`)

- Use SQLAlchemy 2.0 style.

Key elements:
- `Base = declarative_base()`
- `def create_engine_from_url(url: str) -> Engine`
- `def get_session_factory(url: str) -> sessionmaker[Session]`

All functions documented with Google-style docstrings and typed.

### 2.2. Models (`db/models.py`)

Define ORM models based on `architecture.md`:

- `District`
  - `id: int` (PK)
  - `name: str`
  - `slug: str` (unique)
  - `listing_count: int | None`
  - `last_scraped: datetime | None`
  - `created_at: datetime`

- `Concelho`
  - `id: int`
  - `district_id: int` (FK)
  - `name: str`
  - `slug: str`
  - `listing_count: int | None`
  - `last_scraped: datetime | None`

- `Listing`
  - `id: int`
  - `idealista_id: int` (unique)
  - `concelho_id: int` (FK)
  - `operation: str` ("comprar" or "arrendar")
  - `property_type: str`
  - `url: str`
  - `title: str | None`
  - `price: int | None`
  - `price_per_sqm: float | None`
  - `area_gross: float | None`
  - `area_useful: float | None`
  - `typology: str | None`
  - `bathrooms: int | None`
  - Booleans for equipment/flags (elevator, garage, pool, garden, luxury, sea_view, etc.)
  - `energy_class: str | None`
  - `condition: str | None`
  - `year_built: int | None`
  - `street: str | None`
  - `neighborhood: str | None`
  - `parish: str | None`
  - `agency_name: str | None`
  - `agency_url: str | None`
  - `reference: str | None`
  - `tags: str | None` (comma-separated or JSON string)
  - `first_seen: datetime`
  - `last_seen: datetime`
  - `is_active: bool`
  - `raw_data: dict[str, Any]` (JSON column)
  - timestamps

- `ListingHistory`
  - `id: int`
  - `listing_id: int` (FK)
  - `price: int | None`
  - `scraped_at: datetime`
  - `changes: dict[str, Any]` (JSON)

- `ScrapeRun`
  - `id: int`
  - `started_at: datetime`
  - `ended_at: datetime | None`
  - `status: str`  # e.g. "running", "success", "failed"
  - `config: dict[str, Any]` (JSON snapshot)
  - `error_message: str | None`

Relationships:
- `District.concelhos` (one-to-many)
- `Concelho.listings` (one-to-many)
- `Listing.history` (one-to-many)

### 2.3. Database Initialization

- Function in `db/base.py`:

  ```python
  def init_db(url: str) -> None:
      """Create all tables for the configured database URL if they do not exist."""
  ```

- Call `init_db` from CLI before running scrapers.

---

## Phase 3 – HTTP / Zyte Client and Selector Helpers

**Goal:** Create a simple client abstraction and HTML parsing helpers, isolated from scraping logic.

### 3.1. HTTPClient Abstraction (`scraping/client.py`)

Define a small interface class and at least one implementation.

> **UPDATE (2025-11-28):** After testing, Zyte API fails with 520 Website Ban errors on all Idealista URLs. 
> Switched to **Bright Data Scraping Browser** which successfully bypasses Idealista's anti-bot protection.
> See `IMPLEMENTATION_PLAN_PROGRESS_LOG.md` for full test results.

```python
class PageClient(Protocol):
    """Protocol for fetching HTML pages.

    Implementations may use Bright Data, Zyte, httpx, requests, etc.
    """

    def get_html(self, url: str, wait_selector: str | None = None) -> str:
        """Return the HTML content for the given URL.

        Args:
            url: The URL to fetch.
            wait_selector: Optional CSS selector to wait for (for JS-rendered pages).

        Raises:
            RuntimeError: If the page could not be fetched.
        """
```

Implementations:
- `BrightDataClient(PageClient)` – **RECOMMENDED** – connects to Bright Data Scraping Browser via Playwright.
  - Uses Playwright to connect via WebSocket to `wss://brd.superproxy.io:9222`
  - Requires `BRIGHTDATA_BROWSER_USER` and `BRIGHTDATA_BROWSER_PASS` environment variables
  - Supports `wait_for_selector` for JavaScript-rendered content
  - Successfully tested against Idealista (see progress log)
  - Example:
    ```python
    from playwright.sync_api import sync_playwright
    
    BROWSER_WS = f"wss://{user}:{password}@brd.superproxy.io:9222"
    
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(BROWSER_WS)
        page = browser.new_page()
        page.goto(url, timeout=120_000)
        page.wait_for_selector(wait_selector, timeout=30_000)
        html = page.content()
        browser.close()
    ```

- `ZyteClient(PageClient)` – **NOT RECOMMENDED** – Zyte API (fails on Idealista with 520 bans).
  - Uses `requests` to POST to `https://api.zyte.com/v1/extract`.
  - **WARNING**: Tested 2025-11-28 and all requests returned 520 Website Ban errors.
  - Payload example:
    ```python
    {
        "url": url,
        "browserHtml": True,
        "actions": [
            {
                "action": "waitForSelector",
                "selector": {"type": "css", "value": wait_selector},
                "timeout": 15  # Max 15 seconds allowed by Zyte
            }
        ] if wait_selector else []
    }
    ```
  - Response contains `browserHtml` key with rendered HTML (not base64 encoded).
  - Retry on HTTP 520 ("Website Ban") with exponential backoff.
- (Optional) `RequestsClient(PageClient)` for local dev (won't work for JS-rendered content).

Constructor should accept a `ScrapingConfig` and `ZYTE_API_KEY`.

**Wait Selectors by Page Type** (see `html/zyte/FINDINGS.md` for full details):
- Homepage: `nav.locations-list`
- District concelhos page: `section.municipality-search` (may timeout, but still returns content)
- Search results: `article.item`
- Listing detail: `section.detail-info`

### 3.2. Selector Helpers (`scraping/selectors.py`)

Based on `html/zyte/FINDINGS.md`, define pure functions to parse HTML into typed structures using `BeautifulSoup`.

Data models (Pydantic or `@dataclass`) for parsed entities:

- `ParsedListingCard`
  - `idealista_id: int`  # from `data-element-id` attribute
  - `url: str`  # from `a.item-link` href
  - `title: str`  # from `a.item-link` text
  - `price: int | None`  # from `span.item-price`, parsed
  - `operation: Literal["comprar", "arrendar"]`
  - `property_type: str`
  - `summary_location: str | None`
  - `details_raw: list[str]`  # from `span.item-detail` elements (e.g., ["T3", "110 m² área bruta"])
  - `description: str | None`  # from `p.ellipsis`
  - `agency_name: str | None`  # from `picture.logo-branding img` alt
  - `agency_url: str | None`  # from `picture.logo-branding a` href
  - `image_url: str | None`  # from `img[alt="Primeira foto do imóvel"]` src
  - `tags: list[str]`

- `ParsedListingDetail`
  - All extra fields from the detail page (location breakdown, characteristics, equipment, energy cert, description).
  - Key selectors:
    - Title: `h1`
    - Price: `span.info-data-price`
    - Location: `span.main-info__title-minor`
    - Features: `div.info-features span` elements
    - Tags: `div.detail-info-tags span.tag`
    - Description: `div.comment p`

- `SearchMetadata`
  - `total_count: int`  # from `h1#h1-container` text, e.g., "4.423 casas..."
  - `page: int`  # from `div.pagination li.selected span`
  - `has_next_page: bool`  # from `div.pagination li.next`
  - `last_page: int | None`  # parsed from pagination links
  - `lowest_price_on_page: int | None`

- `ParsedConcelhoLink`
  - `name: str`
  - `slug: str`
  - `href: str`

- `ParsedDistrictInfo`
  - `name: str`
  - `slug: str`
  - `concelhos: list[ParsedConcelhoLink]`
  - `listing_count: int | None`

Parsing functions:

- `parse_listings_page(html: str, operation: str) -> tuple[list[ParsedListingCard], SearchMetadata]`
  - Selector: `article.item` with `data-element-id` attribute (filters out ads)
  - Returns 30 listings per page
  
- `parse_listing_detail(html: str) -> ParsedListingDetail`

- `parse_homepage_districts(html: str) -> list[ParsedDistrictInfo]`
  - Container: `nav.locations-list`
  - Regions: `h3.region-title`
  - Subregions (districts): `a.subregion`
  - Municipalities: `a.icon-elbow`

- `parse_concelhos_page(html: str) -> list[ParsedConcelhoLink]`
  - Links matching `/comprar-casas/` or `/arrendar-casas/`

These functions should:
- Be pure (no I/O, just HTML in / objects out).
- Contain all selectors and small bits of parsing logic.
- Use BeautifulSoup for parsing.

---

## Phase 4 – Pre-Scraper (Part 1)

**Goal:** Implement the pre-scraper that populates `districts` and `concelhos` tables and records listing counts.

### 4.1. Pre-Scraper Service (`scraping/pre_scraper.py`)

Design a simple service class:

```python
class PreScraper:
    """Extracts districts and concelhos from the Idealista homepage.

    This corresponds to Part 1 of the plan.
    """

    def __init__(self, client: PageClient, session_factory: sessionmaker[Session]):
        ...

    def run(self) -> None:
        """Run the pre-scraper and persist results.

        Raises:
            RuntimeError: If scraping repeatedly fails.
        """
```

Responsibilities:
- Fetch homepage.
- Parse districts + counts + concelho links.
- Upsert into `District` and `Concelho` tables.
- Update `listing_count` and `last_scraped`.

Implementation pattern:
- Use small helper functions inside the module (not methods) for parsing the homepage section – keeps class focused on orchestration.

### 4.2. CLI Wiring

- `prescrape` command:
  - Load config & DB session factory.
  - Instantiate `PageClient`.
  - Instantiate `PreScraper` and call `run()`.
  - Log summary (number of districts/concelhos updated).

---

## Phase 5 – Listings Scraper (Part 2)

**Goal:** Implement logic to traverse listings pages with price segmentation and store cover info into `listings`.

### 5.1. Price Segmentation Strategy

As per `SCRAPING_LOGIC.md` and findings:
- 30 listings/page, max 60 pages => ~1,800 listings per search.
- For locations with more results, we segment by `max_price`.

Algorithm (high-level):

1. For a given `(location_slug, operation, property_type)`:
   - Start with `max_price = None` (no upper bound).
2. Fetch the first page sorted by descending price: `?ordem=precos-desc`.
3. Determine total pages:
   - If `pages <= 60`: scrape all pages sequentially, stop.
   - If `pages > 60`: scrape up to page 60, record lowest price on page 60 as `p_low`.
     - Set new `max_price = p_low` and repeat the process, until no more results.

### 5.2. ListingsScraper Service (`scraping/listings_scraper.py`)

Create a class focused on orchestrating this logic.

```python
class ListingsScraper:
    """Scrapes listing cards for configured locations and operations.

    Does not visit detail pages; only cover info.
    """

    def __init__(
        self,
        client: PageClient,
        session_factory: sessionmaker[Session],
        config: RunConfig,
    ) -> None:
        ...

    def run(self) -> None:
        """Run scraping according to the configuration."""
```

Key responsibilities:
- Iterate over `config.locations` (concelhos or distritos depending on `geographic_level`).
- For each location and property type and operation (`comprar`, `arrendar` or both):
  - Run the price-segmentation scraping loop.
  - For each page, call `parse_listings_page`.
  - Upsert entries in `Listing` table:
    - If `idealista_id` exists:
      - Update fields, `last_seen`.
      - Insert row in `ListingHistory` if price changed.
    - Else:
      - Insert new `Listing` with `first_seen` and `last_seen`.

Separation of concerns:
- URL building placed in small helper functions (e.g. `build_search_url(location_slug, operation, property_type, max_price, page)` in `scraping/urls` or `utils/urls.py`).
- DB writes encapsulated in private methods (e.g. `_upsert_listing_cards`).

### 5.3. Rate Limiting and Retries

Use `ScrapingConfig`:
- Sleep `delay_seconds` between page fetches.
- Retry up to `max_retries` on transient errors (HTTP 5xx, Zyte transient issues).
- Implement a small retry helper (functional style) in `utils/time_utils.py`.

### 5.4. CLI Wiring

- `scrape` command:
  - Load config.
  - Initialize DB and `ScrapeRun` row.
  - Run `ListingsScraper.run()`.
  - Update `ScrapeRun` with `ended_at` and status.

---

## Phase 6 – Detail Scraper (Part 3)

**Goal:** Enrich `Listing` rows by visiting individual listing pages and extracting maximum available details.

### 6.1. DetailsScraper Service (`scraping/details_scraper.py`)

```python
class DetailsScraper:
    """Loads individual listing pages and enriches listings in the database."""

    def __init__(
        self,
        client: PageClient,
        session_factory: sessionmaker[Session],
        max_listings: int | None = None,
    ) -> None:
        ...

    def run(self) -> None:
        """Scrape details for a subset of listings.

        The subset may be limited by `max_listings` or other criteria.
        """
```

Strategy:
- Select listings needing details, for example:
  - `description IS NULL OR energy_class IS NULL OR year_built IS NULL`.
  - Or limited by `max_listings` argument.
- For each listing:
  - Fetch `listing.url` via `PageClient`.
  - Parse with `parse_listing_detail`.
  - Update fields on the `Listing` row (`description`, `characteristics`, energy, equipment, etc.).
  - Optionally update `raw_data` with the parsed detail structure.
  - Respect `delay_seconds` and `max_retries`.

### 6.2. CLI Wiring

- `scrape-details --limit 1000`:
  - Load config, DB.
  - Instantiate client and `DetailsScraper(max_listings=limit)`.
  - Run and log counts.

---

## Phase 7 – Export Layer

**Goal:** Implement simple, typed export functions to CSV or Parquet.

### 7.1. Export Functions (`export/exporters.py`)

Use pandas for convenience; keep interface simple.

```python
def export_listings_to_csv(
    session_factory: sessionmaker[Session],
    path: Path,
    filters: ExportFilters,
) -> None:
    """Export listings to a CSV file.

    Args:
        session_factory: Factory to create database sessions.
        path: Output CSV path.
        filters: Filters to limit exported data.
    """


def export_listings_to_parquet(
    session_factory: sessionmaker[Session],
    path: Path,
    filters: ExportFilters,
) -> None:
    """Export listings to a Parquet file.
    """
```

Where `ExportFilters` is a small Pydantic model or `@dataclass`:

- `districts: list[str] | None`
- `concelhos: list[str] | None`
- `operation: str | None`
- `since: datetime | None` (filter by `last_seen` or `first_seen`).

Implementation:
- Query DB for `Listing` (optionally joined with `Concelho`/`District`).
- Convert rows to dictionaries (e.g. using SQLAlchemy row mappings).
- Build a DataFrame, then `to_csv` or `to_parquet`.

### 7.2. CLI Wiring

- `export` command:
  - Args: `--format {csv,parquet}`, `--output PATH`, `--district`, `--concelho`, `--operation`, `--since`.
  - Build `ExportFilters`.
  - Call the corresponding export function.

---

## Phase 8 – Type Checking, Tests, and Hardening

**Goal:** Ensure maintainability and correctness.

### 8.1. Type Checking

- Configure `mypy` in `pyproject.toml` (or `mypy.ini`):
  - Enable strict optional checks.
  - Exclude tests if desired.
- Run `mypy src/` in CI and locally.

### 8.2. Tests

Use `pytest`.

Recommended tests:
- Unit tests for `selectors.py` parsing functions using HTML snapshots saved in `tests/fixtures/`.
- Unit tests for URL builders (ensure correct pagination and filters).
- Unit tests for DB upsert logic with an in-memory SQLite database.
- Smoke tests for CLI commands (using `typer.testing.CliRunner`).

### 8.3. Logging and Observability

- Centralize configuration in `utils/logging.py`:
  - JSON or simple text logs.
  - Use INFO for high-level progress, DEBUG for details.
- Make sure scrapers log progress per location and segment (e.g. "Lisboa, comprar, casas: segment 1 with max_price=None, pages=60").

### 8.4. Failure Handling

- Wrap main CLI commands in try/except to set `ScrapeRun.status` appropriately.
- On fatal errors, log stack traces at ERROR level but exit with non-zero code.

---

## Implementation Order Summary

1. **Phase 0** – Ensure project structure, tooling, and dependencies.
2. **Phase 1** – Implement config models, loader, and basic CLI.
3. **Phase 2** – Implement SQLAlchemy base, models, and DB init.
4. **Phase 3** – Implement `PageClient` and selector helpers (parsers).
5. **Phase 4** – Implement PreScraper and `prescrape` command.
6. **Phase 5** – Implement ListingsScraper (price segmentation) and `scrape` command.
7. **Phase 6** – Implement DetailsScraper and `scrape-details` command.
8. **Phase 7** – Implement export functions and `export` command.
9. **Phase 8** – Add tests, mypy, refine logging, and harden error handling.

Following these phases should yield a clean, maintainable scraper that respects Idealista's structure, stores all data in SQLite via SQLAlchemy, and supports flexible export for downstream analysis.
