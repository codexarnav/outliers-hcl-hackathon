# DTU Polite PDF Scraper (Stage 1 Data Pipeline)

A robust, polite, and compliant web scraper built for Delhi Technological University ([dtu.ac.in](https://dtu.ac.in)). This tool downloads PDF documents exclusively from the **Notices**, **Jobs**, and **Tenders** sections, validates them, hashes their content using SHA-256, stores them in a flat-file raw cache, and indexes them in a streaming `manifest.jsonl`.

---

## Architecture & Design Principles

```
dtu-scraper/
├── scraper/
│   ├── __init__.py
│   ├── config.yaml           # All tunables (delays, timeouts, retries, URLs)
│   ├── fetcher.py            # PoliteFetcher: robots.txt, rate limiter, backoff, circuit breaker
│   ├── listing.py            # HTML parser: extracts PDF links, titles, dates from tabs & archives
│   ├── cache.py              # PDFCacheManager: validation (%PDF- bytes), SHA-256 hashing, JSONL manifest
│   ├── selenium_fallback.py  # Isolated fallback module for JS-rendered listings
│   └── run.py                # CLI entry point
├── tests/
│   ├── __init__.py
│   └── test_scraper.py       # 17 pytest unit tests (100% mocked, zero network during tests)
├── data/
│   ├── raw/                  # Flat-file cache named by <sha256>.pdf
│   └── manifest.jsonl        # JSON Lines metadata index
├── logs/                     # Scraper execution logs
├── requirements.txt
└── README.md
```

### 1. Politeness & Compliance
- **robots.txt Adherence**: Dynamically fetches and parses DTU's `robots.txt` upon startup using `urllib.robotparser.RobotFileParser`. Honors any `Disallow` rules and checks for `Crawl-delay`.
- **Sequential Requests**: Enforces strictly linear downloads (one request at a time). No asynchronous thread pools or parallel bursts that could strain university servers.
- **Random Jitter**: Injects uniform random jitter (`0.5s - 1.5s`) into polite delays (defaulting to 2.0s - 3.0s between requests).
- **Custom User-Agent**: Identifies the scraper clearly (`DTU-Hackathon-Scraper/1.0 (student project)`).
- **Exponential Backoff**: Automatically backs off exponentially on HTTP `429`, `500`, `502`, `503`, and `504` up to 3 retries.
- **Circuit Breaker**: If 5 consecutive requests fail, the circuit breaker automatically trips and terminates execution to prevent server distress.

### 2. Validation & Deduplication
- **Magic Bytes Validation**: Verifies that every downloaded document starts with `%PDF-` within the first 1024 bytes and rejects HTML error pages or redirects.
- **Content-Length & Sanity Checks**: Ensures non-empty files within configurable size bounds (default < 50MB).
- **Content-Addressable Storage**: Files are saved on disk as `<cache_dir>/<sha256>.pdf`.
- **Idempotence**: Existing manifest records and on-disk files are loaded into memory. Already-cached files are skipped immediately without re-downloading.

### 3. Manifest Record (`manifest.jsonl`)
Every valid downloaded PDF is recorded in `data/manifest.jsonl` with full traceability:
```json
{
  "sha256": "8c8af2274496a5c8fd9a8cf76cd2c35b48275417073a8ce4228dc0a066254bde",
  "original_url": "https://dtu.ac.in/Web/upload/events/aug/file0807.pdf",
  "source_page": "https://dtu.ac.in",
  "section": "notices",
  "title": "Notice",
  "publication_date": "17.09.2026",
  "download_timestamp": "2026-10-23T08:35:51.244656+00:00",
  "file_size_bytes": 99355,
  "mime_type": "application/pdf",
  "http_status": 200
}
```

---

## Setup & Installation

### Requirements
- Python 3.11+
- Virtual environment (recommended)

### Installation
```bash
git clone <repo_url>
cd hcl-hackathon
pip install -r requirements.txt
```

---

## How to Run

### Command Line Interface Options
```text
python -m scraper.run [OPTIONS]

Options:
  --section [notices|tenders|jobs|all]   Section to scrape (default: all)
  --limit INT                            Maximum PDFs to download (0 = unlimited, default: 0)
  --max-pages INT                        Maximum listing/archive pages to crawl per section (default: 5)
  --cache-dir PATH                       Directory to store cached PDFs (default: data/raw)
  --dry-run                              Simulate crawl and log discovered links without downloading files
  --verbose                              Enable DEBUG level logs
  --config PATH                          Path to custom configuration YAML (default: scraper/config.yaml)
```

### Usage Examples

1. **Download up to 30 PDFs per section:**
   ```bash
   python -m scraper.run --limit-per-section 30
   ```

2. **Dry run (Inspect links without downloading files):**
   ```bash
   python -m scraper.run --dry-run --section notices --limit 5
   ```

3. **Crawl all sections (Notices, Jobs, Tenders) with verbose logging:**
   ```bash
   python -m scraper.run --section all --verbose
   ```

4. **Re-running for idempotence:**
   ```bash
   python -m scraper.run --limit-per-section 30
   ```
   *(Previously downloaded files are recognized in the manifest and skipped immediately!)*

---

## Stage 2: Metadata Extraction & Source Register Generation

The metadata drafting pipeline applies regex patterns, heuristic rules, and `pypdf` text extraction to generate a clean, structured `source_register.csv`.

### Extracted Metadata Fields
- `doc_id`: Content-addressable SHA-256 hash.
- `section`: notices / jobs / tenders.
- `category`: Document classification (*Tender / Procurement, Job / Recruitment, Examination / Date Sheet, Result, Circular, Office Order, General Notice*).
- `title`: Extracted title.
- `file_number`: Reference / official file number (e.g. `DTU/SO/Notice/...`, `DTU/Rectt/...`, or GeM bid number `GEM/2026/B/...`).
- `published_date`: Publication date.
- `deadline_date`: Submission/application closing deadline (for tenders and jobs).
- `issuing_authority`: Issuing university department or office.
- `total_pages`: Total page count.
- `needs_review`: Boolean flag indicating if human verification is recommended (e.g., scanned image requiring OCR, or missing key fields).
- `review_notes`: Detailed reasons if manual review was flagged.

### Running the Source Register Generator
```bash
python generate_source_register.py [OPTIONS]

Options:
  --manifest PATH   Path to manifest.jsonl (default: data/manifest.jsonl)
  --raw-dir PATH    Path to raw cached PDF directory (default: data/raw)
  --output PATH     Output CSV path (default: data/source_register.csv)
  --limit INT       Limit number of documents to process (0 = all, default: 0)
  --verbose         Enable debug logging
```

---

## Running Unit Tests

The test suite contains 24 comprehensive unit tests with **zero live network calls** using `unittest.mock` and `pytest`:
- Robots.txt parsing & delay compliance
- Tab parsing & metadata extraction for Notices, Jobs, and Tenders
- Date parsing variants & deadline extraction
- PDF validation (valid PDF, empty file, HTML error page, truncated file, size limits)
- SHA-256 calculation & file deduplication
- Manifest read / write / reload persistence
- Circuit breaker trip behavior & exponential backoff on HTTP 429/503
- Regex file number & GeM bid extraction
- Department / Authority detection rules
- Document classification rules

Run tests with:
```bash
python -m pytest -v
```

