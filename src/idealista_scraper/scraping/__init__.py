"""Scraping module for the Idealista scraper."""

from __future__ import annotations

from idealista_scraper.scraping.client import (
    WAIT_SELECTOR_DISTRICT_CONCELHOS,
    WAIT_SELECTOR_HOMEPAGE,
    WAIT_SELECTOR_LISTING_DETAIL,
    WAIT_SELECTOR_SEARCH_RESULTS,
    BrightDataClient,
    BrightDataClientError,
    PageClient,
    RequestsClient,
    create_client,
)
from idealista_scraper.scraping.details_scraper import DetailsScraper
from idealista_scraper.scraping.listings_scraper import ListingsScraper
from idealista_scraper.scraping.pre_scraper import PreScraper
from idealista_scraper.scraping.selectors import (
    ParsedConcelhoLink,
    ParsedDistrictInfo,
    ParsedListingCard,
    ParsedListingDetail,
    SearchMetadata,
    parse_concelhos_page,
    parse_homepage_districts,
    parse_listing_detail,
    parse_listings_page,
)

__all__ = [
    # Client
    "BrightDataClient",
    "BrightDataClientError",
    "PageClient",
    "RequestsClient",
    "create_client",
    # Wait selectors
    "WAIT_SELECTOR_DISTRICT_CONCELHOS",
    "WAIT_SELECTOR_HOMEPAGE",
    "WAIT_SELECTOR_LISTING_DETAIL",
    "WAIT_SELECTOR_SEARCH_RESULTS",
    # Scrapers
    "DetailsScraper",
    "ListingsScraper",
    "PreScraper",
    # Data models
    "ParsedConcelhoLink",
    "ParsedDistrictInfo",
    "ParsedListingCard",
    "ParsedListingDetail",
    "SearchMetadata",
    # Parsing functions
    "parse_concelhos_page",
    "parse_homepage_districts",
    "parse_listing_detail",
    "parse_listings_page",
]
