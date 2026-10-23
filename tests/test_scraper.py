"""
Unit tests for DTU Scraper.
Uses unittest.mock for zero network requests and maximum portability across test environments.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import requests

from scraper.cache import (
    validate_pdf_content,
    PDFCacheManager,
)
from scraper.fetcher import PoliteFetcher, CircuitBreakerError
from scraper.listing import (
    parse_listing_page,
    extract_date_from_text,
    extract_archive_pages,
    PDFItem,
)


# ---------------------------------------------------------------------------
# Fixtures & Data
# ---------------------------------------------------------------------------

SAMPLE_CONFIG = {
    "base_url": "https://dtu.ac.in",
    "user_agent": "TestScraper/1.0",
    "page_delay_min": 0.001,
    "page_delay_max": 0.002,
    "pdf_delay_min": 0.001,
    "pdf_delay_max": 0.002,
    "connect_timeout": 5,
    "read_timeout": 5,
    "pdf_read_timeout": 5,
    "max_retries": 2,
    "backoff_base": 1.1,
    "retry_status_codes": [429, 500, 502, 503, 504],
    "circuit_breaker_threshold": 3,
}

SAMPLE_DTU_HTML = """
<!DOCTYPE html>
<html>
<head><title>Delhi Technological University</title></head>
<body>
  <div id="tab1">
    <ul>
      <li>
        <a href="Web/upload/notice/2026/sep/file0986.pdf">Schedule for Mid Term Examination</a>
        <span class="date">Date:23.09.2026</span>
      </li>
      <li>
        <span>Recruitment of Project Assistant</span>
        <a href="Web/upload/notice/2026/sep/file0987.pdf">Notice</a> ||
        <a href="Web/upload/notice/2026/sep/file0988.pdf">Application Form</a>
        <em>Date: 21.09.2026</em>
      </li>
    </ul>
  </div>
  <div id="tab2">
    <ul>
      <li>
        <a href="Web/Jobs/2026/aug/job012.pdf">Engagement of Assistant Professor on contract</a>
        <span>Date:15.08.2026</span>
      </li>
    </ul>
  </div>
  <div id="tab3">
    <ul>
      <li>
        <a href="Web/upload/tenders/tender88.pdf">Tender Notice for Lab Equipment</a>
        <span>Date:10.08.2026</span>
      </li>
    </ul>
  </div>
</body>
</html>
"""

SAMPLE_ARCHIVE_HTML = """
<html>
<body>
  <div class="archive-list">
    <a href="Web/Archive/file1.pdf">Archive Notice 1</a>
    <a href="Web/Archive/file2.pdf">Archive Notice 2</a>
  </div>
  <div class="pagination">
    <a href="archive-notices.php?page=1">1</a>
    <a href="archive-notices.php?page=2">2</a>
    <a href="archive-notices.php?page=3">3</a>
  </div>
</body>
</html>
"""


def _make_mock_response(status_code: int = 200, text: str = "", content: bytes = b"", headers: dict = None):
    resp = requests.Response()
    resp.status_code = status_code
    if content:
        resp._content = content
    elif text:
        resp._content = text.encode("utf-8")
    else:
        resp._content = b""
    if headers:
        resp.headers.update(headers)
    return resp


# ---------------------------------------------------------------------------
# 1. Robots.txt parsing & compliance tests
# ---------------------------------------------------------------------------

def test_robots_txt_parsing_and_delay():
    robots_content = """
User-agent: *
Disallow: /admin/
Disallow: /private/
Crawl-delay: 4
"""
    fetcher = PoliteFetcher(SAMPLE_CONFIG)
    mock_resp = _make_mock_response(status_code=200, text=robots_content)

    with patch.object(fetcher.session, "get", return_value=mock_resp):
        fetcher.load_robots_txt("https://dtu.ac.in")

    assert fetcher.can_fetch("https://dtu.ac.in/Web/upload/notice/file.pdf") is True
    assert fetcher.can_fetch("https://dtu.ac.in/admin/dashboard") is False
    assert fetcher.crawl_delay_from_robots == 4.0


def test_robots_disallow_raises_permission_error():
    robots_content = """
