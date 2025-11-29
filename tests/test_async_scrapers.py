"""Tests for async scrapers.

Tests AsyncListingsScraper, AsyncDetailsScraper, and AsyncPreScraper
with mock clients to avoid actual network requests.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from idealista_scraper.config import RunConfig
from idealista_scraper.db import (
    Base,
    Concelho,
    District,
    Listing,
)
from idealista_scraper.scraping.async_details_scraper import (
    AsyncDetailsScraper,
    DetailFetchResult,
)
from idealista_scraper.scraping.async_listings_scraper import (
    AsyncListingsScraper,
    FetchResult,
)
from idealista_scraper.scraping.async_pre_scraper import (
    AsyncPreScraper,
    DistrictConcelhosResult,
)
from idealista_scraper.scraping.selectors import (
    ParsedConcelhoLink,
    ParsedDistrictInfo,
    ParsedListingCard,
    ParsedListingDetail,
    SearchMetadata,
)


def get_test_session_factory() -> sessionmaker:
    """Create an in-memory SQLite database session factory for testing.

    Returns:
        A sessionmaker instance configured with an in-memory database.
    """
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


# --- Test Fixtures ---


def sample_listing_card(
    idealista_id: int = 12345678,
    title: str = "Test Listing",
    price: int | None = 500000,
) -> ParsedListingCard:
    """Create a sample ParsedListingCard for testing."""
    return ParsedListingCard(
        idealista_id=idealista_id,
        url=f"/imovel/{idealista_id}/",
        title=title,
        price=price,
        operation="comprar",
        property_type="casas",
        summary_location="Cascais, Lisboa",
        details_raw=["T3", "120 m² área bruta"],
        description="A nice property",
        agency_name="Test Agency",
        agency_url="/agency/test/",
        image_url="https://example.com/image.jpg",
        tags=["Piscina", "Jardim"],
    )


def sample_listing_detail() -> ParsedListingDetail:
    """Create a sample ParsedListingDetail for testing."""
    return ParsedListingDetail(
        title="Test Listing Detail",
        price=500000,
        location="Rua Test, Cascais",
        features_raw=["T3", "3 quartos", "2 casas de banho", "120 m²"],
        tags=["Luxo"],
        description="Full description of the property.",
        reference="REF123",
        characteristics={"Ano de construção": "2010", "Estado": "Novo"},
        equipment=["Ar condicionado", "Piscina"],
        energy_class="B",
        photo_count=25,
    )


def sample_search_metadata(
    page: int = 1,
    total_count: int = 100,
    has_next: bool = True,
    last_page: int = 4,
    lowest_price: int | None = 400000,
) -> SearchMetadata:
    """Create sample SearchMetadata for testing."""
    return SearchMetadata(
        total_count=total_count,
        page=page,
        has_next_page=has_next,
        last_page=last_page,
        lowest_price_on_page=lowest_price,
    )


def sample_district_info() -> ParsedDistrictInfo:
    """Create a sample ParsedDistrictInfo for testing."""
    return ParsedDistrictInfo(
        name="Lisboa",
        slug="lisboa-distrito",
        concelhos=[],
        listing_count=50000,
    )


def sample_concelho_link(
    name: str = "Cascais",
    slug: str = "cascais",
) -> ParsedConcelhoLink:
    """Create a sample ParsedConcelhoLink for testing."""
    return ParsedConcelhoLink(
        name=name,
        slug=slug,
        href=f"/comprar-casas/{slug}/",
    )


# --- FetchResult Tests ---


class TestFetchResult:
    """Tests for FetchResult dataclass."""

    def test_successful_result(self) -> None:
        """Test creating a successful fetch result."""
        result = FetchResult(
            url="https://example.com/page1",
            page_num=1,
            html="<html>Content</html>",
        )
        assert result.url == "https://example.com/page1"
        assert result.page_num == 1
        assert result.html == "<html>Content</html>"
        assert result.error is None

    def test_failed_result(self) -> None:
        """Test creating a failed fetch result."""
        result = FetchResult(
            url="https://example.com/page1",
            page_num=1,
            html=None,
            error="Connection timeout",
        )
        assert result.html is None
        assert result.error == "Connection timeout"


class TestDetailFetchResult:
    """Tests for DetailFetchResult dataclass."""

    def test_successful_result(self) -> None:
        """Test creating a successful detail fetch result."""
        detail = sample_listing_detail()
        result = DetailFetchResult(
            listing_id=1,
            idealista_id=12345678,
            detail=detail,
        )
        assert result.listing_id == 1
        assert result.idealista_id == 12345678
        assert result.detail == detail
        assert result.error is None

    def test_failed_result(self) -> None:
        """Test creating a failed detail fetch result."""
        result = DetailFetchResult(
            listing_id=1,
            idealista_id=12345678,
            detail=None,
            error="Page not found",
        )
        assert result.detail is None
        assert result.error == "Page not found"


class TestDistrictConcelhosResult:
    """Tests for DistrictConcelhosResult dataclass."""

    def test_successful_result(self) -> None:
        """Test creating a successful district concelhos result."""
        concelhos = [sample_concelho_link("Cascais", "cascais")]
        result = DistrictConcelhosResult(
            district_slug="lisboa-distrito",
            concelhos=concelhos,
        )
        assert result.district_slug == "lisboa-distrito"
        assert len(result.concelhos) == 1
        assert result.error is None

    def test_failed_result(self) -> None:
        """Test creating a failed district concelhos result."""
        result = DistrictConcelhosResult(
            district_slug="lisboa-distrito",
            concelhos=[],
            error="Failed to fetch",
        )
        assert len(result.concelhos) == 0
        assert result.error == "Failed to fetch"


# --- AsyncListingsScraper Tests ---


class TestAsyncListingsScraperInit:
    """Tests for AsyncListingsScraper initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()
        config = RunConfig(
            locations=["cascais"],
            operation="comprar",
            property_types=["casas"],
        )

        scraper = AsyncListingsScraper(
            client=mock_client,
            session_factory=session_factory,
            config=config,
        )

        assert scraper.concurrency == 5
        assert scraper._semaphore is None

    def test_init_with_custom_concurrency(self) -> None:
        """Test initialization with custom concurrency."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()
        config = RunConfig(
            locations=["cascais"],
            operation="comprar",
            property_types=["casas"],
        )

        scraper = AsyncListingsScraper(
            client=mock_client,
            session_factory=session_factory,
            config=config,
            concurrency=10,
        )

        assert scraper.concurrency == 10


class TestAsyncListingsScraperFetchPage:
    """Tests for AsyncListingsScraper._fetch_page method."""

    @pytest.mark.asyncio
    async def test_fetch_page_success(self) -> None:
        """Test successful page fetch."""
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(return_value="<html>Page content</html>")
        mock_client.close = AsyncMock()

        session_factory = get_test_session_factory()
        config = RunConfig(
            locations=["cascais"],
            operation="comprar",
            property_types=["casas"],
        )

        scraper = AsyncListingsScraper(
            client=mock_client,
            session_factory=session_factory,
            config=config,
        )
        scraper._semaphore = asyncio.Semaphore(5)

        result = await scraper._fetch_page("https://example.com/page1", 1)

        assert result.html == "<html>Page content</html>"
        assert result.page_num == 1
        assert result.error is None

    @pytest.mark.asyncio
    async def test_fetch_page_failure(self) -> None:
        """Test failed page fetch."""
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(side_effect=Exception("Network error"))
        mock_client.close = AsyncMock()

        session_factory = get_test_session_factory()
        config = RunConfig(
            locations=["cascais"],
            operation="comprar",
            property_types=["casas"],
        )

        scraper = AsyncListingsScraper(
            client=mock_client,
            session_factory=session_factory,
            config=config,
        )
        scraper._semaphore = asyncio.Semaphore(5)

        result = await scraper._fetch_page("https://example.com/page1", 1)

        assert result.html is None
        assert "Network error" in result.error

    @pytest.mark.asyncio
    async def test_fetch_page_requires_semaphore(self) -> None:
        """Test that fetch_page raises if semaphore not initialized."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()
        config = RunConfig(
            locations=["cascais"],
            operation="comprar",
            property_types=["casas"],
        )

        scraper = AsyncListingsScraper(
            client=mock_client,
            session_factory=session_factory,
            config=config,
        )
        # Don't initialize semaphore

        with pytest.raises(RuntimeError, match="Semaphore not initialized"):
            await scraper._fetch_page("https://example.com/page1", 1)


