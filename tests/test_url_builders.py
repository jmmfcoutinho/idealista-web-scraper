"""Tests for URL building functions in the listings_scraper module."""

from __future__ import annotations

from idealista_scraper.scraping.listings_scraper import (
    IDEALISTA_BASE_URL,
    build_paginated_url,
    build_search_url,
)


class TestBuildSearchUrl:
    """Tests for build_search_url function."""

    def test_build_search_url_basic(self) -> None:
        """Test building a basic search URL."""
        url = build_search_url(
            location_slug="cascais",
            operation="comprar",
            property_type="casas",
        )

        assert url == f"{IDEALISTA_BASE_URL}/comprar-casas/cascais/"

    def test_build_search_url_with_pagination(self) -> None:
        """Test building a search URL with pagination."""
        url = build_search_url(
            location_slug="cascais",
            operation="comprar",
            property_type="casas",
            page=5,
        )

        assert "pagina=5" in url
        assert url.startswith(f"{IDEALISTA_BASE_URL}/comprar-casas/cascais/")

    def test_build_search_url_page_1_no_pagination(self) -> None:
        """Test that page 1 doesn't add pagination parameter."""
        url = build_search_url(
            location_slug="cascais",
            operation="comprar",
            property_type="casas",
            page=1,
        )

        assert "pagina=" not in url

    def test_build_search_url_with_max_price(self) -> None:
        """Test building a search URL with max price filter."""
        url = build_search_url(
            location_slug="cascais",
            operation="comprar",
            property_type="casas",
            max_price=500000,
        )

        assert "maxPrice=500000" in url

    def test_build_search_url_with_min_price(self) -> None:
        """Test building a search URL with min price filter."""
        url = build_search_url(
            location_slug="cascais",
            operation="comprar",
            property_type="casas",
            min_price=100000,
        )

        assert "minPrice=100000" in url

    def test_build_search_url_with_price_range(self) -> None:
        """Test building a search URL with both min and max price."""
        url = build_search_url(
            location_slug="cascais",
            operation="comprar",
            property_type="casas",
            min_price=100000,
            max_price=500000,
        )

        assert "minPrice=100000" in url
        assert "maxPrice=500000" in url

    def test_build_search_url_with_order(self) -> None:
        """Test building a search URL with sorting."""
        url = build_search_url(
            location_slug="cascais",
            operation="comprar",
            property_type="casas",
            order="precos-desc",
        )

        assert "ordem=precos-desc" in url

    def test_build_search_url_rent_operation(self) -> None:
        """Test building a search URL for rental properties."""
        url = build_search_url(
            location_slug="lisboa",
            operation="arrendar",
            property_type="apartamentos",
        )

        assert url == f"{IDEALISTA_BASE_URL}/arrendar-apartamentos/lisboa/"

    def test_build_search_url_full_parameters(self) -> None:
        """Test building a search URL with all parameters."""
        url = build_search_url(
            location_slug="cascais",
            operation="comprar",
            property_type="casas",
            page=3,
            min_price=100000,
            max_price=500000,
            order="precos-desc",
        )

        assert url.startswith(f"{IDEALISTA_BASE_URL}/comprar-casas/cascais/")
        assert "?" in url
        assert "minPrice=100000" in url
        assert "maxPrice=500000" in url
        assert "ordem=precos-desc" in url
        assert "pagina=3" in url


class TestBuildPaginatedUrl:
    """Tests for build_paginated_url function."""

    def test_build_paginated_url_page_1_unchanged(self) -> None:
        """Test that page 1 returns unchanged URL."""
        base_url = f"{IDEALISTA_BASE_URL}/comprar-casas/cascais/"
        url = build_paginated_url(base_url, page=1)

        assert url == base_url

    def test_build_paginated_url_add_pagination(self) -> None:
        """Test adding pagination to URL without query string."""
        base_url = f"{IDEALISTA_BASE_URL}/comprar-casas/cascais/"
        url = build_paginated_url(base_url, page=5)

        assert url == f"{base_url}?pagina=5"

    def test_build_paginated_url_with_existing_params(self) -> None:
        """Test adding pagination to URL with existing query string."""
        base_url = f"{IDEALISTA_BASE_URL}/comprar-casas/cascais/?maxPrice=500000"
        url = build_paginated_url(base_url, page=3)

        assert url == f"{base_url}&pagina=3"

    def test_build_paginated_url_replace_existing_pagination(self) -> None:
        """Test replacing existing pagination in URL."""
        base_url = f"{IDEALISTA_BASE_URL}/comprar-casas/cascais/?pagina=2"
        url = build_paginated_url(base_url, page=5)

        assert url == f"{IDEALISTA_BASE_URL}/comprar-casas/cascais/?pagina=5"
        assert "pagina=2" not in url

    def test_build_paginated_url_replace_pagination_with_other_params(self) -> None:
        """Test replacing pagination when other params exist."""
        base_url = (
            f"{IDEALISTA_BASE_URL}/comprar-casas/cascais/?ordem=precos-desc&pagina=2"
        )
        url = build_paginated_url(base_url, page=10)

        assert "pagina=10" in url
        assert "pagina=2" not in url
        assert "ordem=precos-desc" in url