User-agent: *
Disallow: /restricted/
"""
    fetcher = PoliteFetcher(SAMPLE_CONFIG)
    mock_resp = _make_mock_response(status_code=200, text=robots_content)

    with patch.object(fetcher.session, "get", return_value=mock_resp):
        fetcher.load_robots_txt("https://dtu.ac.in")

    with pytest.raises(PermissionError):
        fetcher.get("https://dtu.ac.in/restricted/secret.pdf")


# ---------------------------------------------------------------------------
# 2. HTML parsing / link extraction tests
# ---------------------------------------------------------------------------

def test_parse_listing_page_notices():
    items = parse_listing_page(
        html=SAMPLE_DTU_HTML,
        page_url="https://dtu.ac.in",
        section="notices",
        container_selector="#tab1"
    )

    assert len(items) == 3
    # Check item 1
    assert items[0].url == "https://dtu.ac.in/Web/upload/notice/2026/sep/file0986.pdf"
    assert items[0].title == "Schedule for Mid Term Examination"
    assert items[0].publication_date == "23.09.2026"
    assert items[0].section == "notices"

    # Check sublink items with date extraction from parent
    assert items[1].url == "https://dtu.ac.in/Web/upload/notice/2026/sep/file0987.pdf"
    assert items[1].publication_date == "21.09.2026"


def test_parse_listing_page_jobs_and_tenders():
    job_items = parse_listing_page(
        html=SAMPLE_DTU_HTML,
        page_url="https://dtu.ac.in",
        section="jobs",
        container_selector="#tab2"
    )
    assert len(job_items) == 1
    assert job_items[0].url == "https://dtu.ac.in/Web/Jobs/2026/aug/job012.pdf"
    assert job_items[0].publication_date == "15.08.2026"

    tender_items = parse_listing_page(
        html=SAMPLE_DTU_HTML,
        page_url="https://dtu.ac.in",
        section="tenders",
        container_selector="#tab3"
    )
    assert len(tender_items) == 1
    assert tender_items[0].url == "https://dtu.ac.in/Web/upload/tenders/tender88.pdf"
    assert tender_items[0].publication_date == "10.08.2026"


def test_extract_archive_pages():
    pages = extract_archive_pages(SAMPLE_ARCHIVE_HTML, "https://dtu.ac.in/archive-notices.php", max_pages=3)
    assert len(pages) == 2
    assert "https://dtu.ac.in/archive-notices.php?page=2" in pages


def test_extract_date_variants():
    assert extract_date_from_text("Date: 23.09.2026") == "23.09.2026"
    assert extract_date_from_text("Published on Date:12-05-2025") == "12-05-2025"
    assert extract_date_from_text("No date here") is None


# ---------------------------------------------------------------------------
# 3. PDF validation tests
# ---------------------------------------------------------------------------

def test_validate_valid_pdf():
    valid_pdf_bytes = b"%PDF-1.5 \x00\x01\x02 testing content %%EOF"
    valid, reason = validate_pdf_content(200, {"Content-Type": "application/pdf"}, valid_pdf_bytes)
    assert valid is True
    assert reason is None


def test_validate_empty_content():
    valid, reason = validate_pdf_content(200, {"Content-Type": "application/pdf"}, b"")
    assert valid is False
    assert "Empty content" in reason


def test_validate_html_error_page_as_pdf():
    html_bytes = b"<!DOCTYPE html><html><head><title>404 Not Found</title></head><body>Error</body></html>"
    valid, reason = validate_pdf_content(200, {"Content-Type": "text/html"}, html_bytes)
    assert valid is False
    assert "HTML document instead of PDF" in reason


def test_validate_missing_magic_bytes():
    junk_bytes = b"Random binary garbage without pdf signature"
    valid, reason = validate_pdf_content(200, {"Content-Type": "application/pdf"}, junk_bytes)
    assert valid is False
    assert "Missing %PDF-" in reason


def test_validate_exceeding_max_size():
    valid_pdf_bytes = b"%PDF-1.4 " + b"X" * 1000
    valid, reason = validate_pdf_content(200, {"Content-Type": "application/pdf"}, valid_pdf_bytes, max_size_bytes=500)
    assert valid is False
    assert "exceeds maximum allowed" in reason


def test_validate_non_200_status():
    valid, reason = validate_pdf_content(404, {}, b"%PDF-1.4 content")
    assert valid is False
    assert "404 != 200" in reason


# ---------------------------------------------------------------------------
# 4. SHA-256 computation and deduplication logic
# ---------------------------------------------------------------------------

def test_sha256_computation_and_file_caching(tmp_path):
    cache_manager = PDFCacheManager(str(tmp_path))
    content = b"%PDF-1.4 Sample content for hashing"
    sha = cache_manager.calculate_sha256(content)
    assert len(sha) == 64

    # Mock fetcher
    mock_fetcher = MagicMock()
    mock_resp = _make_mock_response(status_code=200, content=content, headers={"Content-Type": "application/pdf"})
    mock_fetcher.get.return_value = mock_resp

    item = PDFItem(
        url="https://dtu.ac.in/notice1.pdf",
        source_page="https://dtu.ac.in",
        section="notices",
        title="Notice 1"
    )

    record = cache_manager.process_and_cache(mock_fetcher, item)
    assert record is not None
    assert record["sha256"] == sha
    assert (tmp_path / f"{sha}.pdf").exists()

    # Re-running with same URL should skip (idempotence)
    second_record = cache_manager.process_and_cache(mock_fetcher, item)
    assert second_record is None
    # Verify fetcher was only called once
    assert mock_fetcher.get.call_count == 1


# ---------------------------------------------------------------------------
# 5. Manifest read / write / append tests
# ---------------------------------------------------------------------------

def test_manifest_read_write_append(tmp_path):
    manifest_path = tmp_path / "manifest.jsonl"
    cache_manager = PDFCacheManager(str(tmp_path), str(manifest_path))

    record1 = {
        "sha256": "abc123hash",
        "original_url": "https://dtu.ac.in/doc1.pdf",
        "source_page": "https://dtu.ac.in",
        "section": "notices",
        "title": "Doc 1",
        "publication_date": "2026-09-01",
        "download_timestamp": "2026-10-23T10:00:00Z",
        "file_size_bytes": 1024,
        "mime_type": "application/pdf",
        "http_status": 200
    }
    cache_manager.append_manifest_record(record1)

    assert manifest_path.exists()
    lines = manifest_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    loaded = json.loads(lines[0])
    assert loaded["sha256"] == "abc123hash"
    assert loaded["original_url"] == "https://dtu.ac.in/doc1.pdf"

    # Create dummy pdf file so cache reload recognizes it
    (tmp_path / "abc123hash.pdf").write_bytes(b"%PDF-1.4 dummy")

    # New cache manager instance should reload existing records
    new_manager = PDFCacheManager(str(tmp_path), str(manifest_path))
    assert new_manager.is_cached("https://dtu.ac.in/doc1.pdf")
    assert "abc123hash" in new_manager.seen_hashes


# ---------------------------------------------------------------------------
# 6. Circuit breaker tests
# ---------------------------------------------------------------------------

def test_circuit_breaker_aborts_after_consecutive_failures():
    cfg = dict(SAMPLE_CONFIG)
    cfg["circuit_breaker_threshold"] = 3
    cfg["max_retries"] = 0  # No retry loop to trigger failures directly

    fetcher = PoliteFetcher(cfg)
    mock_resp = _make_mock_response(status_code=500)

    with patch.object(fetcher.session, "get", return_value=mock_resp):
        fetcher.get("https://dtu.ac.in/fail1")
        fetcher.get("https://dtu.ac.in/fail2")

        # Third failure trips the circuit breaker
        with pytest.raises(CircuitBreakerError):
            fetcher.get("https://dtu.ac.in/fail3")


# ---------------------------------------------------------------------------
# 7. Exponential backoff on 429 / 503 tests
# ---------------------------------------------------------------------------

@patch("time.sleep")
def test_backoff_on_429_retry_success(mock_sleep):
    cfg = dict(SAMPLE_CONFIG)
    cfg["max_retries"] = 2
    fetcher = PoliteFetcher(cfg)

    url = "https://dtu.ac.in/rate-limited.pdf"
    resp_429 = _make_mock_response(status_code=429)
    resp_200 = _make_mock_response(status_code=200, content=b"%PDF-1.4 success", headers={"Content-Type": "application/pdf"})

    with patch.object(fetcher.session, "get", side_effect=[resp_429, resp_200]):
        resp = fetcher.get(url, is_pdf=True)

    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF-")
    assert mock_sleep.called


# ---------------------------------------------------------------------------
# 8. Dry run mode test
# ---------------------------------------------------------------------------

def test_dry_run_mode(tmp_path):
    cache_manager = PDFCacheManager(str(tmp_path))
    mock_fetcher = MagicMock()

    item = PDFItem(
        url="https://dtu.ac.in/dry_run_notice.pdf",
        source_page="https://dtu.ac.in",
        section="notices",
        title="Dry Run Notice"
    )

    record = cache_manager.process_and_cache(mock_fetcher, item, dry_run=True)
    assert record is not None
    assert record["sha256"] == "DRY_RUN_HASH"
    # No HTTP request should have been made
    assert mock_fetcher.get.call_count == 0
    # No file written on disk
    assert len(list(tmp_path.glob("*.pdf"))) == 0
