"""
Listing parser module for DTU Scraper.
Extracts PDF links and metadata (title, publication date, section) from listing pages and tabs.
"""

import logging
import re
import urllib.parse
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DATE_REGEX = re.compile(r'Date\s*:\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})', re.IGNORECASE)
FALLBACK_DATE_REGEX = re.compile(r'\b(\d{1,2}[./-]\d{1,2}[./-]\d{4})\b')


@dataclass
class PDFItem:
    url: str
    source_page: str
    section: str
    title: str
    publication_date: Optional[str] = None


def extract_date_from_text(text: str) -> Optional[str]:
    """Extract date string in DD.MM.YYYY (or similar) from surrounding text."""
    if not text:
        return None
    match = DATE_REGEX.search(text)
    if match:
        return match.group(1).strip()
    fallback_match = FALLBACK_DATE_REGEX.search(text)
    if fallback_match:
        return fallback_match.group(1).strip()
    return None


def is_pdf_url(href: str, pdf_patterns: Optional[List[str]] = None) -> bool:
    """Check if href points to a PDF file."""
    if not href:
        return False
    clean_href = href.lower().split('?')[0].split('#')[0]
    if clean_href.endswith('.pdf'):
        return True
    if pdf_patterns:
        return any(pattern.lower() in href.lower() for pattern in pdf_patterns)
    return '.pdf' in href.lower()


def parse_listing_page(
    html: str,
    page_url: str,
    section: str,
    container_selector: Optional[str] = None,
    pdf_patterns: Optional[List[str]] = None
) -> List[PDFItem]:
    """Parse HTML content to find all PDF links and their metadata for a given section."""
    soup = BeautifulSoup(html, "html.parser")

    container = None
    if container_selector:
        container = soup.select_one(container_selector)
        if not container:
            logger.warning(
                "Container selector '%s' not found on %s. Searching full document.",
                container_selector, page_url
            )
            container = soup
    else:
        container = soup

    items: List[PDFItem] = []
    seen_urls = set()

    # Look for all <a> tags inside container
    for a_tag in container.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not is_pdf_url(href, pdf_patterns):
            continue

        resolved_url = urllib.parse.urljoin(page_url, href)

        # Skip duplicate links within the same page extraction
        if resolved_url in seen_urls:
            continue
        seen_urls.add(resolved_url)

        # Title extraction:
        # 1. Link text
        title = a_tag.get_text(strip=True)
        # 2. If short (e.g. "Notice", "Poster", "Download", "||"), inspect parent
        parent = a_tag.find_parent(["li", "p", "div", "tr"])
        parent_text = parent.get_text(" ", strip=True) if parent else ""

        if len(title) < 4 or title.lower() in ["click here", "download", "pdf", "notice", "view", "link"]:
            if parent_text:
                # Use clean summary of parent text up to 150 chars
                title = parent_text.split("Date:")[0].strip() or title

        # Publication date extraction
        # Try parent text first, then surrounding context
        pub_date = extract_date_from_text(parent_text) if parent_text else None
        if not pub_date:
            pub_date = extract_date_from_text(title)

        items.append(
            PDFItem(
                url=resolved_url,
                source_page=page_url,
                section=section,
                title=title if title else "Untitled PDF",
                publication_date=pub_date
            )
        )

    logger.info("Found %d PDF links for section '%s' on %s", len(items), section, page_url)
    return items


def extract_archive_pages(html: str, current_url: str, max_pages: int) -> List[str]:
    """Extract pagination or archive page URLs from an archive listing page."""
    if max_pages <= 1:
        return []

    soup = BeautifulSoup(html, "html.parser")
    page_urls = []
    seen = {current_url}

    # Find pagination links: look for pagination containers or hrefs with page/offset
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if any(param in href.lower() for param in ["page=", "offset=", "p="]) or (a.get_text(strip=True).isdigit() and len(a.get_text(strip=True)) <= 2):
            full_url = urllib.parse.urljoin(current_url, href)
            if full_url not in seen:
                seen.add(full_url)
                page_urls.append(full_url)
                if len(page_urls) >= max_pages - 1:
                    break

    return page_urls