class TestAsyncListingsScraperFetchBatch:
    """Tests for AsyncListingsScraper._fetch_pages_batch method."""

    @pytest.mark.asyncio
    async def test_fetch_pages_batch(self) -> None:
        """Test batch page fetching."""
        mock_client = AsyncMock()

        async def mock_get_html(url: str, *args, **kwargs):  # noqa: ARG001
            page = int(url.split("=")[-1])
            return f"<html>Page {page}</html>"

        mock_client.get_html = mock_get_html
        mock_client.close = AsyncMock()

        session_factory = get_test_session_factory()
        config = RunConfig(
            locations=["cascais"],
            operation="comprar",
            property_types=["casas"],
        )

        scraper = AsyncListingsScraper(
            client=mock_client,
            session_factory=session_factory,
            config=config,
        )
        scraper._semaphore = asyncio.Semaphore(5)

        # Fetch pages 2-4
        results = await scraper._fetch_pages_batch(
            "https://example.com/search?pagina=1",
            start_page=2,
            end_page=4,
        )

        assert len(results) == 3
        # Results may be in any order due to async
        page_nums = {r.page_num for r in results}
        assert page_nums == {2, 3, 4}


class TestAsyncListingsScraperConcurrency:
    """Tests for concurrency behavior in AsyncListingsScraper."""

    @pytest.mark.asyncio
    async def test_concurrency_limit_respected(self) -> None:
        """Test that semaphore limits concurrent requests."""
        max_concurrent = 0
        current_concurrent = 0

        async def mock_get_html(*args, **kwargs):  # noqa: ARG001
            nonlocal max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.05)  # Simulate network delay
            current_concurrent -= 1
            return "<html>Test</html>"

        mock_client = AsyncMock()
        mock_client.get_html = mock_get_html
        mock_client.close = AsyncMock()

        session_factory = get_test_session_factory()
        config = RunConfig(
            locations=["cascais"],
            operation="comprar",
            property_types=["casas"],
        )

        scraper = AsyncListingsScraper(
            client=mock_client,
            session_factory=session_factory,
            config=config,
            concurrency=2,  # Limit to 2 concurrent
        )
        scraper._semaphore = asyncio.Semaphore(2)

        # Start 5 concurrent tasks
        tasks = [
            scraper._fetch_page(f"https://example.com/page{i}", i) for i in range(1, 6)
        ]
        await asyncio.gather(*tasks)

        # Max concurrent should not exceed 2
        assert max_concurrent <= 2


