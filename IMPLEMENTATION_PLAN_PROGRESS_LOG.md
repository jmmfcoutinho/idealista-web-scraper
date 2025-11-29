# Implementation Progress Log

This document tracks the progress of implementing the Idealista scraper according to `IMPLEMENTATION_PLAN.md`.

---

## Phase 0 – Repository & Tooling Baseline

**Status:** ✅ Completed  
**Date:** 2025-11-28

### Summary

Established the project skeleton with proper Python packaging, tooling configuration, and all placeholder modules.

### Completed Tasks

#### 0.1. Project Layout

Created the following directory structure:

```
src/
└── idealista_scraper/
    ├── __init__.py
    ├── __main__.py
    ├── config/
    │   ├── __init__.py
    │   └── settings.py
    ├── db/
    │   ├── __init__.py
    │   ├── base.py
    │   └── models.py
    ├── scraping/
    │   ├── __init__.py
    │   ├── client.py
    │   ├── selectors.py
    │   ├── pre_scraper.py
    │   ├── listings_scraper.py
    │   └── details_scraper.py
    ├── export/
    │   ├── __init__.py
    │   └── exporters.py
    └── utils/
        ├── __init__.py
        ├── logging.py
        └── time_utils.py
tests/
├── __init__.py
└── fixtures/
```

#### 0.2. Dependencies

Updated `pyproject.toml` with:

**Core dependencies:**
- `sqlalchemy>=2.0`
- `pydantic>=2`
- `python-dotenv>=1.2.1`
- `pyyaml>=6.0`
- `typer>=0.9`

**Scraping dependencies:**
- `beautifulsoup4>=4.14.2`
- `requests>=2.32.5`
- `httpx>=0.27`
- `lxml>=5.0`

**Export dependencies:**
- `pandas>=2.0`
- `pyarrow>=15.0`

**Dev dependencies:**
- `mypy>=1.8`
- `ruff>=0.3`
- `pytest>=8.0`
- `pytest-cov>=4.0`
- Type stubs for requests, beautifulsoup4, PyYAML, pandas

#### 0.3. Tooling Configuration

Configured in `pyproject.toml`:

- **Ruff**: Linting and formatting with rules for pycodestyle, Pyflakes, isort, bugbear, comprehensions, pyupgrade, unused-arguments, and simplify
- **Mypy**: Strict mode enabled with pydantic plugin
- **Pytest**: Configured with `src` layout

#### 0.4. Configuration Templates

- Created `config.example.yaml` with all configuration options
- Created `.env.example` with environment variable placeholders

#### 0.5. Utility Modules

Implemented:

- `utils/logging.py`: Centralized logging configuration with `setup_logging()` and `get_logger()` functions
- `utils/time_utils.py`: `sleep_with_jitter()` and `retry_with_backoff()` helper functions using Python 3.12 type parameter syntax

### Verification

All checks pass:
- `ruff format src tests` - 19 files formatted
- `ruff check src tests` - All checks passed
- `mypy src` - Success: no issues found in 18 source files

### Notes for Next Engineer

- Phase 1 (Configuration Layer) is ready to begin
- All module files contain placeholder docstrings indicating which phase will implement them
- The CLI entry point (`__main__.py`) has a basic `main()` function that will be expanded in Phase 1

---

## Phase 1 – Configuration Layer

**Status:** ✅ Completed  
**Date:** 2025-11-28

### Summary

Implemented a comprehensive configuration layer with Pydantic models, YAML/ENV/CLI configuration loading, and a full Typer-based CLI.

### Completed Tasks

#### 1.1. Configuration Models (`config/settings.py`)

Implemented Pydantic models:

- **`DatabaseConfig`**: Database connection URL configuration
- **`ScrapingConfig`**: Delay, retries, Zyte usage, max pages settings
- **`FilterConfig`**: Price and size filters with typology validation
- **`RunConfig`**: Main configuration combining all sub-configs with operation, geographic level, locations, and property types

All models include:
- Field validation with Pydantic validators
- Sensible defaults
- Type hints for all attributes

#### 1.2. Configuration Loader

Implemented `load_config()` function with precedence:
1. CLI overrides (highest)
2. Environment variables
3. YAML configuration file
4. Default values (lowest)

Helper functions:
- `_deep_merge()`: Deep dictionary merging
- `_load_yaml_config()`: YAML file loading
- `_get_env_overrides()`: Environment variable parsing
- `_flatten_cli_overrides()`: CLI argument to nested config mapping
- `get_zyte_api_key()`: Secure API key retrieval

#### 1.3. CLI Implementation (`__main__.py`)

Created Typer CLI with commands:

- **`prescrape`**: Pre-scrape districts and concelhos (Phase 4)
- **`scrape`**: Scrape listing cards from search results (Phase 5)
- **`scrape-details`**: Scrape individual listing details (Phase 6)
- **`export`**: Export data to CSV/Parquet (Phase 7)

Common options:
- `--config, -c`: YAML configuration file path
- `--operation, -o`: Operation type (comprar/arrendar/both)
- `--district, -d`: District slugs (repeatable)
- `--concelho`: Concelho slugs (repeatable)
- `--verbose, -v`: Enable debug logging
- `--dry-run`: Preview mode without changes

#### 1.4. Package Exports

Updated `config/__init__.py` with public API:
- `DatabaseConfig`, `FilterConfig`, `RunConfig`, `ScrapingConfig`
- `load_config`, `get_zyte_api_key`

### Verification

All checks pass:
- `ruff format src tests` - Files formatted
- `ruff check src tests` - All checks passed
- `mypy src` - Success: no issues found in 18 source files
- `idealista-scraper --help` - CLI working correctly

### Notes for Next Engineer

- Phase 2 (Database Models) is ready to begin
- CLI commands are implemented but call placeholder logic
- Configuration is fully functional and tested via CLI
- The `config.example.yaml` matches the Pydantic model structure

---

## Phase 2 – Database Models and Session Management

**Status:** ✅ Completed  
**Date:** 2025-11-28

### Summary

Implemented SQLAlchemy 2.0-style ORM models and database utilities for persisting scraped data to SQLite (or any other database).

### Completed Tasks

#### 2.1. SQLAlchemy Base and Engine (`db/base.py`)

Implemented:

- **`Base`**: SQLAlchemy declarative base class for all ORM models
- **`create_engine_from_url(url: str) -> Engine`**: Creates a SQLAlchemy engine from a database URL; automatically creates directories for SQLite databases
- **`get_session_factory(url: str) -> Callable[[], Session]`**: Returns a sessionmaker instance configured with the engine
- **`init_db(url: str) -> None`**: Creates all tables based on registered models

#### 2.2. ORM Models (`db/models.py`)

Implemented all models as specified in the plan:

- **`District`**: Portuguese districts (distritos)
  - Fields: `id`, `name`, `slug` (unique), `listing_count`, `last_scraped`, `created_at`
  - Relationship: `concelhos` (one-to-many)

- **`Concelho`**: Portuguese municipalities (concelhos)
  - Fields: `id`, `district_id` (FK), `name`, `slug` (unique), `listing_count`, `last_scraped`, `created_at`
  - Relationships: `district` (many-to-one), `listings` (one-to-many)

- **`Listing`**: Real estate listings
  - Basic info: `idealista_id` (unique), `operation`, `property_type`, `url`, `title`, `price`, `price_per_sqm`
  - Size/layout: `area_gross`, `area_useful`, `typology`, `bedrooms`, `bathrooms`, `floor`
  - Features (booleans): `has_elevator`, `has_garage`, `has_pool`, `has_garden`, `has_terrace`, `has_balcony`, `has_air_conditioning`, `has_central_heating`, `is_luxury`, `has_sea_view`
  - Property details: `energy_class`, `condition`, `year_built`
  - Location: `street`, `neighborhood`, `parish`
  - Content: `description`, `agency_name`, `agency_url`, `reference`, `tags`, `image_url`
  - Tracking: `first_seen`, `last_seen`, `is_active`, `raw_data` (JSON)
  - Timestamps: `created_at`, `updated_at`
  - Relationships: `concelho` (many-to-one), `history` (one-to-many)

- **`ListingHistory`**: Price/change history for listings
  - Fields: `id`, `listing_id` (FK), `price`, `scraped_at`, `changes` (JSON)
  - Relationship: `listing` (many-to-one)

- **`ScrapeRun`**: Scraper run metadata
  - Fields: `id`, `started_at`, `ended_at`, `status`, `run_type`, `config` (JSON), `error_message`
  - Statistics: `listings_processed`, `listings_created`, `listings_updated`

All models include:
- Type hints using `Mapped[]` (SQLAlchemy 2.0 style)
- Google-style docstrings
- `__repr__()` methods for debugging

#### 2.3. Database Module Exports (`db/__init__.py`)

Exported public API:
- `Base`, `create_engine_from_url`, `get_session_factory`, `init_db`
- `District`, `Concelho`, `Listing`, `ListingHistory`, `ScrapeRun`

### Verification

All checks pass:
- `uv run ruff format src tests` - 1 file reformatted
- `uv run ruff check src tests` - All checks passed
- `uv run mypy src` - Success: no issues found in 18 source files

### Notes for Next Engineer

- Phase 3 (HTTP/Zyte Client and Selector Helpers) is ready to begin
- Database initialization can be done by calling `init_db(config.database.url)`
- The session factory returns a callable that creates new sessions: `session = get_session_factory(url)()`
- All models use server-side defaults for timestamps (`server_default=func.now()`)
- The `Listing` model includes fields for both card-level data (from search pages) and detail-level data (from individual listing pages)

---

## Phase 3 – HTTP / Zyte Client and Selector Helpers

**Status:** ✅ Completed  
**Date:** 2025-11-28

### Summary

