"""Tests for the selectors module.

Tests the HTML parsing functions using fixture files.
"""

from __future__ import annotations

from pathlib import Path

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

# Path to fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    """Load a fixture file.

    Args:
        name: Name of the fixture file.

    Returns:
        Contents of the fixture file.
    """
    return (FIXTURES_DIR / name).read_text()


# -----------------------------------------------------------------------------
# parse_listings_page tests
# -----------------------------------------------------------------------------


class TestParseListingsPage:
    """Tests for parse_listings_page function."""

    def test_parse_listings_page_returns_listings_and_metadata(self) -> None:
        """Test that parse_listings_page returns correct structure."""
        html = load_fixture("search_results.html")
        listings, metadata = parse_listings_page(html, "comprar", "casas")

        assert isinstance(listings, list)
        assert isinstance(metadata, SearchMetadata)

    def test_parse_listings_page_count(self) -> None:
        """Test that correct number of listings are parsed."""
        html = load_fixture("search_results.html")
        listings, _metadata = parse_listings_page(html, "comprar", "casas")

        # Should parse 3 listings (skipping the ad without data-element-id)
        assert len(listings) == 3

    def test_parse_listings_page_skips_ads(self) -> None:
        """Test that listings without data-element-id are skipped."""
        html = load_fixture("search_results.html")
        listings, _metadata = parse_listings_page(html, "comprar", "casas")

        # Verify no ad in results
        ad_ids = [item for item in listings if item.title == "Publicidade"]
        assert len(ad_ids) == 0

    def test_parse_listings_page_full_listing(self) -> None:
        """Test parsing a listing with all fields populated."""
        html = load_fixture("search_results.html")
        listings, _metadata = parse_listings_page(html, "comprar", "casas")

        # Find the full listing
        listing = next(item for item in listings if item.idealista_id == 34609275)

        assert isinstance(listing, ParsedListingCard)
        assert listing.idealista_id == 34609275
        assert listing.url == "/imovel/34609275/"
        assert listing.title == "Moradia T5 em Cascais"
        assert listing.price == 1500000
        assert listing.operation == "comprar"
        assert listing.property_type == "casas"
        assert listing.summary_location == "Cascais, Lisboa"
        assert "T5" in listing.details_raw
        assert "350 m² área bruta" in listing.details_raw
        assert listing.description == "Fantástica moradia com piscina e jardim"
        assert listing.agency_name == "RE/MAX Cascais"
        assert listing.agency_url == "/agencia/remax-cascais/"
        assert listing.image_url == "https://example.com/photo.jpg"
        assert "Luxo" in listing.tags
        assert "Piscina" in listing.tags

    def test_parse_listings_page_minimal_listing(self) -> None:
        """Test parsing a listing with minimal data."""
        html = load_fixture("search_results.html")
        listings, _metadata = parse_listings_page(html, "comprar", "casas")

        # Find the minimal listing
        listing = next(item for item in listings if item.idealista_id == 33977796)

        assert listing.idealista_id == 33977796
        assert listing.title == "Casa em Cascais"
        assert listing.price is None  # "Sob consulta" should parse to None
        assert listing.agency_name is None
        assert listing.agency_url is None
        assert listing.tags == []

    def test_parse_listings_page_metadata(self) -> None:
        """Test that metadata is correctly parsed."""
        html = load_fixture("search_results.html")
        _listings, metadata = parse_listings_page(html, "comprar", "casas")

        assert metadata.total_count == 4423
        assert metadata.page == 1
        assert metadata.has_next_page is True
        assert metadata.last_page == 60

    def test_parse_listings_page_lowest_price(self) -> None:
        """Test that lowest price on page is correctly tracked."""
        html = load_fixture("search_results.html")
        _listings, metadata = parse_listings_page(html, "comprar", "casas")

        # Lowest price should be 650000 (from the T3 listing)
        assert metadata.lowest_price_on_page == 650000


# -----------------------------------------------------------------------------
# parse_listing_detail tests
# -----------------------------------------------------------------------------


class TestParseListingDetail:
    """Tests for parse_listing_detail function."""

    def test_parse_listing_detail_returns_detail(self) -> None:
        """Test that parse_listing_detail returns correct structure."""
        html = load_fixture("listing_detail.html")
        detail = parse_listing_detail(html)

        assert isinstance(detail, ParsedListingDetail)

    def test_parse_listing_detail_basic_fields(self) -> None:
        """Test parsing basic fields from listing detail."""
        html = load_fixture("listing_detail.html")
        detail = parse_listing_detail(html)

        assert detail.title == "Moradia T5 em Cascais com piscina e jardim"
        assert detail.price == 1500000
        assert detail.location == "Rua das Flores, 123, Cascais, Lisboa"

    def test_parse_listing_detail_features(self) -> None:
        """Test parsing features from listing detail."""
        html = load_fixture("listing_detail.html")
        detail = parse_listing_detail(html)

        assert "T5" in detail.features_raw
        assert "350 m²" in detail.features_raw
        assert "5 quartos" in detail.features_raw
        assert "4 casas de banho" in detail.features_raw

    def test_parse_listing_detail_tags(self) -> None:
        """Test parsing tags from listing detail."""
        html = load_fixture("listing_detail.html")
        detail = parse_listing_detail(html)

        assert "Luxo" in detail.tags
        assert "Piscina" in detail.tags
        assert "Jardim" in detail.tags

    def test_parse_listing_detail_description(self) -> None:
        """Test parsing description from listing detail."""
        html = load_fixture("listing_detail.html")
        detail = parse_listing_detail(html)

        assert detail.description is not None
        assert "Fantástica moradia de luxo" in detail.description
        assert "piscina aquecida" in detail.description

    def test_parse_listing_detail_reference(self) -> None:
        """Test parsing reference from listing detail."""
        html = load_fixture("listing_detail.html")
        detail = parse_listing_detail(html)

        assert detail.reference == "ABC123"

    def test_parse_listing_detail_characteristics(self) -> None:
        """Test parsing characteristics from listing detail."""
        html = load_fixture("listing_detail.html")
        detail = parse_listing_detail(html)

        assert "Ano de construção" in detail.characteristics
        assert detail.characteristics["Ano de construção"] == "2015"
        assert "Estado" in detail.characteristics
        assert detail.characteristics["Estado"] == "Segunda mão/bom estado"

    def test_parse_listing_detail_equipment(self) -> None:
        """Test parsing equipment from listing detail."""
        html = load_fixture("listing_detail.html")
        detail = parse_listing_detail(html)

        assert "Ar condicionado" in detail.equipment
        assert "Aquecimento central" in detail.equipment
        assert "Varanda" in detail.equipment

    def test_parse_listing_detail_energy_class(self) -> None:
        """Test parsing energy class from listing detail."""
        html = load_fixture("listing_detail.html")
        detail = parse_listing_detail(html)

        assert detail.energy_class == "B"

    def test_parse_listing_detail_photo_count(self) -> None:
        """Test parsing photo count from listing detail."""
        html = load_fixture("listing_detail.html")
        detail = parse_listing_detail(html)

        assert detail.photo_count == 46


# -----------------------------------------------------------------------------
# parse_homepage_districts tests
# -----------------------------------------------------------------------------


class TestParseHomepageDistricts:
    """Tests for parse_homepage_districts function."""

    def test_parse_homepage_districts_returns_list(self) -> None:
        """Test that parse_homepage_districts returns a list."""
        html = load_fixture("homepage.html")
        districts = parse_homepage_districts(html)

        assert isinstance(districts, list)

    def test_parse_homepage_districts_count(self) -> None:
        """Test that correct number of districts are parsed."""
        html = load_fixture("homepage.html")
        districts = parse_homepage_districts(html)

        # Should parse 3 districts: Porto, Braga, Lisboa
        assert len(districts) == 3

    def test_parse_homepage_districts_info(self) -> None:
        """Test that district info is correctly parsed."""
        html = load_fixture("homepage.html")
        districts = parse_homepage_districts(html)

        # Find Porto district
        porto = next(d for d in districts if d.name == "Porto")
        assert isinstance(porto, ParsedDistrictInfo)
        assert porto.slug == "porto-distrito"
        assert len(porto.concelhos) == 3

        # Verify concelhos
        concelho_names = [c.name for c in porto.concelhos]
        assert "Porto (concelho)" in concelho_names
        assert "Vila Nova de Gaia" in concelho_names
        assert "Matosinhos" in concelho_names

    def test_parse_homepage_districts_lisboa(self) -> None:
        """Test parsing Lisboa district with more concelhos."""
        html = load_fixture("homepage.html")
        districts = parse_homepage_districts(html)

        lisboa = next(d for d in districts if d.name == "Lisboa")
        assert lisboa.slug == "lisboa-distrito"
        assert len(lisboa.concelhos) == 4

        concelho_slugs = [c.slug for c in lisboa.concelhos]
        assert "lisboa" in concelho_slugs
        assert "cascais" in concelho_slugs
        assert "sintra" in concelho_slugs
        assert "oeiras" in concelho_slugs


# -----------------------------------------------------------------------------
# parse_concelhos_page tests
# -----------------------------------------------------------------------------


class TestParseConcelhosPage:
    """Tests for parse_concelhos_page function."""

    def test_parse_concelhos_page_returns_list(self) -> None:
        """Test that parse_concelhos_page returns a list."""
        html = load_fixture("district_concelhos.html")
        concelhos = parse_concelhos_page(html)

        assert isinstance(concelhos, list)

    def test_parse_concelhos_page_count(self) -> None:
        """Test that correct number of concelhos are parsed."""
        html = load_fixture("district_concelhos.html")
        concelhos = parse_concelhos_page(html)

        # Should parse 7 concelhos
        assert len(concelhos) == 7

    def test_parse_concelhos_page_info(self) -> None:
        """Test that concelho info is correctly parsed."""
        html = load_fixture("district_concelhos.html")
        concelhos = parse_concelhos_page(html)

        # Find Cascais
        cascais = next(c for c in concelhos if c.slug == "cascais")
        assert isinstance(cascais, ParsedConcelhoLink)
        assert cascais.name == "Cascais"
        assert cascais.href == "/comprar-casas/cascais/"

    def test_parse_concelhos_page_skips_special_pages(self) -> None:
        """Test that special pages like concelhos-freguesias are skipped."""
        html = load_fixture("district_concelhos.html")
        concelhos = parse_concelhos_page(html)

        # Should not include special pages
        slugs = [c.slug for c in concelhos]
        assert "concelhos-freguesias" not in slugs
        assert "lisboa-distrito" not in slugs

    def test_parse_concelhos_page_deduplicates(self) -> None:
        """Test that duplicate concelhos are removed."""
        html = load_fixture("district_concelhos.html")
        concelhos = parse_concelhos_page(html)

        # Each slug should appear only once
        slugs = [c.slug for c in concelhos]
        assert len(slugs) == len(set(slugs))
