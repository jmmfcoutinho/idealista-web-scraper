"""HTML parsing helpers and selectors based on findings.

This module contains pure functions for parsing Idealista HTML pages
into typed data structures using BeautifulSoup.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from typing import Literal

from bs4 import BeautifulSoup, NavigableString, Tag

from idealista_scraper.utils.logging import get_logger

logger = get_logger(__name__)


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------


@dataclass
class ParsedListingCard:
    """Parsed data from a listing card on search results page.

    Attributes:
        idealista_id: Unique listing ID from Idealista.
        url: Relative URL to the listing detail page.
        title: Listing title/headline.
        price: Price in euros, or None if not available.
        operation: The operation type (comprar or arrendar).
        property_type: The type of property.
        summary_location: Location summary text.
        details_raw: Raw detail strings (e.g., ["T3", "110 m²"]).
        description: Short description snippet.
        agency_name: Name of the listing agency.
        agency_url: URL to the agency page.
        image_url: URL of the main listing image.
        tags: List of tags (e.g., ["Luxo", "Terraço"]).
    """

    idealista_id: int
    url: str
    title: str
    price: int | None
    operation: Literal["comprar", "arrendar"]
    property_type: str
    summary_location: str | None = None
    details_raw: list[str] = field(default_factory=list)
    description: str | None = None
    agency_name: str | None = None
    agency_url: str | None = None
    image_url: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class SearchMetadata:
    """Metadata from a search results page.

    Attributes:
        total_count: Total number of listings matching the search.
        page: Current page number.
        has_next_page: Whether there is a next page.
        last_page: The last page number, if known.
        lowest_price_on_page: The lowest price on this page.
    """

    total_count: int
    page: int
    has_next_page: bool
    last_page: int | None = None
    lowest_price_on_page: int | None = None


@dataclass
class ParsedListingDetail:
    """Parsed data from an individual listing detail page.

    Attributes:
        title: Full listing title.
        price: Price in euros.
        location: Location string from the page.
        features_raw: Raw feature strings from info-features div.
        tags: Tags like "Luxo", etc.
        description: Full listing description.
        reference: Agency reference number.
        characteristics: Parsed characteristics dict.
        equipment: List of equipment items (pool, garden, AC, etc.).
        energy_class: Energy certificate class (A, B, C, etc.).
        photo_count: Total number of photos.
    """

    title: str | None = None
    price: int | None = None
    location: str | None = None
    features_raw: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    description: str | None = None
    reference: str | None = None
    characteristics: dict[str, str] = field(default_factory=dict)
    equipment: list[str] = field(default_factory=list)
    energy_class: str | None = None
    photo_count: int | None = None


@dataclass
class ParsedConcelhoLink:
    """Parsed link to a concelho (municipality).

    Attributes:
        name: Display name of the concelho.
        slug: URL slug for the concelho.
        href: Full relative href to the concelho page.
    """

    name: str
    slug: str
    href: str


@dataclass
class ParsedDistrictInfo:
    """Parsed information about a district from the homepage.

    Attributes:
        name: Display name of the district.
        slug: URL slug for the district.
        concelhos: List of concelho links in this district.
        listing_count: Number of listings, if available.
    """

    name: str
    slug: str
    concelhos: list[ParsedConcelhoLink] = field(default_factory=list)
    listing_count: int | None = None


# -----------------------------------------------------------------------------
# Parsing Helpers
# -----------------------------------------------------------------------------


def _parse_price(price_text: str) -> int | None:
    """Parse a price string to an integer.

    Args:
        price_text: Price string like "36.500.000€" or "2.700.000 €" or "3.500€/mês".

    Returns:
        Integer price in euros, or None if parsing fails.
    """
    if not price_text:
        return None

    # Remove currency symbol, spaces, thousands separators, and rental suffix
    cleaned = (
        price_text.replace("€", "")
        .replace(" ", "")
        .replace(".", "")
        .replace("/mês", "")
        .replace("/mes", "")
    )

    # Handle decimal separator (comma in PT)
    if "," in cleaned:
        cleaned = cleaned.split(",")[0]

    try:
        return int(cleaned)
    except ValueError:
        logger.debug("Could not parse price: %s", price_text)
        return None


def _parse_count_from_text(text: str) -> int | None:
    """Extract a count number from text like "4.423 casas...".

    Args:
        text: Text containing a number with dots as thousands separators.

    Returns:
        Parsed integer count, or None if not found.
    """
    if not text:
        return None

    # Match numbers with optional dot separators: 4.423 or 423
    match = re.search(r"([\d.]+)", text)
    if match:
        num_str = match.group(1).replace(".", "")
        try:
            return int(num_str)
        except ValueError:
            pass
    return None


def _extract_slug_from_href(href: str) -> str:
    """Extract the location slug from a URL path.

    Args:
        href: URL path like "/comprar-casas/cascais/" or
              "/comprar-casas/lisboa-distrito/concelhos-freguesias".

    Returns:
        The location slug (e.g., "cascais" or "lisboa-distrito").
    """
    if not href:
        return ""

    # Remove trailing slash and split
    parts = href.rstrip("/").split("/")

    # Look for the location slug (after operation-type)
    for i, part in enumerate(parts):
        if part in ("comprar-casas", "arrendar-casas") and i + 1 < len(parts):
            slug = parts[i + 1]
            # Handle /concelhos-freguesias suffix
            if slug == "concelhos-freguesias" and i > 0:
                return parts[i - 1] if i - 1 >= 0 else ""
            return slug

    # Fallback: return second-to-last non-empty part
    non_empty = [p for p in parts if p and p != "concelhos-freguesias"]
    return non_empty[-1] if non_empty else ""


def _get_text(element: Tag | NavigableString | None, strip: bool = True) -> str | None:
    """Safely get text content from a BeautifulSoup element.

    Args:
        element: BeautifulSoup Tag, NavigableString, or None.
        strip: Whether to strip whitespace.

    Returns:
        Text content or None if element is None.
    """
    if element is None:
        return None
    if isinstance(element, NavigableString):
        text = str(element)
        return text.strip() if strip else text
    text = element.get_text(strip=strip)
    return text if text else None


def _get_attr(element: Tag | None, attr: str) -> str | None:
    """Safely get an attribute from a BeautifulSoup element.

    Args:
        element: BeautifulSoup Tag or None.
        attr: Attribute name.

    Returns:
        Attribute value as string or None.
    """
    if element is None:
        return None
    value = element.get(attr)
    if value is None:
        return None
    if isinstance(value, list):
        return " ".join(value)
    return str(value)


# -----------------------------------------------------------------------------
# Main Parsing Functions
# -----------------------------------------------------------------------------


def parse_listings_page(
    html: str,
    operation: Literal["comprar", "arrendar"],
    property_type: str = "casas",
) -> tuple[list[ParsedListingCard], SearchMetadata]:
    """Parse a search results page into listing cards and metadata.

    Args:
        html: The HTML content of the search results page.
        operation: The operation type for these listings.
        property_type: The property type being searched.

    Returns:
        A tuple of (list of ParsedListingCard, SearchMetadata).
    """
    soup = BeautifulSoup(html, "lxml")
    listings: list[ParsedListingCard] = []

    # Parse total count from h1
    h1 = soup.find("h1", id="h1-container")
    total_count = _parse_count_from_text(_get_text(h1) or "")

    # Find all listing articles (filter out ads without data-element-id)
    articles = soup.find_all("article", class_="item")
    lowest_price: int | None = None

    for article in articles:
        if not isinstance(article, Tag):
            continue

        # Skip ads (no data-element-id)
        element_id = _get_attr(article, "data-element-id")
        if not element_id:
            continue

        try:
            idealista_id = int(element_id)
        except ValueError:
            logger.warning("Invalid listing ID: %s", element_id)
            continue

        # Title and URL
        link = article.find("a", class_="item-link")
        if not isinstance(link, Tag):
            continue

        title = _get_text(link) or ""
        url = _get_attr(link, "href") or ""

        # Price
        price_span = article.find("span", class_="item-price")
        price = _parse_price(_get_text(price_span) or "")

        # Track lowest price
        if price is not None and (lowest_price is None or price < lowest_price):
            lowest_price = price

        # Location summary (may be in item-detail or separate element)
        location_elem = article.find("span", class_="item-location")
        summary_location = _get_text(location_elem)

        # Details (rooms, area, etc.)
        detail_spans = article.find_all("span", class_="item-detail")
        details_raw = [
            text for span in detail_spans if (text := _get_text(span)) is not None
        ]

        # Description snippet
        desc_elem = article.find("p", class_="ellipsis")
        description = _get_text(desc_elem)

        # Agency info
        agency_name: str | None = None
        agency_url: str | None = None
        agency_pic = article.find("picture", class_="logo-branding")
        if isinstance(agency_pic, Tag):
            agency_img = agency_pic.find("img")
            if isinstance(agency_img, Tag):
                agency_name = _get_attr(agency_img, "alt")
            agency_link = agency_pic.find("a")
            if isinstance(agency_link, Tag):
                agency_url = _get_attr(agency_link, "href")

        # Main image
        img = article.find("img", alt="Primeira foto do imóvel")
        image_url = _get_attr(img, "src") if isinstance(img, Tag) else None

        # Tags
        tags: list[str] = []
        tags_container = article.find("div", class_="item-tags")
        if isinstance(tags_container, Tag):
            tag_spans = tags_container.find_all("span")
            tags = [text for t in tag_spans if (text := _get_text(t)) is not None]

        listing = ParsedListingCard(
            idealista_id=idealista_id,
            url=url,
            title=title,
            price=price,
            operation=operation,
            property_type=property_type,
            summary_location=summary_location,
            details_raw=details_raw,
            description=description,
            agency_name=agency_name,
            agency_url=agency_url,
            image_url=image_url,
            tags=tags,
        )
        listings.append(listing)

    # Parse pagination
    page = 1
    has_next_page = False
    last_page: int | None = None

    pagination = soup.find("div", class_="pagination")
    if isinstance(pagination, Tag):
        # Current page
        current_li = pagination.find("li", class_="selected")
        if isinstance(current_li, Tag):
            current_span = current_li.find("span")
            page_text = _get_text(current_span)
            if page_text:
                with contextlib.suppress(ValueError):
                    page = int(page_text)

        # Next page
        next_li = pagination.find("li", class_="next")
        has_next_page = next_li is not None and isinstance(next_li, Tag)

        # Last page (from page links)
        page_links = pagination.find_all("a")
        for link in page_links:
            if not isinstance(link, Tag):
                continue
            href = _get_attr(link, "href") or ""
            page_match = re.search(r"/pagina-(\d+)", href)
            if page_match:
                page_num = int(page_match.group(1))
                if last_page is None or page_num > last_page:
                    last_page = page_num

        # Also check span in last li for page number
        all_lis = pagination.find_all("li")
        for li in reversed(all_lis):
            if not isinstance(li, Tag):
                continue
            if "next" in (li.get("class") or []):
                continue
            span = li.find("span")
            span_text = _get_text(span)
            if span_text and span_text.isdigit():
                page_num = int(span_text)
                if last_page is None or page_num > last_page:
                    last_page = page_num
                break

    metadata = SearchMetadata(
        total_count=total_count or 0,
        page=page,
        has_next_page=has_next_page,
        last_page=last_page,
        lowest_price_on_page=lowest_price,
    )

    logger.debug(
        "Parsed %d listings from page %d (total: %d, has_next: %s)",
        len(listings),
        page,
        total_count or 0,
        has_next_page,
    )

    return listings, metadata


def parse_listing_detail(html: str) -> ParsedListingDetail:
    """Parse an individual listing detail page.

    Args:
        html: The HTML content of the listing detail page.

    Returns:
        ParsedListingDetail with extracted data.
    """
    soup = BeautifulSoup(html, "lxml")
    result = ParsedListingDetail()

    # Title
    h1 = soup.find("h1")
    result.title = _get_text(h1)

    # Price
    price_span = soup.find("span", class_="info-data-price")
    result.price = _parse_price(_get_text(price_span) or "")

    # Location
    location_span = soup.find("span", class_="main-info__title-minor")
    result.location = _get_text(location_span)

    # Features from header
    features_div = soup.find("div", class_="info-features")
    if isinstance(features_div, Tag):
        feature_spans = features_div.find_all("span")
        result.features_raw = [
            text for s in feature_spans if (text := _get_text(s)) is not None
        ]

    # Tags
    tags_div = soup.find("div", class_="detail-info-tags")
    if isinstance(tags_div, Tag):
        tag_spans = tags_div.find_all("span", class_="tag")
        result.tags = [text for t in tag_spans if (text := _get_text(t)) is not None]

    # Description
    comment_div = soup.find("div", class_="comment")
    if isinstance(comment_div, Tag):
        p = comment_div.find("p")
        result.description = _get_text(p)

    # Reference
    reference_elem = soup.find("p", class_="txt-ref")
    if isinstance(reference_elem, Tag):
        ref_text = _get_text(reference_elem)
        if ref_text:
            # Extract reference number from text like "Referência: 12345"
            match = re.search(r"(?:Refer[êe]ncia|Ref\.?):?\s*(.+)", ref_text, re.I)
            result.reference = match.group(1).strip() if match else ref_text

    # Features from details-property_features sections (bathrooms, area, etc.)
    for section in soup.find_all("div", class_="details-property_features"):
        if not isinstance(section, Tag):
            continue
        items = section.find_all("li")
        for item in items:
            if not isinstance(item, Tag):
                continue
            text = _get_text(item)
            if text:
                # Add to features_raw if not already there
                if text not in result.features_raw:
                    result.features_raw.append(text)
                # Also try to parse as key:value
                if ":" in text:
                    key, value = text.split(":", 1)
                    result.characteristics[key.strip()] = value.strip()

    # Equipment from details-property-feature-two section
    equipment_section = soup.find("div", class_="details-property-feature-two")
    if isinstance(equipment_section, Tag):
        items = equipment_section.find_all("li")
        for item in items:
            if not isinstance(item, Tag):
                continue
            text = _get_text(item)
            if text and "Classe energética" not in text:
                result.equipment.append(text)

    # Energy class - look for icon-energy-X pattern
    for elem in soup.find_all("span", class_=True):
        if not isinstance(elem, Tag):
            continue
        classes = elem.get("class") or []
        if isinstance(classes, list):
            for cls in classes:
                # Match patterns like "icon-energy-a", "icon-energy-b-2", etc.
                energy_match = re.match(r"icon-energy-([a-g])", cls.lower())
                if energy_match:
                    # The title attribute may have the actual class
                    title = elem.get("title")
                    if title and isinstance(title, str):
                        result.energy_class = title.upper()
                    else:
                        result.energy_class = energy_match.group(1).upper()
                    break
        if result.energy_class:
            break

    # Photo count
    multimedia = soup.find("span", class_="item-multimedia-pictures__counter")
    if isinstance(multimedia, Tag):
        counter_text = _get_text(multimedia)
        if counter_text:
            # Parse "1/46" to get total
            match = re.search(r"/(\d+)", counter_text)
            if match:
                with contextlib.suppress(ValueError):
                    result.photo_count = int(match.group(1))

    logger.debug("Parsed listing detail: %s", result.title)
    return result


def parse_homepage_districts(html: str) -> list[ParsedDistrictInfo]:
    """Parse the homepage to extract district and concelho information.

    Args:
        html: The HTML content of the Idealista homepage.

    Returns:
        List of ParsedDistrictInfo with districts and their concelhos.
    """
    soup = BeautifulSoup(html, "lxml")
    districts: list[ParsedDistrictInfo] = []

    # Find the locations nav
    locations_nav = soup.find("nav", class_="locations-list")
    if not isinstance(locations_nav, Tag):
        logger.warning("Could not find locations-list nav on homepage")
        return districts

    # Find all district links (subregion class)
    district_links = locations_nav.find_all("a", class_="subregion")

    for district_link in district_links:
        if not isinstance(district_link, Tag):
            continue

        name = _get_text(district_link)
        href = _get_attr(district_link, "href")

        if not name or not href:
            continue

        # Extract slug from href
        slug = _extract_slug_from_href(href)

        district = ParsedDistrictInfo(
            name=name,
            slug=slug,
        )

        # Find associated municipality links (icon-elbow class following this district)
        # These are sibling elements in the DOM
        parent = district_link.parent
        if isinstance(parent, Tag):
            # Look for icon-elbow links that are siblings
            concelho_links = parent.find_all("a", class_="icon-elbow")
            for concelho_link in concelho_links:
                if not isinstance(concelho_link, Tag):
                    continue
                concelho_name = _get_text(concelho_link)
                concelho_href = _get_attr(concelho_link, "href")
                if concelho_name and concelho_href:
                    concelho_slug = _extract_slug_from_href(concelho_href)
                    district.concelhos.append(
                        ParsedConcelhoLink(
                            name=concelho_name,
                            slug=concelho_slug,
                            href=concelho_href,
                        )
                    )

        districts.append(district)

    logger.debug("Parsed %d districts from homepage", len(districts))
    return districts


def parse_concelhos_page(html: str) -> list[ParsedConcelhoLink]:
    """Parse a district's concelhos listing page.

    The concelho links can appear in multiple places:
    1. Breadcrumb dropdown (breadcrumb-dropdown-subitem-list) - primary source
    2. Municipality search section (municipality-search) - fallback
    3. General page links - last resort

    Links have the pattern: /comprar-casas/{concelho}/concelhos-freguesias
    (which shows parishes within a concelho).

    Args:
        html: The HTML content of the concelhos page
              (e.g., /comprar-casas/lisboa-distrito/concelhos-freguesias).

    Returns:
        List of ParsedConcelhoLink with all concelhos for this district.
    """
    soup = BeautifulSoup(html, "lxml")
    concelhos: list[ParsedConcelhoLink] = []
    seen_slugs: set[str] = set()

    def _add_concelho(link: Tag) -> None:
        """Add a concelho from a link element if valid."""
        href = _get_attr(link, "href")
        if not href:
            return

        name = _get_text(link)
        if not name:
            return

        # Extract slug from href patterns like:
        # /comprar-casas/cascais/concelhos-freguesias -> cascais
        # /comprar-casas/cascais/ -> cascais
        slug = _extract_concelho_slug(href)
        if not slug:
            return

        # Skip district links (they end with -distrito)
        if slug.endswith("-distrito"):
            return

        # Skip island links
        if "-ilha" in slug or "ilha-" in slug:
            return

        # Deduplicate by slug
        if slug in seen_slugs:
            return
        seen_slugs.add(slug)

        concelhos.append(
            ParsedConcelhoLink(
                name=name,
                slug=slug,
                href=href,
            )
        )

    # Strategy 1: Look in breadcrumb dropdown (real website structure)
    breadcrumb_list = soup.find("ul", class_="breadcrumb-dropdown-subitem-list")
    if isinstance(breadcrumb_list, Tag):
        links = breadcrumb_list.find_all("a", href=True)
        for link in links:
            if isinstance(link, Tag):
                _add_concelho(link)

    # Strategy 2: Look for municipality-search section (test fixtures)
    if not concelhos:
        section = soup.find("section", class_="municipality-search")
        if isinstance(section, Tag):
            links = section.find_all("a", href=True)
            for link in links:
                if isinstance(link, Tag):
                    href = _get_attr(link, "href") or ""
                    # Accept both direct concelho links and concelhos-freguesias links
                    if "/comprar-casas/" in href or "/arrendar-casas/" in href:
                        _add_concelho(link)

    # Strategy 3: Fallback - search entire page
    if not concelhos:
        all_links = soup.find_all("a", href=True)
        for link in all_links:
            if not isinstance(link, Tag):
                continue
            href = _get_attr(link, "href") or ""
            # Match pattern: /comprar-casas/{concelho}/concelhos-freguesias
            if re.match(r"/(comprar|arrendar)-casas/[^/]+/concelhos-freguesias", href):
                _add_concelho(link)

    logger.debug("Parsed %d concelhos from page", len(concelhos))
    return concelhos


def _extract_concelho_slug(href: str) -> str:
    """Extract the concelho slug from a URL path.

    Args:
        href: URL path like "/comprar-casas/cascais/concelhos-freguesias"
              or "/comprar-casas/cascais/"
              or "/comprar-casas/lisboa/azambuja/azambuja/concelhos-freguesias".

    Returns:
        The concelho slug (e.g., "cascais" or "azambuja").
    """
    if not href:
        return ""

    # Remove query string and fragment
    href = href.split("?")[0].split("#")[0]

    # Split the path
    parts = href.rstrip("/").split("/")

    # Find the part just before 'concelhos-freguesias' if present
    if "concelhos-freguesias" in parts:
        idx = parts.index("concelhos-freguesias")
        if idx > 0:
            candidate = parts[idx - 1]
            # Skip if it's the operation type
            if candidate not in ("comprar-casas", "arrendar-casas"):
                return candidate

    # Pattern: /comprar-casas/{concelho}/
    # or /comprar-casas/{distrito}/{concelho}/
    match = re.match(r"/(comprar|arrendar)-casas/([^/]+)/?$", href)
    if match:
        slug = match.group(2)
        if slug not in ("mapa", "pagina", "concelhos-freguesias"):
            return slug

    return ""