class TestAsyncListingsScraperProcessResults:
    """Tests for AsyncListingsScraper._process_page_results method."""

    def test_process_page_results(self) -> None:
        """Test processing page results."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()
        session = session_factory()

        # Create a district and concelho
        district = District(name="Lisboa", slug="lisboa-distrito")
        session.add(district)
        session.flush()
        concelho = Concelho(district_id=district.id, name="Cascais", slug="cascais")
        session.add(concelho)
        session.commit()

        config = RunConfig(
            locations=["cascais"],
            operation="comprar",
            property_types=["casas"],
        )

        scraper = AsyncListingsScraper(
            client=mock_client,
            session_factory=session_factory,
            config=config,
        )

        from idealista_scraper.scraping.listings_scraper import ScrapeSegment

        segment = ScrapeSegment(
            location_slug="cascais",
            operation="comprar",
            property_type="casas",
        )

        listings = [
            sample_listing_card(12345678, "Listing 1", 500000),
            sample_listing_card(12345679, "Listing 2", 400000),
        ]
        metadata = sample_search_metadata(page=1, lowest_price=400000)

        stats: dict[str, int | None] = {
            "listings_processed": 0,
            "listings_created": 0,
            "listings_updated": 0,
            "pages_scraped": 0,
            "next_max_price": None,
        }

        lowest = scraper._process_page_results(
            session, segment, listings, metadata, stats
        )

        assert stats["listings_processed"] == 2
        assert stats["listings_created"] == 2
        assert stats["pages_scraped"] == 1
        assert lowest == 400000

        session.close()


# --- AsyncDetailsScraper Tests ---


class TestAsyncDetailsScraperInit:
    """Tests for AsyncDetailsScraper initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()

        scraper = AsyncDetailsScraper(
            client=mock_client,
            session_factory=session_factory,
        )

        assert scraper.max_listings is None
        assert scraper.concurrency == 5
        assert scraper._semaphore is None

    def test_init_with_limit_and_concurrency(self) -> None:
        """Test initialization with custom limit and concurrency."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()

        scraper = AsyncDetailsScraper(
            client=mock_client,
            session_factory=session_factory,
            max_listings=100,
            concurrency=10,
        )

        assert scraper.max_listings == 100
        assert scraper.concurrency == 10


class TestAsyncDetailsScraperFetchDetail:
    """Tests for AsyncDetailsScraper._fetch_detail method."""

    @pytest.mark.asyncio
    async def test_fetch_detail_success(self) -> None:
        """Test successful detail fetch."""
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(
            return_value="<html><h1>Detail page</h1></html>"
        )
        mock_client.close = AsyncMock()

        session_factory = get_test_session_factory()
        session = session_factory()

        # Create required parent objects
        district = District(name="Lisboa", slug="lisboa-distrito")
        session.add(district)
        session.flush()
        concelho = Concelho(district_id=district.id, name="Cascais", slug="cascais")
        session.add(concelho)
        session.flush()

        # Create a test listing
        listing = Listing(
            idealista_id=12345678,
            concelho_id=concelho.id,
            operation="comprar",
            property_type="casas",
            url="https://www.idealista.pt/imovel/12345678/",
            price=500000,
            is_active=True,
        )
        session.add(listing)
        session.commit()

        scraper = AsyncDetailsScraper(
            client=mock_client,
            session_factory=session_factory,
        )
        scraper._semaphore = asyncio.Semaphore(5)

        with patch(
            "idealista_scraper.scraping.async_details_scraper.parse_listing_detail"
        ) as mock_parse:
            mock_parse.return_value = sample_listing_detail()
            result = await scraper._fetch_detail(listing)

        assert result.listing_id == listing.id
        assert result.idealista_id == 12345678
        assert result.detail is not None
        assert result.error is None

        session.close()

    @pytest.mark.asyncio
    async def test_fetch_detail_failure(self) -> None:
        """Test failed detail fetch."""
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(side_effect=Exception("Page not found"))
        mock_client.close = AsyncMock()

        session_factory = get_test_session_factory()
        session = session_factory()

        # Create required parent objects
        district = District(name="Lisboa", slug="lisboa-distrito")
        session.add(district)
        session.flush()
        concelho = Concelho(district_id=district.id, name="Cascais", slug="cascais")
        session.add(concelho)
        session.flush()

        listing = Listing(
            idealista_id=12345678,
            concelho_id=concelho.id,
            operation="comprar",
            property_type="casas",
            url="https://www.idealista.pt/imovel/12345678/",
            price=500000,
            is_active=True,
        )
        session.add(listing)
        session.commit()

        scraper = AsyncDetailsScraper(
            client=mock_client,
            session_factory=session_factory,
        )
        scraper._semaphore = asyncio.Semaphore(5)

        result = await scraper._fetch_detail(listing)

        assert result.detail is None
        assert "Page not found" in result.error

        session.close()


class TestAsyncDetailsScraperUpdateListing:
    """Tests for AsyncDetailsScraper._update_listing_from_detail method."""

    def test_update_listing_from_detail(self) -> None:
        """Test updating listing with detail data."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()
        session = session_factory()

        # Create required parent objects
        district = District(name="Lisboa", slug="lisboa-distrito")
        session.add(district)
        session.flush()
        concelho = Concelho(district_id=district.id, name="Cascais", slug="cascais")
        session.add(concelho)
        session.flush()

        listing = Listing(
            idealista_id=12345678,
            concelho_id=concelho.id,
            operation="comprar",
            property_type="casas",
            url="https://www.idealista.pt/imovel/12345678/",
            price=500000,
            is_active=True,
        )
        session.add(listing)
        session.commit()

        scraper = AsyncDetailsScraper(
            client=mock_client,
            session_factory=session_factory,
        )

        detail = sample_listing_detail()
        scraper._update_listing_from_detail(listing, detail)
        session.commit()

        # Verify updates
        assert listing.description == "Full description of the property."
        assert listing.reference == "REF123"
        assert listing.energy_class == "B"
        assert listing.has_air_conditioning is True
        assert listing.has_pool is True
        assert listing.bedrooms == 3
        assert listing.bathrooms == 2

        session.close()