Implemented the HTTP client abstraction for fetching HTML pages via Zyte API and pure HTML parsing functions using BeautifulSoup.

### Completed Tasks

#### 3.1. HTTP Client Abstraction (`scraping/client.py`)

Implemented:

- **`PageClient`** (Protocol): Interface for fetching HTML pages with `get_html(url, wait_selector)` method
- **`ZyteClient`**: Zyte API client implementation
  - Uses `browserHtml: true` for JavaScript-rendered content
  - Supports `waitForSelector` actions with 15-second timeout
  - Automatic retry with exponential backoff on HTTP 520 (website ban) and 429 (rate limit)
  - Configurable delay between requests via `ScrapingConfig`
  - Reads `ZYTE_API_KEY` from environment variables
- **`RequestsClient`**: Simple requests-based client for local development (no JS rendering)
  - Includes User-Agent and Accept headers for basic requests
  - Warning logged when wait_selector is provided
- **`ZyteClientError`**: Custom exception for Zyte API errors with status code and ban flag
- **`create_client(config)`**: Factory function to create appropriate client based on configuration

Wait selector constants:
- `WAIT_SELECTOR_HOMEPAGE`: `nav.locations-list`
- `WAIT_SELECTOR_DISTRICT_CONCELHOS`: `section.municipality-search`
- `WAIT_SELECTOR_SEARCH_RESULTS`: `article.item`
- `WAIT_SELECTOR_LISTING_DETAIL`: `section.detail-info`

#### 3.2. Selector Helpers (`scraping/selectors.py`)

Data models (dataclasses):

- **`ParsedListingCard`**: Listing card data from search results
  - `idealista_id`, `url`, `title`, `price`, `operation`, `property_type`
  - `summary_location`, `details_raw`, `description`
  - `agency_name`, `agency_url`, `image_url`, `tags`
- **`SearchMetadata`**: Search results page metadata
  - `total_count`, `page`, `has_next_page`, `last_page`, `lowest_price_on_page`
- **`ParsedListingDetail`**: Individual listing detail page data
  - `title`, `price`, `location`, `features_raw`, `tags`
  - `description`, `reference`, `characteristics`, `energy_class`, `photo_count`
- **`ParsedConcelhoLink`**: Concelho link data
  - `name`, `slug`, `href`
- **`ParsedDistrictInfo`**: District information from homepage
  - `name`, `slug`, `concelhos`, `listing_count`

Parsing functions:

- **`parse_listings_page(html, operation, property_type)`**: Parse search results page
  - Extracts listing cards (30 per page)
  - Filters out ads (articles without `data-element-id`)
  - Parses pagination metadata
- **`parse_listing_detail(html)`**: Parse individual listing detail page
  - Extracts all available fields: title, price, location, features, tags
  - Parses description, reference, characteristics, energy class, photo count
- **`parse_homepage_districts(html)`**: Parse Idealista homepage
  - Extracts districts from `nav.locations-list`
  - Links districts with their associated concelhos
- **`parse_concelhos_page(html)`**: Parse district concelhos page
  - Extracts all concelho links from the municipality search section

Helper functions:
- `_parse_price(price_text)`: Parse Portuguese price format ("36.500.000€")
- `_parse_count_from_text(text)`: Extract count from text ("4.423 casas...")
- `_extract_slug_from_href(href)`: Extract location slug from URL path
- `_get_text(element, strip)`: Safely get text from BeautifulSoup element
- `_get_attr(element, attr)`: Safely get attribute from BeautifulSoup element

#### 3.3. Module Exports (`scraping/__init__.py`)

Exported public API:
- Client: `PageClient`, `ZyteClient`, `RequestsClient`, `ZyteClientError`, `create_client`
- Wait selectors: `WAIT_SELECTOR_*` constants
- Data models: `ParsedListingCard`, `ParsedListingDetail`, `SearchMetadata`, `ParsedConcelhoLink`, `ParsedDistrictInfo`
- Parsing functions: `parse_listings_page`, `parse_listing_detail`, `parse_homepage_districts`, `parse_concelhos_page`

### Verification

All checks pass:
- `uv run ruff format src tests` - Files formatted
- `uv run ruff check src tests` - All checks passed
- `uv run mypy src` - Success: no issues found in 18 source files

### Notes for Next Engineer

- Phase 4 (Pre-Scraper) is ready to begin
- The `ZyteClient` requires `ZYTE_API_KEY` environment variable to be set
- Parsing functions are pure (no I/O) and can be tested with HTML fixtures
- The `create_client(config)` factory function should be used to instantiate the appropriate client
- Wait selectors are provided as constants for each page type
- All parsing functions handle missing elements gracefully (return None or empty lists)

---

## Phase 4 – Pre-Scraper (Part 1)

**Status:** ✅ Completed  
**Date:** 2025-11-28

### Summary

Implemented the pre-scraper that populates the `districts` and `concelhos` tables by fetching and parsing the Idealista homepage and district concelhos pages.

### Completed Tasks

#### 4.1. PreScraper Service (`scraping/pre_scraper.py`)

Implemented the `PreScraper` class:

- **Constructor**: Accepts `PageClient` and session factory
- **`run()` method**: Main entry point that orchestrates the pre-scraping process
  - Fetches the Idealista homepage using the configured PageClient
  - Parses district information using `parse_homepage_districts()`
  - For each district, fetches the concelhos page if no concelhos were found on the homepage
  - Upserts districts and concelhos into the database
  - Creates a `ScrapeRun` record to track the operation
  - Returns statistics: districts created/updated, concelhos created/updated
- **Helper methods**:
  - `_create_scrape_run()`: Creates a new ScrapeRun record
  - `_process_district()`: Processes a single district and its concelhos
  - `_upsert_district()`: Upserts a district record
  - `_upsert_concelho()`: Upserts a concelho record
  - `_fetch_concelhos_for_district()`: Fetches concelho info from the district's concelhos page

Key features:
- Uses the existing `PageClient` protocol for HTTP requests
- Applies wait selectors (`WAIT_SELECTOR_HOMEPAGE`, `WAIT_SELECTOR_DISTRICT_CONCELHOS`)
- Proper error handling with `ScrapeRun` status updates
- Detailed logging at INFO and DEBUG levels
- Returns statistics dictionary for CLI output

#### 4.2. CLI Wiring (`__main__.py`)

Updated the `prescrape` command:

- Loads configuration from YAML file and CLI options
- Initializes the database with `init_db()`
- Creates session factory with `get_session_factory()`
- Creates the appropriate PageClient with `create_client(config.scraping)`
- Instantiates `PreScraper` and calls `run()`
- Logs summary of districts/concelhos created and updated
- Handles errors with proper exit codes
- Supports `--dry-run` flag to preview configuration without scraping

#### 4.3. Module Exports (`scraping/__init__.py`)

Updated exports to include:
- `PreScraper` class

### Verification

All checks pass:
- `uv run ruff format src tests` - 1 file reformatted
- `uv run ruff check src tests` - All checks passed (5 errors auto-fixed with --fix)
- `uv run mypy src` - Success: no issues found in 18 source files

### CLI Usage

```bash
# Run pre-scraper with default config
idealista-scraper prescrape

# Run with custom config file
idealista-scraper prescrape -c config.yaml

# Run with verbose logging
idealista-scraper prescrape -v

# Dry run (preview configuration without scraping)
idealista-scraper prescrape --dry-run
```

### Notes for Next Engineer

