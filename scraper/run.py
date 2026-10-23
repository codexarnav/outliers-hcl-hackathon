"""
CLI entry point for DTU PDF Scraper.
Runs the polite scraping and caching pipeline for Notices, Jobs, and Tenders.
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

import yaml

from scraper.cache import PDFCacheManager
from scraper.fetcher import PoliteFetcher, CircuitBreakerError
from scraper.listing import parse_listing_page, extract_archive_pages, PDFItem
from scraper.selenium_fallback import SeleniumFallbackFetcher, SeleniumFallbackUnavailable


def setup_logging(verbose: bool, log_dir: str):
    """Configure stdout and file logging."""
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    handlers = [logging.StreamHandler(sys.stdout)]

    try:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path / "scraper.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)
    except Exception as e:
        print(f"Warning: Could not create file log handler in {log_dir}: {e}")

    logging.basicConfig(level=log_level, format=log_format, handlers=handlers, force=True)


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration dictionary from YAML file."""
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def scrape_section(
    section_name: str,
    section_cfg: Dict[str, Any],
    fetcher: PoliteFetcher,
    cache_manager: PDFCacheManager,
    max_pages: int,
    limit: int,
    limit_per_section: int,
    dry_run: bool,
    pdf_patterns: List[str],
    current_download_count: int
) -> int:
    """Crawl a specific section (e.g. notices, jobs, tenders) and download candidate PDFs.

    Returns the updated count of downloaded PDFs.
    """
    logger = logging.getLogger("scraper")
    logger.info("=" * 60)
    logger.info("Starting crawl for section: %s", section_name.upper())
    logger.info("=" * 60)

    url = section_cfg.get("url", "https://dtu.ac.in")
    container_selector = section_cfg.get("container_selector")
    archive_url = section_cfg.get("archive_url")

    # Step 1: Fetch listing page via requests
    logger.info("Fetching primary listing page: %s", url)
    html = ""
    try:
        resp = fetcher.get(url, is_pdf=False)
        html = resp.text
    except Exception as e:
        logger.error("Failed to fetch %s via requests: %s", url, e)

    # Step 2: Parse items
    items = parse_listing_page(
        html=html,
        page_url=url,
        section=section_name,
        container_selector=container_selector,
        pdf_patterns=pdf_patterns
    )

    # Fallback to Selenium if requests produced 0 items
    if not items:
        logger.warning(
            "Zero PDF items found with requests for section '%s'. Attempting Selenium fallback...",
            section_name
        )
        try:
            selenium_fetcher = SeleniumFallbackFetcher(user_agent=fetcher.user_agent)
            html = selenium_fetcher.fetch_rendered_html(url, wait_selector=container_selector)
            items = parse_listing_page(
                html=html,
                page_url=url,
                section=section_name,
                container_selector=container_selector,
                pdf_patterns=pdf_patterns
            )
            logger.info("Selenium fallback extracted %d items for '%s'.", len(items), section_name)
        except Exception as e:
            logger.error("Selenium fallback was unable to extract items: %s", e)

    # Step 3: Archive crawl if max_pages > 1 and archive URL exists
    pages_crawled = 1
    if max_pages > 1 and archive_url:
        logger.info("Crawling archive page for section '%s': %s", section_name, archive_url)
        try:
            arch_resp = fetcher.get(archive_url, is_pdf=False)
            arch_items = parse_listing_page(
                html=arch_resp.text,
                page_url=archive_url,
                section=section_name,
                container_selector=None,
                pdf_patterns=pdf_patterns
            )
            items.extend(arch_items)
            pages_crawled += 1

            # Extract further pagination if needed
            if pages_crawled < max_pages:
                subpages = extract_archive_pages(
                    arch_resp.text,
                    archive_url,
                    max_pages=max_pages - pages_crawled + 1
                )
                for subpage in subpages:
                    logger.info("Crawling subpage: %s", subpage)
                    sub_resp = fetcher.get(subpage, is_pdf=False)
                    sub_items = parse_listing_page(
                        html=sub_resp.text,
                        page_url=subpage,
                        section=section_name,
                        container_selector=None,
                        pdf_patterns=pdf_patterns
                    )
                    items.extend(sub_items)
                    pages_crawled += 1
                    if pages_crawled >= max_pages:
                        break
        except Exception as e:
            logger.warning("Error fetching archive pages for %s: %s", section_name, e)

    # Deduplicate candidate items by URL
    unique_items: List[PDFItem] = []
    seen = set()
    for item in items:
        if item.url not in seen:
            seen.add(item.url)
            unique_items.append(item)

    logger.info("Total unique PDF items discovered for %s: %d", section_name, len(unique_items))

    # Step 4: Process and download PDFs sequentially
    download_count = current_download_count
    section_download_count = 0
    for item in unique_items:
        if limit > 0 and download_count >= limit:
            logger.info("Reached global download limit (%d). Halting downloads.", limit)
            break
        if limit_per_section > 0 and section_download_count >= limit_per_section:
            logger.info("Reached section limit (%d) for %s. Moving to next section.", limit_per_section, section_name)
            break

        record = cache_manager.process_and_cache(fetcher, item, dry_run=dry_run)
        if record is not None:
            download_count += 1
            section_download_count += 1

    return download_count


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Polite PDF Scraper for Delhi Technological University (DTU)."
    )
    parser.add_argument(
        "--section",
        choices=["notices", "tenders", "jobs", "all"],
        default="all",
        help="Section to scrape (notices, tenders, jobs, or all). Default: all"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Global maximum PDFs to download across all sections (0 = unlimited). Default: 0"
    )
    parser.add_argument(
        "--limit-per-section",
        type=int,
        default=30,
        help="Maximum PDFs to download per section/page (default: 30)."
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Maximum listing pages to crawl per section. Default: 5"
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Directory to store cached PDFs (defaults to config setting: data/raw)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Crawl and log what would be downloaded without actually downloading files."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed debug logging."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(Path(__file__).parent / "config.yaml"),
        help="Path to YAML configuration file."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)

    log_dir = config.get("log_dir", "logs")
    setup_logging(args.verbose, log_dir)

    logger = logging.getLogger("scraper")
    logger.info("Initializing DTU PDF Scraper...")

    cache_dir = args.cache_dir or config.get("raw_dir", "data/raw")
    manifest_path = config.get("manifest_path", os.path.join(cache_dir, "manifest.jsonl"))

    fetcher = PoliteFetcher(config)
    cache_manager = PDFCacheManager(cache_dir=cache_dir, manifest_path=manifest_path)

    # Initialize robots.txt
    base_url = config.get("base_url", "https://dtu.ac.in")
    fetcher.load_robots_txt(base_url)

    target_sections = (
        ["notices", "jobs", "tenders"]
        if args.section == "all"
        else [args.section]
    )

    pdf_patterns = config.get("pdf_url_patterns", [".pdf"])
    total_downloaded = 0
    start_time = time.time()

    try:
        for section in target_sections:
            if section not in config.get("sections", {}):
                logger.warning("Section '%s' not defined in config.yaml. Skipping.", section)
                continue

            section_cfg = config["sections"][section]
            total_downloaded = scrape_section(
                section_name=section,
                section_cfg=section_cfg,
                fetcher=fetcher,
                cache_manager=cache_manager,
                max_pages=args.max_pages,
                limit=args.limit,
                limit_per_section=args.limit_per_section,
                dry_run=args.dry_run,
                pdf_patterns=pdf_patterns,
                current_download_count=total_downloaded
            )

            if args.limit > 0 and total_downloaded >= args.limit:
                logger.info("Overall limit of %d PDFs reached.", args.limit)
                break

    except CircuitBreakerError as e:
        logger.critical("Scraper aborted due to Circuit Breaker: %s", e)
    except KeyboardInterrupt:
        logger.warning("Scraper interrupted by user.")
    except Exception as e:
        logger.exception("Unexpected error during scraping: %s", e)
    finally:
        elapsed = time.time() - start_time
        logger.info("=" * 60)
        logger.info("Scraper Run Summary:")
        logger.info("  Processed/Downloaded in this run: %d", total_downloaded)
        logger.info("  Total items indexed in manifest: %d", len(cache_manager.seen_urls))
        logger.info("  Total unique PDFs cached: %d", len(cache_manager.seen_hashes))
        logger.info("  Cache directory: %s", cache_dir)
        logger.info("  Elapsed time: %.2f seconds", elapsed)
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