class TestAsyncDetailsScraperNormalizeEnergyClass:
    """Tests for AsyncDetailsScraper._normalize_energy_class method."""

    def test_normalize_simple_class(self) -> None:
        """Test normalizing simple energy class."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()

        scraper = AsyncDetailsScraper(
            client=mock_client,
            session_factory=session_factory,
        )

        assert scraper._normalize_energy_class("B") == "B"
        assert scraper._normalize_energy_class("A") == "A"
        assert scraper._normalize_energy_class("c") == "C"

    def test_normalize_class_with_modifier(self) -> None:
        """Test normalizing energy class with modifier."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()

        scraper = AsyncDetailsScraper(
            client=mock_client,
            session_factory=session_factory,
        )

        assert scraper._normalize_energy_class("A+") == "A+"
        assert scraper._normalize_energy_class("B-") == "B-"
        # Note: "Classe A+" matches 'C' from Classe first (known limitation)
        # In practice, energy_class values come pre-parsed from the selector
        assert scraper._normalize_energy_class("A+ (certificado)") == "A+"


# --- AsyncPreScraper Tests ---


class TestAsyncPreScraperInit:
    """Tests for AsyncPreScraper initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()

        scraper = AsyncPreScraper(
            client=mock_client,
            session_factory=session_factory,
        )

        assert scraper.concurrency == 5
        assert scraper._semaphore is None

    def test_init_with_custom_concurrency(self) -> None:
        """Test initialization with custom concurrency."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()

        scraper = AsyncPreScraper(
            client=mock_client,
            session_factory=session_factory,
            concurrency=10,
        )

        assert scraper.concurrency == 10


