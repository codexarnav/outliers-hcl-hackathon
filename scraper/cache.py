"""
Cache and Storage module for DTU Scraper.
Handles downloading, validating, hashing (SHA-256), storing PDFs, and maintaining manifest.jsonl.
"""

import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Set

import requests

from scraper.fetcher import PoliteFetcher
from scraper.listing import PDFItem

logger = logging.getLogger(__name__)

# Maximum file size: 50MB default
DEFAULT_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


class PDFValidationError(Exception):
    """Raised when downloaded content fails PDF validation."""
    pass


def validate_pdf_content(
    status_code: int,
    headers: Dict[str, str],
    content: bytes,
    max_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES
) -> Tuple[bool, Optional[str]]:
    """Validate that the downloaded content is a legitimate PDF file.

    Returns:
        (is_valid, failure_reason)
    """
    if status_code != 200:
        return False, f"HTTP status {status_code} != 200"

    size = len(content)
    if size == 0:
        return False, "Empty content (0 bytes)"

    if size > max_size_bytes:
        return False, f"File size {size} bytes exceeds maximum allowed {max_size_bytes} bytes"

    # Check magic bytes: PDF specification requires %PDF- at the start
    # Some servers may prepend a small UTF-8 BOM or whitespace, so check first 1024 bytes
    prefix = content[:1024]
    if b"%PDF-" not in prefix:
        # Check if it looks like an HTML error page or redirect
        if b"<html" in prefix.lower() or b"<!doctype html" in prefix.lower():
            return False, "Content is HTML document instead of PDF (likely error or redirect page)"
        return False, "Missing %PDF- magic bytes signature"

    return True, None


class PDFCacheManager:
    """Manages the raw file cache and the manifest.jsonl metadata index."""

    def __init__(self, cache_dir: str, manifest_path: Optional[str] = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if manifest_path:
            self.manifest_file = Path(manifest_path)
            self.manifest_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.manifest_file = self.cache_dir / "manifest.jsonl"

        # In-memory index of processed records for fast idempotence checks
        self.seen_urls: Set[str] = set()
        self.seen_hashes: Set[str] = set()
        self._load_existing_manifest()

    def _load_existing_manifest(self):
        """Read existing manifest.jsonl if present to populate seen_urls and seen_hashes."""
        if not self.manifest_file.exists():
            return

        count = 0
        try:
            with open(self.manifest_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        sha = record.get("sha256")
                        url = record.get("original_url")
                        if sha:
                            # Verify file still exists on disk
                            pdf_path = self.cache_dir / f"{sha}.pdf"
                            if pdf_path.exists():
                                self.seen_hashes.add(sha)
                        if url:
                            self.seen_urls.add(url)
                        count += 1
                    except json.JSONDecodeError:
                        continue
            logger.info("Loaded %d manifest records from %s", count, self.manifest_file)
        except Exception as e:
            logger.warning("Error reading manifest file %s: %s", self.manifest_file, e)

    def is_cached(self, url: str) -> bool:
        """Check if URL has already been downloaded and cached."""
        return url in self.seen_urls

    def calculate_sha256(self, data: bytes) -> str:
        """Compute hex-encoded SHA-256 digest of data bytes."""
        hasher = hashlib.sha256()
        hasher.update(data)
        return hasher.hexdigest()

    def append_manifest_record(self, record: Dict[str, Any]):
        """Append a JSON record to manifest.jsonl."""
        with open(self.manifest_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        if "original_url" in record:
            self.seen_urls.add(record["original_url"])
        if "sha256" in record:
            self.seen_hashes.add(record["sha256"])

    def process_and_cache(
        self,
        fetcher: PoliteFetcher,
        item: PDFItem,
        dry_run: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Fetch, validate, hash, and store a PDF document.

        Returns the manifest record dictionary, or None if skipped/invalid.
        """
        # Idempotence check by URL
        if self.is_cached(item.url):
            logger.info("Skipping already cached PDF: %s", item.url)
            return None

        if dry_run:
            logger.info("[DRY-RUN] Would download: %s ('%s')", item.url, item.title)
            return {
                "sha256": "DRY_RUN_HASH",
                "original_url": item.url,
                "source_page": item.source_page,
                "section": item.section,
                "title": item.title,
                "publication_date": item.publication_date,
                "download_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "file_size_bytes": 0,
                "mime_type": "application/pdf",
                "http_status": 200
            }

        try:
            resp = fetcher.get(item.url, is_pdf=True)
        except Exception as e:
            logger.error("Failed to download PDF from %s: %s", item.url, e)
            return None

        content = resp.content
        mime_type = resp.headers.get("Content-Type", "application/pdf").split(";")[0].strip()

        # Validation
        is_valid, failure_reason = validate_pdf_content(resp.status_code, dict(resp.headers), content)
        if not is_valid:
            logger.warning("Validation failed for %s: %s", item.url, failure_reason)
            return None

        # SHA-256 computation
        sha256_hash = self.calculate_sha256(content)
        file_path = self.cache_dir / f"{sha256_hash}.pdf"

        # Save to disk if not already present
        if not file_path.exists():
            with open(file_path, "wb") as f:
                f.write(content)
            logger.info("Saved %s (%d bytes) to %s", item.url, len(content), file_path.name)
        else:
            logger.info("File with hash %s already exists on disk (duplicate content)", sha256_hash)

        # Manifest entry
        record = {
            "sha256": sha256_hash,
            "original_url": item.url,
            "source_page": item.source_page,
            "section": item.section,
            "title": item.title,
            "publication_date": item.publication_date,
            "download_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "file_size_bytes": len(content),
            "mime_type": mime_type,
            "http_status": resp.status_code
        }

        self.append_manifest_record(record)
        return record
