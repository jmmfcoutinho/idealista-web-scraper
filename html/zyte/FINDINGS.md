# Idealista Scraping Findings - Zyte API

## Overview

This document describes the HTML structure and CSS selectors needed to scrape Idealista.pt using Zyte API with browser rendering.

### Zyte API Configuration

- **Required**: `browserHtml: true` (not httpResponseBody)
- **Actions**: Use `waitForSelector` with timeout ≤15 seconds for dynamic content
- **Retries**: Ban responses (HTTP 520) are normal - retry with exponential backoff

---

## 1. Homepage (`https://www.idealista.pt/`)

### Wait Selector
```
nav.locations-list
```

### Data Available

#### Regions (Districts)
```python
# Parent container
soup.find("nav", class_="locations-list")

# Region titles (Açores, Alentejo, Algarve, etc.)
soup.find_all("h3", class_="region-title")
# Text: region.get_text(strip=True)

# Subregions (districts) with links to concelhos
soup.find_all("a", class_="subregion")
# href: /comprar-casas/beja-distrito/concelhos-freguesias
# text: district name

# Municipalities (popular ones only)
soup.find_all("a", class_="icon-elbow")
# href: /comprar-casas/cascais/
# text: municipality name
```

---

## 2. District Concelhos Page (`/comprar-casas/{distrito}-distrito/concelhos-freguesias`)

### Wait Selector
```
section.municipality-search
```

### Data Available

#### Concelho Links
```python
# All concelho links for this district
soup.find_all("a", href=lambda x: x and "/comprar-casas/" in x)
# href: /comprar-casas/cascais/concelhos-freguesias
# text: concelho name
```

---

## 3. Search Results Page (`/comprar-casas/{concelho}/` or `/arrendar-casas/{concelho}/`)

### Wait Selector
```
article.item
```

### Data Available

#### Total Count
```python
h1 = soup.find("h1", id="h1-container")
# Text: "4.423 casas e apartamentos em Cascais, Lisboa"
# Parse the number: re.search(r'([\d.]+)', h1_text).group(1).replace('.', '')
```

#### Listing Cards
```python
# All listing articles (30 per page)
articles = soup.find_all("article", class_="item")

# Filter out ads
real_listings = [a for a in articles if a.get("data-element-id")]
```

#### Per-Listing Data
```python
article = soup.find("article", class_="item")

# Listing ID
listing_id = article.get("data-element-id")
# Example: "34609275"

# Title and URL
link = article.find("a", class_="item-link")
title = link.get_text(strip=True)
url = link.get("href")  # e.g., "/imovel/34609275/"

# Price
price_span = article.find("span", class_="item-price")
price = price_span.get_text(strip=True)  # "36.500.000€"

# Details (rooms, area)
details = article.find_all("span", class_="item-detail")
# Example: ["T8", "2.500 m² área bruta"]

# Description snippet
desc = article.find("p", class_="ellipsis")
description = desc.get_text(strip=True) if desc else None

# Agency info
agency_pic = article.find("picture", class_="logo-branding")
if agency_pic:
    agency_img = agency_pic.find("img")
    agency_name = agency_img.get("alt") if agency_img else None
    agency_link = agency_pic.find("a")
    agency_url = agency_link.get("href") if agency_link else None

# Main image
img = article.find("img", alt="Primeira foto do imóvel")
image_url = img.get("src") if img else None
```

#### Pagination
```python
pagination = soup.find("div", class_="pagination")

# Current page
current = pagination.find("li", class_="selected")
current_page = int(current.find("span").get_text(strip=True))

# Next page link
next_li = pagination.find("li", class_="next")
if next_li:
    next_link = next_li.find("a")
    next_url = next_link.get("href")  # "/comprar-casas/cascais/pagina-2?ordem=precos-desc"

# All page links
page_links = pagination.find_all("a")
# Extract page numbers from href with regex: /pagina-(\d+)
```

---

## 4. Listing Detail Page (`/imovel/{listing_id}/`)

### Wait Selector
```
section.detail-info
```

### Data Available

```python
# Title
h1 = soup.find("h1")
title = h1.get_text(strip=True)  # "Apartamento t3 à venda na Rua da Junqueira"

# Price
price_span = soup.find("span", class_="info-data-price")
price = price_span.get_text(strip=True)  # "2.700.000€"

# Location
location = soup.find("span", class_="main-info__title-minor")
location_text = location.get_text(strip=True)  # "Junqueira, Alcântara"

# Features (area, rooms, floor, garage)
features_div = soup.find("div", class_="info-features")
features = [span.get_text(strip=True) for span in features_div.find_all("span")]
# Example: ["254 m² área bruta", "T3", "1º andar com elevador", "Garagem incluída"]

# Tags (luxury, etc.)
tags_div = soup.find("div", class_="detail-info-tags")
tags = [tag.get_text(strip=True) for tag in tags_div.find_all("span", class_="tag")]

# Full description
comment_div = soup.find("div", class_="comment")
if comment_div:
    p = comment_div.find("p")
    description = p.get_text(strip=True) if p else None

# Photo count
multimedia = soup.find("span", class_="item-multimedia-pictures__counter")
# Contains "1/46" - parse to get total photos
```

---

## URL Patterns

### Search URLs
- Buy: `/comprar-casas/{location}/`
- Rent: `/arrendar-casas/{location}/`
- With sorting: `?ordem=precos-desc` or `?ordem=precos-asc`
- Pagination: `/pagina-{n}` in the path

### Location URL Slugs
- District: `{district}-distrito` (e.g., `lisboa-distrito`)
- Concelho: `{concelho}` (e.g., `cascais`)
- Freguesia: `{concelho}/{freguesia}` (e.g., `cascais/cascais-e-estoril`)

### Listing Detail
- `/imovel/{listing_id}/`

### Concelhos listing
- `/comprar-casas/{distrito}-distrito/concelhos-freguesias`

---

## Notes

1. **30 listings per page** on search results
2. **Pagination** available via div.pagination
3. **Ads** are also `article.item` but lack `data-element-id`
4. **JavaScript required** - must use browserHtml with wait actions
5. **Rate limiting** - Zyte handles this automatically, but expect some 429/520 responses