class TestAsyncPreScraperFetchConcelhos:
    """Tests for AsyncPreScraper._fetch_concelhos_for_district method."""

    @pytest.mark.asyncio
    async def test_fetch_concelhos_success(self) -> None:
        """Test successful concelhos fetch."""
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(
            return_value="<html><section class='municipality-search'></section></html>"
        )
        mock_client.close = AsyncMock()

        session_factory = get_test_session_factory()

        scraper = AsyncPreScraper(
            client=mock_client,
            session_factory=session_factory,
        )
        scraper._semaphore = asyncio.Semaphore(5)

        with patch(
            "idealista_scraper.scraping.async_pre_scraper.parse_concelhos_page"
        ) as mock_parse:
            mock_parse.return_value = [
                sample_concelho_link("Cascais", "cascais"),
                sample_concelho_link("Sintra", "sintra"),
            ]
            result = await scraper._fetch_concelhos_for_district("lisboa-distrito")

        assert result.district_slug == "lisboa-distrito"
        assert len(result.concelhos) == 2
        assert result.error is None

    @pytest.mark.asyncio
    async def test_fetch_concelhos_failure(self) -> None:
        """Test failed concelhos fetch."""
        mock_client = AsyncMock()
        mock_client.get_html = AsyncMock(side_effect=Exception("Connection error"))
        mock_client.close = AsyncMock()

        session_factory = get_test_session_factory()

        scraper = AsyncPreScraper(
            client=mock_client,
            session_factory=session_factory,
        )
        scraper._semaphore = asyncio.Semaphore(5)

        result = await scraper._fetch_concelhos_for_district("lisboa-distrito")

        assert len(result.concelhos) == 0
        assert "Connection error" in result.error


class TestAsyncPreScraperFetchAllConcelhos:
    """Tests for AsyncPreScraper._fetch_all_concelhos method."""

    @pytest.mark.asyncio
    async def test_fetch_all_concelhos(self) -> None:
        """Test fetching concelhos for multiple districts."""
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()

        call_count = 0

        async def mock_get_html(*args, **kwargs):  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            return "<html>District page</html>"

        mock_client.get_html = mock_get_html

        session_factory = get_test_session_factory()

        scraper = AsyncPreScraper(
            client=mock_client,
            session_factory=session_factory,
        )
        scraper._semaphore = asyncio.Semaphore(5)

        with patch(
            "idealista_scraper.scraping.async_pre_scraper.parse_concelhos_page"
        ) as mock_parse:
            mock_parse.return_value = [sample_concelho_link()]
            results = await scraper._fetch_all_concelhos(
                ["lisboa-distrito", "porto-distrito", "braga-distrito"]
            )

        assert len(results) == 3
        assert call_count == 3