- Phase 5 (Listings Scraper) is ready to begin
- The `PreScraper` uses the same `PageClient` interface as future scrapers
- Districts and concelhos are upserted (created or updated) to allow re-running
- The `ScrapeRun` table records each pre-scrape operation for tracking
- To test locally without Zyte, set `scraping.use_zyte: false` in config (won't work for JS-rendered content)
- The pre-scraper fetches the concelhos page for each district to get complete concelho lists

---

## Provider Testing – Zyte vs Bright Data

**Status:** ✅ Completed  
**Date:** 2025-11-28

### Summary

Tested both Zyte and Bright Data scraping providers against Idealista. Zyte failed completely with 520 Website Ban errors, while Bright Data Scraping Browser succeeded on all tests.

### Zyte API Test Results

Tested 3 different URL types:

| URL Type | Status | Time | Result |
|----------|--------|------|--------|
| Search (Cascais) | ❌ 520 | 65.6s | Website Ban |
| Listing Detail | ❌ 520 | 65.9s | Website Ban |
| Homepage | ❌ 520 | 65.9s | Website Ban |

**Conclusion:** Zyte API cannot bypass Idealista's anti-bot protection. All requests failed with "Zyte API could not get a ban-free response in a reasonable time."

### Bright Data Scraping Browser Test Results

Tested using Playwright + Bright Data Scraping Browser via WebSocket:

| URL Type | Status | Size | Time | Result |
|----------|--------|------|------|--------|
| Search (Cascais) | ✅ 200 | 386,777 bytes | 54.4s | Full content with 30 listings |
| Homepage | ✅ 200 | 105,880 bytes | 13.6s | Full content |

**Conclusion:** Bright Data Scraping Browser successfully bypasses Idealista's anti-bot protection and retrieves full JavaScript-rendered content.

### Decision

**Switch from Zyte to Bright Data Scraping Browser.**

### Implementation Changes Required

1. Replace `ZyteClient` with `BrightDataClient` in `scraping/client.py`
2. Use Playwright to connect to Bright Data Scraping Browser via WebSocket
3. Update config to use `BRIGHTDATA_*` environment variables instead of `ZYTE_API_KEY`
4. Add `playwright` and `brightdata-sdk` to dependencies

### Credentials

- Scraping Browser zone: `scraping_browser1`
- WebSocket endpoint: `wss://brd-customer-hl_52df750f-zone-scraping_browser1:<password>@brd.superproxy.io:9222`
- API Key stored in: `BRIGHTDATA_API_KEY` env var

### Test Scripts

- `test_zyte_quick.py`: Zyte API test (all failed)
- `test_brightdata_quick.py`: Bright Data Scraping Browser test (all passed)
- Sample HTML saved to `html/brightdata_*.html` for inspection

---

## Phase 5 – Listings Scraper (Part 2)

**Status:** ✅ Completed  
**Date:** 2025-11-28

### Summary

Implemented the listings scraper that traverses Idealista search result pages with price segmentation and stores cover info into the listings table.

### Completed Tasks

#### 5.1. URL Building Helpers (`scraping/listings_scraper.py`)

Implemented helper functions for building Idealista URLs:

- **`build_search_url()`**: Builds search URLs with location, operation, property type, pagination, price filters, and sorting
- **`build_paginated_url()`**: Adds or updates pagination parameter to existing URLs
- **Constants**:
  - `IDEALISTA_BASE_URL`: `https://www.idealista.pt`
  - `MAX_PAGES_LIMIT`: 60 (Idealista's maximum visible pages)

#### 5.2. Data Classes

- **`ScrapeSegment`**: Represents a price segment for scraping
  - `location_slug`, `operation`, `property_type`, `max_price`, `min_price`
  - String representation for logging

#### 5.3. ListingsScraper Service

Implemented the main `ListingsScraper` class with:

**Constructor:**
- Accepts `PageClient`, session factory, and `RunConfig`
- Maintains a concelho cache for performance

**Main `run()` method:**
- Creates `ScrapeRun` record to track the operation
- Iterates over configured locations, operations, and property types
- Returns statistics: `listings_processed`, `listings_created`, `listings_updated`, `pages_scraped`, `segments_scraped`
- Handles errors and updates `ScrapeRun` status appropriately

**Price Segmentation (`_scrape_location()`):**
- Implements the price segmentation strategy from the plan
- Starts with no price limit, sorted by price descending
- If total pages > 60, scrapes up to page 60 and notes lowest price
- Creates new segment with `max_price = lowest_price` and repeats
- Continues until no more results or minimum price boundary reached

**Segment Scraping (`_scrape_segment()`):**
- Fetches pages sequentially up to `MAX_PAGES_LIMIT` (60)
- Uses `WAIT_SELECTOR_SEARCH_RESULTS` for page loading
- Parses listings using `parse_listings_page()`
- Tracks lowest price for segmentation
- Commits after each page for durability
- Returns `next_max_price` if more segments needed

#### 5.4. Listing Upsert Logic

**`_upsert_listing_card()`:**
- Looks up existing listing by `idealista_id`
- Calls `_create_listing()` or `_update_listing()` accordingly

**`_create_listing()`:**
- Creates new `Listing` record with all card data
- Parses typology, area, and bedrooms from `details_raw`
- Normalizes URL to absolute form
- Sets `first_seen` and `last_seen` timestamps

**`_update_listing()`:**
- Updates existing listing fields
- Tracks price changes and creates `ListingHistory` record
- Updates `last_seen` and marks as active

**`_parse_details()`:**
- Parses typology (T0, T1, T2, etc.) from raw details
- Extracts area in square meters
- Extracts bedroom count

**`_normalize_url()`:**
- Converts relative URLs to absolute

**`_get_concelho()`:**
- Caches concelho lookups for performance

#### 5.5. CLI Wiring (`__main__.py`)

Updated the `scrape` command:

- Loads configuration with CLI overrides
- Validates locations are configured
- Supports `--dry-run` to preview configuration
- Initializes database with `init_db()`
- Creates session factory and page client
- Instantiates `ListingsScraper` and runs it
- Logs comprehensive summary of results
- Handles errors with proper exit codes

#### 5.6. Module Exports (`scraping/__init__.py`)

Updated exports to include:
- `ListingsScraper` class

### Verification

All checks pass:
- `uv run ruff format src tests` - 4 files reformatted
- `uv run ruff check src tests` - All checks passed
- `uv run mypy src` - Success: no issues found in 18 source files

### CLI Usage

```bash
# Scrape listings for a specific concelho
idealista-scraper scrape --concelho cascais

# Scrape multiple locations
idealista-scraper scrape --concelho cascais --concelho sintra

# Scrape a district
idealista-scraper scrape --district lisboa-distrito

# Scrape with specific operation
idealista-scraper scrape --concelho cascais -o comprar

# Limit pages per search (for testing)
idealista-scraper scrape --concelho cascais --max-pages 5

# Dry run (preview configuration)
idealista-scraper scrape --concelho cascais --dry-run

# Verbose logging
idealista-scraper scrape --concelho cascais -v
```

### Algorithm Summary

The price segmentation algorithm works as follows:

1. **Initial Request**: Fetch first page sorted by price descending (`ordem=precos-desc`)
2. **Check Total Pages**:
   - If ≤60 pages: Scrape all pages sequentially, done
   - If >60 pages: Continue to step 3
3. **Segment by Price**:
   - Scrape pages 1-60
   - Record lowest price on page 60 as `p_low`
   - Create new segment with `max_price = p_low`
   - Repeat from step 1
4. **Termination**: Stop when no more results or `max_price ≤ min_price`

### Notes for Next Engineer

- Phase 6 (Detail Scraper) is ready to begin
- The `ListingsScraper` shares the same `PageClient` interface as `PreScraper`
- Listings are upserted (created or updated) to support incremental scraping
- Price changes are tracked in `ListingHistory` table
- The `ScrapeRun` table records each scrape operation with statistics
- Concelho cache improves performance for repeated lookups
- All typology/area parsing handles Portuguese formats (e.g., "110 m² área bruta")

---

## Phase 6 – Detail Scraper (Part 3)

**Status:** ✅ Completed  
**Date:** 2025-11-28

### Summary

Implemented the details scraper that visits individual listing pages and enriches the database with additional information like descriptions, energy ratings, features, and characteristics.

### Completed Tasks

#### 6.1. DetailsScraper Service (`scraping/details_scraper.py`)

Implemented the `DetailsScraper` class with the following features:

**Constructor:**
- Accepts `PageClient`, session factory, and optional `max_listings` parameter
- Same pattern as `ListingsScraper` for consistency

**Main `run()` method:**
- Creates `ScrapeRun` record to track the operation
- Queries listings needing details (where description or energy_class is NULL)
- Orders by `last_seen` descending to prioritize recently seen listings
- Returns statistics: `listings_processed`, `listings_enriched`, `listings_failed`
- Handles errors and updates `ScrapeRun` status appropriately
- Commits after each listing for durability

**Listing Selection (`_get_listings_needing_details()`):**
- Filters active listings (`is_active = True`)
- Selects listings missing key detail fields:
  - `description IS NULL`
  - `energy_class IS NULL`
- Limits results by `max_listings` if specified
- Uses SQLAlchemy `or_()` for flexible filtering

**Detail Scraping (`_scrape_listing_detail()`):**
- Fetches listing URL via `PageClient`
- Uses `WAIT_SELECTOR_LISTING_DETAIL` for page loading
- Parses HTML with `parse_listing_detail()`
- Updates listing with extracted data
- Returns success/failure status

#### 6.2. Listing Update Logic

**`_update_listing_from_detail()`:**
Updates listing with data from detail page:
- Description
- Reference number
- Energy class (normalized)
- Location (street, neighborhood, parish)
- Features from `features_raw`
- Characteristics from `characteristics` dict
- Tags (merged with existing)
- Raw detail data storage

**Feature Parsing (`_parse_features()`):**
Extracts structured data from feature strings:
- Bedrooms: "3 quartos" → `bedrooms = 3`
- Bathrooms: "2 casas de banho" → `bathrooms = 2`
- Area: "150 m²" → `area_gross = 150.0`
- Useful area: "120 m² área útil" → `area_useful = 120.0`
- Floor: "4º andar" → `floor = "4º andar"`
- Typology: "T3" → `typology = "T3"`

**Characteristics Parsing (`_parse_characteristics()`):**
Extracts structured data from key-value pairs:
- Year built: "Ano de construção: 2010" → `year_built = 2010`
- Condition: "Estado: Usado" → `condition = "Usado"`
- Elevator: "Elevador: Sim" → `has_elevator = True`
- Garage: "Garagem: Sim" → `has_garage = True`
- Pool: "Piscina: Sim" → `has_pool = True`
- Garden: "Jardim: Sim" → `has_garden = True`
- Terrace: "Terraço: Sim" → `has_terrace = True`
- Balcony: "Varanda: Sim" → `has_balcony = True`
- Air conditioning: "Ar condicionado: Sim" → `has_air_conditioning = True`
- Central heating: "Aquecimento central: Sim" → `has_central_heating = True`
- Energy class: "Certificado energético: B" → `energy_class = "B"`
- Price per sqm: "Preço por m²: 3.500 €" → `price_per_sqm = 3500.0`

**Energy Class Normalization (`_normalize_energy_class()`):**
- Extracts letter and modifier from strings like "A+", "B-", "C"
- Returns normalized format (e.g., "A+", "B", "C")

**Location Parsing (`_parse_location()`):**
- Splits comma-separated location string
- Assigns parts to street, neighborhood, parish fields

#### 6.3. CLI Wiring (`__main__.py`)

Updated the `scrape-details` command:

- Loads configuration with CLI overrides
- Supports `--limit/-l` to limit listings processed
- Supports `--dry-run` to preview configuration
- Supports `--track-cost` for cost tracking
- Supports `--verbose/-v` for debug logging
- Initializes database with `init_db()`
- Creates session factory and page client
- Instantiates `DetailsScraper` and runs it
- Logs comprehensive summary of results
- Handles errors with proper exit codes

#### 6.4. Module Exports (`scraping/__init__.py`)

Updated exports to include:
- `DetailsScraper` class

### Verification

All checks pass:
- `uv run ruff format src tests` - 1 file reformatted
- `uv run ruff check src tests` - All checks passed
- `uv run mypy src` - Success: no issues found in 19 source files

### CLI Usage

```bash
# Scrape details for all listings needing enrichment
idealista-scraper scrape-details

# Limit to first 100 listings
idealista-scraper scrape-details --limit 100

# With cost tracking
idealista-scraper scrape-details --limit 50 --track-cost

# Dry run (preview configuration)
idealista-scraper scrape-details --dry-run

# Verbose logging
idealista-scraper scrape-details --limit 10 -v
```

### Notes for Next Engineer

- Phase 7 (Export Layer) is ready to begin
- The `DetailsScraper` shares the same `PageClient` interface as other scrapers
- Listings are selected based on missing detail fields (description, energy_class)
- Each listing is committed individually for durability
- The `ScrapeRun` table records each details scrape operation
- Feature and characteristic parsing handles Portuguese formats
- Energy class is normalized to standard format (A, A+, B, B-, C, etc.)
- Tags are merged with existing tags, not replaced

### Testing Results

Successfully tested against live Idealista pages:

| Metric | Result |
|--------|--------|
| Listings processed | 13 |
| Success rate | 100% (no blocks) |
| Avg page size | ~400 KB |
| Avg cost per page | ~$0.004 |

**Data Extraction Verified:**
- ✅ Descriptions (1000-3000+ chars)
- ✅ Energy class (A, B, E, etc.)
- ✅ Bathrooms (4, 5, 8, etc.)
- ✅ Bedrooms (5, 6, 7, etc.)
- ✅ Area (gross and useful)
- ✅ Floor ("1 andar", "3 andares")
- ✅ Condition ("Segunda mão/bom estado")
- ✅ Pool, Garden, Garage, AC flags
- ✅ Agency references
- ✅ Location (street, neighborhood, parish)

---

## Phase 7 – Export Layer

**Status:** ✅ Completed  
**Date:** 2025-11-28

### Summary

Implemented the export layer with functions to export listing data from the database to CSV and Parquet formats with optional filtering.

### Completed Tasks

#### 7.1. ExportFilters Data Class (`export/exporters.py`)

Implemented the `ExportFilters` dataclass for filtering exports:

- **`districts`**: List of district slugs to filter by
- **`concelhos`**: List of concelho slugs to filter by
- **`operation`**: Operation type filter ("comprar" or "arrendar")
- **`since`**: Export listings seen since this datetime
- **`active_only`**: If True, only export active listings (default: True)

#### 7.2. Export Columns Definition

Defined a comprehensive list of export columns (`EXPORT_COLUMNS`) in consistent order:

- **Identifiers**: id, idealista_id, url
- **Location**: district_name, district_slug, concelho_name, concelho_slug, street, neighborhood, parish
- **Listing info**: operation, property_type, title, description
- **Pricing**: price, price_per_sqm
- **Property characteristics**: typology, bedrooms, bathrooms, area_gross, area_useful, floor
- **Features**: has_elevator, has_garage, has_pool, has_garden, has_terrace, has_balcony, has_air_conditioning, has_central_heating, is_luxury, has_sea_view
- **Property details**: energy_class, condition, year_built
- **Agency**: agency_name, agency_url, reference
- **Metadata**: tags, image_url, first_seen, last_seen, is_active

#### 7.3. Query Builder (`_build_query`)

Implemented a flexible query builder that:

- Uses SQLAlchemy `select()` with eager loading via `joinedload()`
- Applies filters for active_only, operation, since date
- Supports filtering by concelho slugs and/or district slugs
- Orders results by `last_seen` descending
- Returns unique results using `.unique().all()`

#### 7.4. DataFrame Conversion (`_listings_to_dataframe`)

Implemented conversion from Listing objects to pandas DataFrame:

- Extracts all listing fields including nested relationships
- Includes district and concelho names/slugs from joined tables
- Reorders columns to match `EXPORT_COLUMNS` specification

#### 7.5. CSV Export (`export_listings_to_csv`)

Implemented CSV export function:

- Accepts session factory, output path, and filters
- Creates parent directories if needed
- Exports using `pandas.to_csv()` with no index
- Returns count of exported listings
- Creates empty file with headers if no results

#### 7.6. Parquet Export (`export_listings_to_parquet`)

Implemented Parquet export function:

- Same signature and behavior as CSV export
- Uses `pandas.to_parquet()` with PyArrow engine
- Returns count of exported listings
- Creates empty file with headers if no results

#### 7.7. CLI Wiring (`__main__.py`)

Updated the `export` command with full functionality:

**Arguments:**
- `--format, -f`: Output format (csv or parquet, default: csv)
- `--output`: Output file path (default: listings.csv)
- `--district, -d`: District slugs to filter (repeatable)
- `--concelho`: Concelho slugs to filter (repeatable)
- `--operation, -o`: Operation type filter
- `--since`: Export listings seen since date (YYYY-MM-DD format)
- `--active-only/--include-inactive`: Toggle active-only filter
- `--verbose, -v`: Enable verbose logging

**Features:**
- Validates format option
- Parses date string to datetime
- Auto-adjusts output file extension based on format
- Builds ExportFilters from CLI options
- Logs export completion with count

#### 7.8. Module Exports (`export/__init__.py`)

Updated exports to include:
- `EXPORT_COLUMNS`
- `ExportFilters`
- `export_listings_to_csv`
- `export_listings_to_parquet`

### Verification

All checks pass:
- `uv run ruff format src tests` - 20 files left unchanged
- `uv run ruff check src tests` - All checks passed
- `uv run mypy src` - Success: no issues found in 19 source files

### CLI Usage

```bash
# Export all active listings to CSV
idealista-scraper export

# Export to specific file
idealista-scraper export -o data/listings.csv

# Export to Parquet format
idealista-scraper export -f parquet -o data/listings.parquet

# Filter by district
idealista-scraper export -d lisboa-distrito

# Filter by concelho
idealista-scraper export --concelho cascais --concelho sintra

# Filter by operation
idealista-scraper export -o comprar

# Filter by date
idealista-scraper export --since 2025-01-01

# Include inactive listings
idealista-scraper export --include-inactive

# Combine filters
idealista-scraper export -d lisboa-distrito -o arrendar --since 2025-11-01 -f parquet

# Verbose output
idealista-scraper export -v
```

### Notes for Next Engineer

- Phase 8 (Type Checking, Tests, and Hardening) is ready to begin
- The export functions use a session factory pattern for proper session management
- Eager loading with `joinedload()` prevents N+1 queries for related data
- Export columns are defined in a consistent order for reproducibility
- Empty exports create files with headers for consistency
- The CLI auto-corrects file extensions based on format selection

---

## Phase 8 – Type Checking, Tests, and Hardening

**Status:** ⏳ Not Started

---

## Additional Features – Cost Tracking & Billing Utilities

**Status:** ✅ Completed  
**Date:** 2025-11-28

### Summary

Implemented comprehensive cost tracking and billing utilities for monitoring Bright Data API usage and costs in real-time.

### Completed Tasks

#### Balance Checking

Added CLI command to check Bright Data account balance:

```bash
idealista-scraper balance
```

Output:
```
💰 Bright Data Account Balance
   Balance:       $2.00
   Pending costs: $0.38
   Available:     $1.62
```

#### Cost Tracking Option

Added `--track-cost` option to `prescrape` and `scrape` commands:

```bash
idealista-scraper scrape --concelho cascais --max-pages 2 --track-cost
```

This provides two cost estimation methods:

1. **Bandwidth-based estimate** (instant, no delay):
   - Tracks bytes received per request
   - Calculates cost using Scraping Browser pricing ($9.50/GB)
   - Available immediately after scraping completes

2. **API-reported cost** (polling-based):
   - Polls Bright Data balance API until pending_costs changes
   - More accurate but requires ~20-30 second delay
   - Shows actual billed amount

#### New Module: `utils/billing.py`

Implemented the following components:

**Data Classes:**
- `RequestStats`: Per-request statistics (URL, bytes, cost, duration)
- `BandwidthTracker`: Aggregates bandwidth usage across requests
- `AccountBalance`: Bright Data account balance info
- `CostReport`: Combined API and bandwidth cost report

**Functions:**
- `get_balance()`: Fetch current balance from Bright Data API
- `get_zone_info(zone_name)`: Get zone-specific information
- `get_bandwidth_tracker()`: Get global bandwidth tracker instance
- `reset_bandwidth_tracker()`: Reset tracker and get results

**Context Manager:**
- `CostTracker`: Wraps operations to track costs automatically

#### Integration with BrightDataClient

Updated `scraping/client.py` to record bandwidth for each request:
- Measures HTML content size in bytes
- Records request duration
- Calculates estimated cost per request
- Logs per-request cost information

### Sample Output

```
Bandwidth Usage Summary:
   Total bytes:     1,233,401 (0.0011 GB)
   Total requests:  2
   Avg per request: 616,700 bytes
   Price per GB:    $9.50
   Est. total cost: $0.0109
   Est. cost/req:   $0.0055

Cost Report:
  Balance: $2.00 -> $2.00 (change: $+0.00)
  Pending: $0.38 -> $0.39 (change: $+0.01)
  API reported cost: $0.0100
  Bandwidth est. cost: $0.0109 (2 requests, 1,233,401 bytes)
```

### Cost Analysis

Based on testing with Idealista pages:
- **Average page size**: ~600 KB (616,700 bytes)
- **Cost per page**: ~$0.005-0.006 at $9.50/GB
- **Cost per 1000 pages**: ~$5-6

Bandwidth estimate closely matches API-reported cost, validating the approach.

### API Requirements

Requires `BRIGHTDATA_API_KEY` environment variable for balance checking.
Get your API key from: https://brightdata.com/cp/setting/users

### Technical Notes

- Bright Data's billing API has a ~20-30 second delay before costs appear
- Balance polling uses 5-second intervals with 60-second timeout
- Bandwidth tracking is immediate and doesn't require API key
- Cost estimates are based on HTML content size only (excludes TLS overhead)

---

## Phase 8 – Type Checking, Tests, and Hardening

**Status:** ✅ Completed  
**Date:** 2025-11-28

### Summary

Implemented comprehensive type checking, unit tests, CLI smoke tests, and validated the logging and error handling across the codebase.

### Completed Tasks

#### 8.1. Type Checking Configuration

The mypy configuration in `pyproject.toml` was already properly set up with:
- Strict mode enabled
- Pydantic plugin configured
- All 19 source files pass type checking without errors

**Verification:**
```bash
$ uv run mypy src
Success: no issues found in 19 source files
```

#### 8.2. Test Fixtures

Created minimal HTML fixtures in `tests/fixtures/` for testing parsing functions:

- **`search_results.html`**: Search results page with 3 listings + 1 ad (skipped)
  - Includes listings with full data, partial data, and price "Sob consulta"
  - Pagination metadata for testing
  
- **`listing_detail.html`**: Individual listing detail page
  - Title, price, location
  - Features, tags, description
  - Reference, characteristics, equipment
  - Energy class (B), photo count (46)

- **`homepage.html`**: Idealista homepage with district navigation
  - 3 districts: Porto, Braga, Lisboa
  - Multiple concelhos per district

- **`district_concelhos.html`**: District concelhos page
  - 7 concelhos for Lisboa district
  - Tests skipping special pages

#### 8.3. Unit Tests for Selectors (`tests/test_selectors.py`)

**TestParseListingsPage** (7 tests):
- Returns correct structure (listings + metadata)
- Parses correct number of listings (skips ads)
- Extracts full listing data (ID, URL, title, price, location, details, agency, tags)
- Handles minimal listings with missing fields
- Parses pagination metadata (total count, page, has_next, last_page)
- Tracks lowest price on page for segmentation

**TestParseListingDetail** (10 tests):
- Parses title, price, location
- Extracts features (bedrooms, bathrooms, area, floor)
- Parses tags (Luxo, Piscina, Jardim)
- Extracts full description
- Parses reference number
- Extracts characteristics (year built, condition)
- Parses equipment list
- Extracts energy class
- Parses photo count

**TestParseHomepageDistricts** (4 tests):
- Returns list of districts
- Parses correct number of districts
- Extracts district info with concelhos
- Verifies concelho details per district

**TestParseConcelhosPage** (5 tests):
- Returns list of concelhos
- Parses correct count
- Extracts concelho info (name, slug, href)
- Skips special pages (concelhos-freguesias)
- Deduplicates by slug

#### 8.4. Unit Tests for URL Builders (`tests/test_url_builders.py`)

**TestBuildSearchUrl** (9 tests):
- Basic URL construction
- Pagination parameter
- Page 1 excludes pagination
- Max price filter
- Min price filter
- Combined price range
- Order/sorting parameter
- Rent operation (arrendar)
- Full URL with all parameters

**TestBuildPaginatedUrl** (5 tests):
- Page 1 returns unchanged URL
- Adds pagination to clean URL
- Adds pagination with existing params
- Replaces existing pagination
- Preserves other params when replacing pagination

#### 8.5. Unit Tests for Database (`tests/test_database.py`)

Uses in-memory SQLite database for testing.

**TestDatabaseSetup** (1 test):
- Verifies all tables can be created and queried

**TestDistrictModel** (2 tests):
- Create district with all fields
- String representation

**TestConcelhoModel** (2 tests):
- Create concelho with parent district
- District-concelho relationship (one-to-many)

**TestListingModel** (2 tests):
- Create listing with basic fields
- Create listing with all 40+ fields populated

**TestListingHistoryModel** (2 tests):
- Create history record with price change
- Listing-history relationship

**TestScrapeRunModel** (3 tests):
- Create scrape run
- Update status on completion
- Record failed run with error message

#### 8.6. CLI Smoke Tests (`tests/test_cli.py`)

Uses `typer.testing.CliRunner` for testing CLI commands.

**TestCliBasic** (2 tests):
- `--help` shows command list
- No args shows help/usage

**TestPrescrapeCommand** (2 tests):
- `prescrape --help` shows options
- `prescrape --dry-run` previews without changes

**TestScrapeCommand** (3 tests):
- `scrape --help` shows options
- `scrape` without locations shows error
- `scrape --dry-run` with location works

**TestScrapeDetailsCommand** (3 tests):
- `scrape-details --help` shows options
- `scrape-details --dry-run` works
- `scrape-details --dry-run --limit` shows limit

**TestExportCommand** (4 tests):
- `export --help` shows options
- Invalid format shows error
- Invalid date format shows error
- Export to CSV works (empty DB)

**TestBalanceCommand** (1 test):
- `balance --help` shows options

#### 8.7. Logging and Observability Review

Verified that all scrapers implement proper logging:

**PreScraper:**
- Logs start of pre-scraper run
- Logs homepage fetch and district count
- Logs each district processing with concelho count
- Logs final summary on completion
- Logs exceptions with stack traces on failure

**ListingsScraper:**
- Logs start of listings scraper run
- Logs each location/operation/property_type combination
- Logs each segment with price range
- Logs each page with listings count, total, lowest price
- Logs segment completion and when segmentation is needed
- Logs final summary with all statistics
- Logs exceptions with stack traces on failure

**DetailsScraper:**
- Logs start with max_listings parameter
- Logs count of listings needing details
- Logs each listing processing with progress (1/100, 2/100, etc.)
- Logs enrichment details (description, energy class, reference)
- Logs final summary with processed/enriched/failed counts
- Logs exceptions with stack traces on failure

#### 8.8. Error Handling Review

Verified that all scrapers implement proper error handling:

**ScrapeRun Tracking:**
- All scrapers create a ScrapeRun record on start
- Status set to "running" initially
- On success: status="success", ended_at set, stats populated
- On failure: status="failed", ended_at set, error_message saved
- Session always committed in finally block

**Exception Handling:**
- BrightDataClient retries with exponential backoff
- Transient errors logged as warnings, retried
- Fatal errors logged as exceptions with stack traces
- Proper cleanup in finally blocks
- CLI commands exit with code 1 on error

### Verification

**All checks pass:**
```bash
$ uv run ruff format src tests
2 files reformatted, 22 files left unchanged

$ uv run ruff check src tests
All checks passed!

$ uv run mypy src
Success: no issues found in 19 source files

$ uv run pytest tests/ -v
============================== 67 passed in 2.17s ==============================
```

### Test Summary

| Test File | Tests | Status |
|-----------|-------|--------|
| test_cli.py | 15 | ✅ All pass |
| test_database.py | 12 | ✅ All pass |
| test_selectors.py | 26 | ✅ All pass |
| test_url_builders.py | 14 | ✅ All pass |
| **Total** | **67** | **✅ All pass** |

### Notes for Next Engineer

- All Phase 8 objectives have been completed
- The codebase is fully type-checked with mypy in strict mode
- 67 unit tests provide good coverage of core functionality
- CLI commands can be tested with `typer.testing.CliRunner`
- HTML fixtures in `tests/fixtures/` can be used for new selector tests
- Add more tests as needed for edge cases

---

## Implementation Complete 🎉

All 9 phases of the implementation plan have been completed:

| Phase | Description | Status |
|-------|-------------|--------|
| 0 | Repository & Tooling Baseline | ✅ Completed |
| 1 | Configuration Layer | ✅ Completed |
| 2 | Database Models and Session Management | ✅ Completed |
| 3 | HTTP / Bright Data Client and Selector Helpers | ✅ Completed |
| 4 | Pre-Scraper (Part 1) | ✅ Completed |
| 5 | Listings Scraper (Part 2) | ✅ Completed |
| 6 | Detail Scraper (Part 3) | ✅ Completed |
| 7 | Export Layer | ✅ Completed |
| 8 | Type Checking, Tests, and Hardening | ✅ Completed |

The Idealista web scraper is now fully functional with:
- Bright Data Scraping Browser integration (bypasses anti-bot protection)
- SQLite database with SQLAlchemy ORM
- Price segmentation for large result sets
- CSV and Parquet export
- Cost tracking and billing utilities
- Comprehensive test suite
- Full type safety with mypy

---

# Async Implementation Progress Log

This section tracks the progress of implementing async/parallel scraping capabilities according to `ASYNC_IMPLEMENTATION_PLAN.md`.

---

## Async Phase 1 – Async Client Layer

**Status:** ✅ Completed  
**Date:** 2025-11-29

### Summary

Created async versions of the time utilities and page client without modifying existing sync code.

### Completed Tasks

#### 1.1. Async Time Utilities (`utils/async_time_utils.py`)

Created new module with async versions of time utilities:

- **`async_sleep_with_jitter(base_delay, jitter_factor)`**: Async sleep with random jitter for anti-detection
- **`async_retry_with_backoff(coro_func, ...)`**: Retry an async function with exponential backoff
  - Uses Python 3.12 generic type syntax `async def async_retry_with_backoff[T](...)`
  - Same signature as sync version for consistency
  - Logs warnings on retries and errors on final failure

#### 1.2. Async Client (`scraping/async_client.py`)

Created new module with async client implementation:

- **`AsyncPageClient`** (Protocol): Interface for async page fetching with `get_html()` and `close()` methods
- **`AsyncBrightDataClientError`**: Exception for Bright Data errors with `is_connection_error` flag
- **`AsyncBrightDataClient`**: Async Bright Data Scraping Browser client
  - Uses `playwright.async_api.async_playwright` for async browser control
  - Each `get_html()` call creates a new browser connection for IP rotation
  - Integrates with bandwidth tracker for cost estimation
  - Uses async retry and sleep utilities
  - Same timeout and configuration as sync client
- **`create_async_client(config)`**: Factory function for creating async clients
  - Requires `use_brightdata=True` (async only supports Bright Data)

#### 1.3. Module Exports

Updated module exports to include async components:

- **`utils/__init__.py`**: Added exports for `async_sleep_with_jitter`, `async_retry_with_backoff`
- **`scraping/__init__.py`**: Added exports for `AsyncBrightDataClient`, `AsyncBrightDataClientError`, `AsyncPageClient`, `create_async_client`

### Verification

All checks pass:
```bash
$ uv run ruff format src tests
1 file reformatted, 25 files left unchanged

$ uv run ruff check src tests
All checks passed!

$ uv run mypy src
Success: no issues found in 21 source files

$ uv run pytest tests/ -v
============================== 67 passed in 3.05s ==============================
```

### New Files Created

| File | Description |
|------|-------------|
| `src/idealista_scraper/utils/async_time_utils.py` | Async sleep and retry utilities |
| `src/idealista_scraper/scraping/async_client.py` | Async Bright Data client |

### Files Modified

| File | Change |
|------|--------|
| `src/idealista_scraper/utils/__init__.py` | Added async utility exports |
| `src/idealista_scraper/scraping/__init__.py` | Added async client exports |

### Notes for Next Engineer

- Async Phase 2 (Async Scrapers) is ready to begin
- The `AsyncBrightDataClient` shares the same interface pattern as `BrightDataClient`
- Concurrency will be controlled externally via `asyncio.Semaphore` in the scrapers
- The sync code remains unchanged and fully functional
- All 67 existing tests pass

---

## Async Phase 2 – Async Utilities

**Status:** ✅ Completed  
**Date:** 2025-11-29

### Summary

Phase 2 focuses on async time utilities and their testing. The core utilities were already created in Phase 1, so this phase completed the testing coverage and added `pytest-asyncio` as a dev dependency.

### Completed Tasks

#### 2.1. Async Time Utilities (already created in Phase 1)

The following utilities were implemented in `utils/async_time_utils.py`:

- **`async_sleep_with_jitter(base_delay, jitter_factor)`**: Async sleep with random jitter
  - Adds randomness to delays for anti-detection
  - Never returns negative delays
  - Default jitter factor is 0.1 (10%)

- **`async_retry_with_backoff(coro_func, ...)`**: Retry async function with exponential backoff
  - Configurable max_retries, base_delay, max_delay
  - Supports multiple retryable exception types
  - Uses Python 3.12 generic type syntax

#### 2.2. Unit Tests (`tests/test_async_time_utils.py`)

Created comprehensive test suite with 15 tests:

**TestAsyncSleepWithJitter (5 tests):**
- `test_sleep_with_no_jitter`: Zero jitter returns exact delay
- `test_sleep_with_jitter_in_range`: Delays within ±10% range
- `test_sleep_with_large_jitter`: Delays within ±50% range
- `test_sleep_never_negative`: Delays always >= 0
- `test_sleep_default_jitter_factor`: Default is 10%

**TestAsyncRetryWithBackoff (10 tests):**
- `test_success_on_first_attempt`: No retry if successful
- `test_retry_on_failure_then_success`: Retries until success
- `test_raises_after_max_retries`: Raises last exception after max retries
- `test_non_retryable_exception_not_retried`: Only retries specified exceptions
- `test_exponential_backoff_delay`: Delays increase exponentially (1, 2, 4...)
- `test_max_delay_respected`: Delay capped at max_delay
- `test_default_max_retries`: Default is 3 retries
- `test_returns_correct_type`: Return type preserved
- `test_zero_max_retries`: No retries when max_retries=0
- `test_multiple_exception_types`: Handles multiple exception types

#### 2.3. Dependencies and Configuration

Updated `pyproject.toml`:

**Dev dependencies:**
```toml
"pytest-asyncio>=0.23",
```

**Pytest configuration:**
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

#### 2.4. Module Exports (completed in Phase 1)

Already exported from `utils/__init__.py`:
- `async_sleep_with_jitter`
- `async_retry_with_backoff`

### Verification

All checks pass:
```bash
$ uv run ruff format src tests
27 files left unchanged

$ uv run ruff check src tests
All checks passed!

$ uv run mypy src
Success: no issues found in 21 source files

$ uv run pytest tests/ -v
======================== 82 passed in 3.03s ========================
```

### Test Summary

| Test File | Tests | Status |
|-----------|-------|--------|
| test_async_time_utils.py | 15 | ✅ All pass |
| test_cli.py | 15 | ✅ All pass |
| test_database.py | 12 | ✅ All pass |
| test_selectors.py | 26 | ✅ All pass |
| test_url_builders.py | 14 | ✅ All pass |
| **Total** | **82** | **✅ All pass** |

### New Files Created

| File | Description |
|------|-------------|
| `tests/test_async_time_utils.py` | 15 tests for async time utilities |

### Files Modified

| File | Change |
|------|--------|
| `pyproject.toml` | Added `pytest-asyncio>=0.23` and `asyncio_mode = "auto"` |

### Notes for Next Engineer

- Async Phase 3 (Async Scrapers) is ready to begin
- All async utilities are tested and working
- `pytest-asyncio` with `asyncio_mode = "auto"` means `@pytest.mark.asyncio` is auto-applied
- The async utilities use the same signatures as sync versions for consistency
- 82 tests now pass (15 new async tests + 67 existing tests)

---

## Async Phase 3 – Async Scrapers

**Status:** ✅ Completed  
**Date:** 2025-11-29

### Summary

Created async versions of all three scrapers (ListingsScraper, DetailsScraper, PreScraper) that process URLs concurrently using asyncio.gather() with Semaphore for concurrency control.

### Completed Tasks

#### 3.1. Architecture Decision: Batch Processing

Implemented the batch fetch pattern as specified in the plan:

1. Collect URLs to fetch
2. Fetch all URLs concurrently with semaphore control
3. Process results sequentially (for simpler DB handling)

This approach maximizes network efficiency while keeping database operations simple and safe.

#### 3.2. AsyncListingsScraper (`scraping/async_listings_scraper.py`)

Created async version of the listings scraper with:

**FetchResult Dataclass:**
- Holds URL, page number, HTML content, and optional error
- Used for batch fetch results

**Constructor:**
- Accepts `AsyncPageClient`, session factory, `RunConfig`, and concurrency
- Initializes semaphore for concurrency control
- Maintains concelho cache for performance

**Main `run()` Method:**
- Creates `ScrapeRun` record with `run_type="scrape-async"`
- Stores concurrency in config for tracking
- Iterates over locations, operations, and property types
- Returns same statistics as sync version

**`_fetch_page()` Method:**
- Fetches single page with semaphore control
- Returns FetchResult with HTML or error
- Individual errors don't crash the batch

**`_fetch_pages_batch()` Method:**
- Fetches multiple pages concurrently using `asyncio.gather()`
- Returns list of FetchResult objects

**`_scrape_segment_async()` Method:**
- Fetches first page to determine total pages
- Batch fetches remaining pages concurrently
- Processes results sequentially for DB writes
- Commits after each batch
- Implements price segmentation logic

**Helper Methods:**
- Reuses same logic as sync version for DB operations
- `_upsert_listing_card()`, `_create_listing()`, `_update_listing()`
- `_parse_details()`, `_normalize_url()`

#### 3.3. AsyncDetailsScraper (`scraping/async_details_scraper.py`)

Created async version of the details scraper with:

**DetailFetchResult Dataclass:**
- Holds listing ID, Idealista ID, parsed detail, and optional error
- Used for batch detail fetch results

**Constructor:**
- Accepts `AsyncPageClient`, session factory, max_listings, and concurrency
- Initializes semaphore for concurrency control

**Main `run()` Method:**
- Creates `ScrapeRun` record with `run_type="scrape-details-async"`
- Gets listings needing details
- Processes in batches for concurrent fetching
- Returns same statistics as sync version

**`_fetch_detail()` Method:**
- Fetches single detail page with semaphore control
- Parses HTML using `parse_listing_detail()`
- Returns DetailFetchResult with detail or error

**`_fetch_details_batch()` Method:**
- Fetches multiple detail pages concurrently using `asyncio.gather()`
- Returns list of DetailFetchResult objects

**Helper Methods:**
- Reuses same logic as sync version for parsing and updates
- `_update_listing_from_detail()`
- `_normalize_energy_class()`, `_parse_location()`
- `_parse_equipment()`, `_parse_features()`, `_parse_characteristics()`

#### 3.4. AsyncPreScraper (`scraping/async_pre_scraper.py`)

Created async version of the pre-scraper with:

**DistrictConcelhosResult Dataclass:**
- Holds district slug, list of concelhos, and optional error
- Used for batch concelho fetch results

**Constructor:**
- Accepts `AsyncPageClient`, session factory, and concurrency
- Initializes semaphore for concurrency control

**Main `run()` Method:**
- Creates `ScrapeRun` record with `run_type="prescrape-async"`
- Fetches homepage for district info
- Identifies districts needing concelho fetching
- Fetches all concelhos concurrently
- Returns same statistics as sync version

**`_fetch_concelhos_for_district()` Method:**
- Fetches single district's concelhos page with semaphore control
- Parses HTML using `parse_concelhos_page()`
- Returns DistrictConcelhosResult with concelhos or error

**`_fetch_all_concelhos()` Method:**
- Fetches concelhos for multiple districts concurrently
- Returns list of DistrictConcelhosResult objects

**Helper Methods:**
- Reuses same logic as sync version for DB operations
- `_process_district()`, `_upsert_district()`, `_upsert_concelho()`

#### 3.5. Module Exports (`scraping/__init__.py`)

Updated exports to include all async scrapers:

```python
from idealista_scraper.scraping.async_details_scraper import AsyncDetailsScraper
from idealista_scraper.scraping.async_listings_scraper import AsyncListingsScraper
from idealista_scraper.scraping.async_pre_scraper import AsyncPreScraper

__all__ = [
    # ... existing exports ...
    # Async Scrapers
    "AsyncDetailsScraper",
    "AsyncListingsScraper",
    "AsyncPreScraper",
]
```

### Verification

All checks pass:

```bash
$ uv run ruff format src tests
2 files reformatted, 28 files left unchanged

$ uv run ruff check src tests
All checks passed!

$ uv run mypy src
Success: no issues found in 24 source files

$ uv run pytest tests/ -v
======================== 82 passed in 3.03s ========================
```

### New Files Created

| File | Description |
|------|-------------|
| `src/idealista_scraper/scraping/async_listings_scraper.py` | Async listings scraper with concurrent page fetching |
| `src/idealista_scraper/scraping/async_details_scraper.py` | Async details scraper with concurrent detail fetching |
| `src/idealista_scraper/scraping/async_pre_scraper.py` | Async pre-scraper with concurrent concelho fetching |

### Files Modified

| File | Change |
|------|--------|
| `src/idealista_scraper/scraping/__init__.py` | Added async scraper exports |

### Key Design Decisions

1. **Batch Processing Pattern**: Fetch multiple pages concurrently, process results sequentially. This maximizes network efficiency while keeping DB operations simple.

2. **Semaphore-Based Concurrency**: Each scraper creates a semaphore with the specified concurrency level. All fetch operations acquire the semaphore before making requests.

3. **Error Isolation**: Individual fetch failures don't crash the batch. Errors are logged and skipped, allowing other pages to be processed.

4. **Same DB Logic**: All database operations (upsert, update, history tracking) reuse the same logic as sync scrapers. No async DB required.

5. **Configurable Batch Size**: Batch size is `concurrency * 2` to ensure there's always work queued while requests are in flight.

6. **Run Type Tracking**: Async runs are tracked with distinct `run_type` values (`scrape-async`, `scrape-details-async`, `prescrape-async`) for monitoring.

### Performance Expectations

| Sync (1 request) | Async (5 concurrent) | Async (10 concurrent) |
|------------------|---------------------|----------------------|
| ~5s per page | ~5-6s per 5 pages | ~5-6s per 10 pages |
| 60 pages: 5 min | 60 pages: ~1 min | 60 pages: ~30s |

### Notes for Next Engineer

- Async Phase 4 (CLI Integration) is ready to begin
- The async scrapers share the same interface as sync scrapers
- Concurrency is controlled via constructor parameter (default: 5)
- All 82 existing tests pass (no async scraper tests yet - will be added in Phase 6)
- The sync code remains unchanged and fully functional
- ScrapeRun records include concurrency in config for monitoring

---

## Async Phase 4 – CLI Integration

**Status:** ✅ Completed  
**Date:** 2025-11-29

### Summary

Added CLI flags for async mode and concurrency control to all scraping commands (prescrape, scrape, scrape-details).

### Completed Tasks

#### 4.1. New CLI Options

Added two new option type aliases to `__main__.py`:

**AsyncOption:**
```python
AsyncOption = Annotated[
    bool,
    typer.Option(
        "--async/--sync",
        help="Use async concurrent scraping (faster but higher cost).",
    ),
]
```

**ConcurrencyOption:**
```python
ConcurrencyOption = Annotated[
    int,
    typer.Option(
        "--concurrency",
        help="Number of concurrent browser sessions (only with --async).",
        min=1,
        max=20,
    ),
]
```

#### 4.2. Updated Commands

**prescrape command:**
- Added `use_async: AsyncOption = False` parameter
- Added `concurrency: ConcurrencyOption = 5` parameter
- Uses `AsyncPreScraper` when `--async` is specified
- Uses `asyncio.run()` to execute async scraper

**scrape command:**
- Added `use_async: AsyncOption = False` parameter
- Added `concurrency: ConcurrencyOption = 5` parameter
- Uses `AsyncListingsScraper` when `--async` is specified
- Uses `asyncio.run()` to execute async scraper

**scrape-details command:**
- Added `use_async: AsyncOption = False` parameter
- Added `concurrency: ConcurrencyOption = 5` parameter
- Uses `AsyncDetailsScraper` when `--async` is specified
- Uses `asyncio.run()` to execute async scraper

#### 4.3. Dry Run Output

Updated dry-run output for all commands to show:
- Mode: async or sync
- Concurrency: number of browser sessions (only when async)

Example:
```
[DRY RUN] Mode: async
[DRY RUN] Concurrency: 5 browser sessions
```

#### 4.4. Concurrency Warning

All commands now warn when `--concurrency` is specified without `--async`:
```
WARNING: --concurrency has no effect without --async. Use --async to enable concurrent scraping.
```

#### 4.5. Import Updates

Updated imports in `__main__.py` to include:
- `asyncio` module
- `AsyncDetailsScraper`, `AsyncListingsScraper`, `AsyncPreScraper`
- `create_async_client` factory function

### Verification

All checks pass:

```bash
$ uv run ruff format src tests
30 files left unchanged

$ uv run ruff check src tests
All checks passed!

$ uv run mypy src
Success: no issues found in 24 source files

$ uv run pytest tests/ -v
======================== 82 passed in 3.00s ========================
```

### CLI Usage Examples

```bash
# Sync mode (default)
idealista-scraper prescrape
idealista-scraper scrape --concelho cascais
idealista-scraper scrape-details --limit 10

# Async mode with default concurrency (5)
idealista-scraper prescrape --async
idealista-scraper scrape --concelho cascais --async
idealista-scraper scrape-details --limit 10 --async

# Async mode with custom concurrency
idealista-scraper prescrape --async --concurrency 10
idealista-scraper scrape --concelho cascais --async --concurrency 3
idealista-scraper scrape-details --limit 50 --async --concurrency 8

# Dry run with async (preview)
idealista-scraper scrape --concelho cascais --async --dry-run

# With cost tracking
idealista-scraper scrape --concelho cascais --async --track-cost
```

### Files Modified

| File | Change |
|------|--------|
| `src/idealista_scraper/__main__.py` | Added async/concurrency options to all commands |

### Notes for Next Engineer

- Async Phase 5 (Configuration) is ready to begin if needed
- All async CLI options are optional with sensible defaults
- The `--async/--sync` flag uses typer's boolean flag syntax
- Concurrency is validated to be between 1 and 20
- Cost tracking (`--track-cost`) works with async mode
- All 82 existing tests pass

---

## Async Phase 5 – Configuration

**Status:** ✅ Completed  
**Date:** 2025-11-29

### Summary

Added async configuration to the Pydantic models and YAML configuration file, enabling configuration-driven async settings.

### Completed Tasks

#### 5.1. AsyncConfig Model (`config/settings.py`)

Created new Pydantic model for async configuration:

```python
class AsyncConfig(BaseModel):
    """Configuration for async scraping behavior.

    Attributes:
        enabled: Whether to use async mode by default.
        concurrency: Number of concurrent browser sessions.
        batch_size: Number of pages to fetch per batch.
        jitter_factor: Random delay variation factor (0.0-1.0).
    """

    enabled: bool = Field(default=False)
    concurrency: int = Field(default=5, ge=1, le=20)
    batch_size: int = Field(default=10, ge=1, le=50)
    jitter_factor: float = Field(default=0.2, ge=0.0, le=1.0)
```

**Validation:**
- `concurrency`: Must be between 1 and 20
- `batch_size`: Must be between 1 and 50
- `jitter_factor`: Must be between 0.0 and 1.0

#### 5.2. Updated ScrapingConfig Model

Added `async_config` field to `ScrapingConfig`:

```python
class ScrapingConfig(BaseModel):
    # ... existing fields ...
    async_config: AsyncConfig = Field(default_factory=AsyncConfig)
```

#### 5.3. Updated config.example.yaml

Added async configuration section:

```yaml
scraping:
  # ... existing settings ...
  
  # Async/concurrency settings
  async:
    # Whether to use async mode by default
    enabled: false
    # Number of concurrent browser sessions (1-20)
    concurrency: 5
    # Number of pages to fetch per batch (1-50)
    batch_size: 10
    # Random delay variation factor (0.0-1.0) for anti-detection
    jitter_factor: 0.2
```

#### 5.4. CLI Override Mapping

Updated `_flatten_cli_overrides()` to support async settings from CLI:

```python
key_mapping = {
    # ... existing mappings ...
    "use_async": ["scraping", "async_config", "enabled"],
    "concurrency": ["scraping", "async_config", "concurrency"],
    "batch_size": ["scraping", "async_config", "batch_size"],
    "jitter_factor": ["scraping", "async_config", "jitter_factor"],
}
```

#### 5.5. Module Exports

Updated `config/__init__.py` to export `AsyncConfig`:

```python
from idealista_scraper.config.settings import (
    AsyncConfig,
    # ... other exports ...
)

__all__ = [
    "AsyncConfig",
    # ... other exports ...
]
```

### Verification

All checks pass:

```bash
$ uv run ruff format src tests
30 files left unchanged

$ uv run ruff check src tests
All checks passed!

$ uv run mypy src
Success: no issues found in 24 source files

$ uv run pytest tests/ -v
======================== 82 passed in 2.96s ========================
```

### Files Modified

| File | Change |
|------|--------|
| `src/idealista_scraper/config/settings.py` | Added `AsyncConfig` model, updated `ScrapingConfig`, updated CLI mapping |
| `src/idealista_scraper/config/__init__.py` | Added `AsyncConfig` export |
| `config.example.yaml` | Added async configuration section |

### Configuration Precedence

The async configuration follows the same precedence as other settings:

1. **CLI overrides** (highest): `--async`, `--concurrency`
2. **Environment variables**: Not mapped (use YAML for complex settings)
3. **YAML config file**: `scraping.async.*` settings
4. **Default values** (lowest): `enabled=False`, `concurrency=5`, etc.

### Usage Examples

**Via YAML configuration:**
```yaml
scraping:
  async:
    enabled: true
    concurrency: 10
    batch_size: 20
```

**Via CLI:**
```bash
# Override config with CLI flags
idealista-scraper scrape --concelho cascais --async --concurrency 8
```

**Programmatic access:**
```python
from idealista_scraper.config import load_config

config = load_config(config_path="config.yaml")
if config.scraping.async_config.enabled:
    concurrency = config.scraping.async_config.concurrency
    # Use async scraper with specified concurrency
```

### Notes for Next Engineer

- Async Phase 6 (Testing) is ready to begin
- The `AsyncConfig` model can be accessed via `config.scraping.async_config`
- CLI flags (`--async`, `--concurrency`) override YAML settings
- Default values are conservative: async disabled, 5 concurrent sessions
- All 82 existing tests pass

---

## Async Phase 6 – Testing

**Status:** ✅ Completed  
**Date:** 2025-11-29

### Summary

Implemented comprehensive test coverage for async functionality including unit tests for the async client, async scrapers, and CLI async options.

### Completed Tasks

#### 6.1. Async Client Tests (`tests/test_async_client.py`)

Created 16 tests covering:

**TestAsyncBrightDataClientError (2 tests):**
- Error with message
- Error with connection flag

**TestAsyncBrightDataClient (6 tests):**
- Initialization with credentials
- Initialization with ScrapingConfig
- Browser WebSocket URL format
- `close()` is no-op
- Successful HTML fetch with mocked playwright
- Fetch without wait_selector
- Retry on error
- Raises after max retries
- Request count increments

**TestAsyncBrightDataClientDelays (2 tests):**
- No delay on first request
- Delay on subsequent requests

**TestCreateAsyncClient (2 tests):**
- Create with brightdata enabled
- Raises ValueError when brightdata disabled

**TestAsyncClientConcurrency (1 test):**
- Concurrent requests work correctly

#### 6.2. Async Scrapers Tests (`tests/test_async_scrapers.py`)

Created 32 tests covering:

**Data Classes (6 tests):**
- FetchResult success/failure
- DetailFetchResult success/failure
- DistrictConcelhosResult success/failure

**AsyncListingsScraper (8 tests):**
- Initialization with defaults and custom concurrency
- `_fetch_page()` success and failure
- `_fetch_page()` requires semaphore
- `_fetch_pages_batch()` concurrent fetching
- Concurrency limit respected
- `_process_page_results()` updates stats

**AsyncDetailsScraper (8 tests):**
- Initialization with defaults and custom settings
- `_fetch_detail()` success and failure
- `_update_listing_from_detail()` updates fields
- `_normalize_energy_class()` simple and with modifier

**AsyncPreScraper (7 tests):**
- Initialization with defaults and custom concurrency
- `_fetch_concelhos_for_district()` success and failure
- `_fetch_all_concelhos()` concurrent fetching
- `_upsert_district()` create and update
- `_upsert_concelho()` create

**ScrapeRun Creation (3 tests):**
- Listings scraper creates run with correct type
- Details scraper creates run with correct type
- Pre-scraper creates run with correct type

#### 6.3. Async CLI Tests (`tests/test_cli_async.py`)

Created 21 tests covering:

**TestAsyncPrescrapeCommand (5 tests):**
- Help shows async options
- `--async` dry run shows async mode
- `--sync` dry run shows sync mode
- `--concurrency` in dry run
- Warning when `--concurrency` without `--async`

**TestAsyncScrapeCommand (7 tests):**
- Help shows async options
- `--async` dry run
- `--sync` dry run
- `--concurrency` in dry run
- Warning when `--concurrency` without `--async`
- Concurrency validation min (rejects 0)
- Concurrency validation max (rejects 50)

**TestAsyncScrapeDetailsCommand (6 tests):**
- Help shows async options
- `--async` dry run
- `--sync` dry run
- `--concurrency` in dry run
- With `--limit` and `--async`
- Warning when `--concurrency` without `--async`

**TestAsyncConcurrencyDefaults (3 tests):**
- Default concurrency is 5
- Concurrency can be set to 1
- Concurrency can be set to 20 (max)

#### 6.4. Test Dependencies

Updated `pyproject.toml` in Phase 2:
- Added `pytest-asyncio>=0.23` to dev dependencies
- Configured `asyncio_mode = "auto"` in pytest settings

### Verification

All checks pass:

```bash
$ uv run ruff format src tests
1 file reformatted, 32 files left unchanged

$ uv run ruff check src tests
All checks passed!

$ uv run mypy src
Success: no issues found in 24 source files

$ uv run pytest tests/ -v
======================== 151 passed in 10.98s ========================
```

### Test Summary

| Test File | Tests | Status |
|-----------|-------|--------|
| test_async_client.py | 16 | ✅ All pass |
| test_async_scrapers.py | 32 | ✅ All pass |
| test_cli_async.py | 21 | ✅ All pass |
| test_async_time_utils.py | 15 | ✅ All pass |
| test_cli.py | 15 | ✅ All pass |
| test_database.py | 12 | ✅ All pass |
| test_selectors.py | 26 | ✅ All pass |
| test_url_builders.py | 14 | ✅ All pass |
| **Total** | **151** | **✅ All pass** |

### New Files Created

| File | Description |
|------|-------------|
| `tests/test_async_client.py` | 16 tests for async client functionality |
| `tests/test_async_scrapers.py` | 32 tests for async scrapers |
| `tests/test_cli_async.py` | 21 tests for CLI async options |

### Notes for Next Engineer

- Async Phase 7 (Documentation) is ready to begin
- All 151 tests pass (69 new async tests + 82 existing tests)
- Tests use `unittest.mock.AsyncMock` for mocking async functions
- In-memory SQLite databases are used for scraper tests
- Mocked playwright is used for client tests (no real network calls)
- `pytest-asyncio` with `asyncio_mode = "auto"` handles async test marking

---

## Async Implementation Complete 🎉

All 6 async phases have been completed:

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Async Client Layer | ✅ Completed |
| 2 | Async Utilities | ✅ Completed |
| 3 | Async Scrapers | ✅ Completed |
| 4 | CLI Integration | ✅ Completed |
| 5 | Configuration | ✅ Completed |
| 6 | Testing | ✅ Completed |

The async scraping implementation is now complete with:
- `AsyncBrightDataClient` for concurrent browser sessions
- `AsyncListingsScraper`, `AsyncDetailsScraper`, `AsyncPreScraper`
- `--async` and `--concurrency` CLI options
- `AsyncConfig` in configuration
- 69 new tests (151 total)

### Usage

```bash
# Sync mode (default)
idealista-scraper scrape --concelho cascais

# Async mode with default concurrency (5)
idealista-scraper scrape --concelho cascais --async

# Async mode with custom concurrency
idealista-scraper scrape --concelho cascais --async --concurrency 10
```

### Expected Performance

| Mode | Concurrency | Speed | Cost |
|------|-------------|-------|------|
| Sync | 1 | 1x | 1x |
| Async | 5 | ~5x | ~5x |
| Async | 10 | ~8x | ~8x |

---

## Bug Fix – Concelhos Parsing

**Status:** ✅ Completed  
**Date:** 2025-11-29

### Summary

Fixed the `parse_concelhos_page()` function which was failing to parse concelhos from real Idealista HTML pages. The function was looking for a `section.municipality-search` class that doesn't exist in production HTML.

### Problem

The original implementation expected HTML with:
```html
<section class="municipality-search">
    <a href="/comprar-casas/cascais/">Cascais</a>
</section>
```

But the actual Idealista website uses:
```html
<ul class="breadcrumb-dropdown-subitem-list">
    <li class="breadcrumb-dropdown-subitem-element-list">
        <a href="/comprar-casas/cascais/concelhos-freguesias">Cascais</a>
    </li>
</ul>
```

### Solution

Updated `parse_concelhos_page()` with multiple parsing strategies:

1. **Primary**: Look in `breadcrumb-dropdown-subitem-list` (real website structure)
2. **Fallback**: Look for `municipality-search` section (test fixtures)
3. **Last resort**: Search entire page for matching URL patterns

Also added `_extract_concelho_slug()` helper to correctly extract slugs from URLs like:
- `/comprar-casas/cascais/concelhos-freguesias` → `cascais`
- `/comprar-casas/lisboa/` → `lisboa`

### Files Modified

| File | Change |
|------|--------|
| `src/idealista_scraper/scraping/selectors.py` | Rewrote `parse_concelhos_page()`, added `_extract_concelho_slug()` |
| `tests/fixtures/district_concelhos.html` | Updated to match real HTML structure |
| `tests/test_selectors.py` | Updated tests to match new expected behavior |

### Verification

```bash
$ uv run pytest tests/test_selectors.py -v
======================== 26 passed in 0.75s ========================

$ uv run pytest tests/ -v
======================== 151 passed in 11.60s ========================
```

### Results

Real HTML parsing now correctly extracts **16 concelhos** from the Lisboa district page:
- Alenquer, Amadora, Arruda dos Vinhos, Azambuja, Cadaval
- Cascais, Lisboa, Loures, Lourinhã, Mafra
- Odivelas, Oeiras, Sintra, Sobral de Monte Agraço
- Torres Vedras, Vila Franca de Xira