class TestAsyncPreScraperUpsertDistrict:
    """Tests for AsyncPreScraper._upsert_district method."""

    def test_create_new_district(self) -> None:
        """Test creating a new district."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()
        session = session_factory()

        scraper = AsyncPreScraper(
            client=mock_client,
            session_factory=session_factory,
        )

        district_info = sample_district_info()
        district, created = scraper._upsert_district(session, district_info)
        session.commit()

        assert created is True
        assert district.name == "Lisboa"
        assert district.slug == "lisboa-distrito"

        session.close()

    def test_update_existing_district(self) -> None:
        """Test updating an existing district."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()
        session = session_factory()

        # Create existing district
        existing = District(name="Lisboa", slug="lisboa-distrito", listing_count=1000)
        session.add(existing)
        session.commit()

        scraper = AsyncPreScraper(
            client=mock_client,
            session_factory=session_factory,
        )

        district_info = ParsedDistrictInfo(
            name="Lisboa",
            slug="lisboa-distrito",
            concelhos=[],
            listing_count=50000,  # Updated count
        )

        district, created = scraper._upsert_district(session, district_info)
        session.commit()

        assert created is False
        assert district.listing_count == 50000

        session.close()


class TestAsyncPreScraperUpsertConcelho:
    """Tests for AsyncPreScraper._upsert_concelho method."""

    def test_create_new_concelho(self) -> None:
        """Test creating a new concelho."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()
        session = session_factory()

        # Create parent district
        district = District(name="Lisboa", slug="lisboa-distrito")
        session.add(district)
        session.commit()

        scraper = AsyncPreScraper(
            client=mock_client,
            session_factory=session_factory,
        )

        concelho_link = sample_concelho_link("Cascais", "cascais")
        created = scraper._upsert_concelho(session, district, concelho_link)
        session.commit()

        assert created is True

        # Verify in DB
        concelho = session.query(Concelho).filter_by(slug="cascais").first()
        assert concelho is not None
        assert concelho.name == "Cascais"
        assert concelho.district_id == district.id

        session.close()


# --- Integration-style Tests ---


class TestAsyncScrapersCreateScrapeRun:
    """Tests for ScrapeRun creation in async scrapers."""

    def test_listings_scraper_creates_run(self) -> None:
        """Test that listings scraper creates a ScrapeRun record."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()
        session = session_factory()

        config = RunConfig(
            locations=["cascais"],
            operation="comprar",
            property_types=["casas"],
        )

        scraper = AsyncListingsScraper(
            client=mock_client,
            session_factory=session_factory,
            config=config,
            concurrency=5,
        )

        run = scraper._create_scrape_run(session)

        assert run.run_type == "scrape-async"
        assert run.status == "running"
        assert run.config["concurrency"] == 5

        session.close()

    def test_details_scraper_creates_run(self) -> None:
        """Test that details scraper creates a ScrapeRun record."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()
        session = session_factory()

        scraper = AsyncDetailsScraper(
            client=mock_client,
            session_factory=session_factory,
            max_listings=50,
            concurrency=8,
        )

        run = scraper._create_scrape_run(session)

        assert run.run_type == "scrape-details-async"
        assert run.status == "running"
        assert run.config["max_listings"] == 50
        assert run.config["concurrency"] == 8

        session.close()

    def test_pre_scraper_creates_run(self) -> None:
        """Test that pre-scraper creates a ScrapeRun record."""
        mock_client = AsyncMock()
        session_factory = get_test_session_factory()
        session = session_factory()

        scraper = AsyncPreScraper(
            client=mock_client,
            session_factory=session_factory,
            concurrency=3,
        )

        run = scraper._create_scrape_run(session)

        assert run.run_type == "prescrape-async"
        assert run.status == "running"
        assert run.config["concurrency"] == 3

        session.close()
