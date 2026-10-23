"""
Script to generate source_register.csv from cached PDFs and manifest.jsonl.
Applies Regex and heuristic rules to extract administrative metadata.
"""

import argparse
import csv
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

from extractor.metadata_extractor import process_pdf_document, ExtractedMetadata


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def load_manifest(manifest_path: Path) -> List[Dict[str, Any]]:
    """Load records from manifest.jsonl."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    records = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def generate_source_register(
    manifest_path: str = "data/manifest.jsonl",
    raw_dir: str = "data/raw",
    output_csv: str = "data/source_register.csv",
    limit: int = 0
):
    logger = logging.getLogger("source_register")
    manifest_p = Path(manifest_path)
    raw_p = Path(raw_dir)
    output_p = Path(output_csv)
    output_p.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Loading manifest from %s", manifest_p)
    records = load_manifest(manifest_p)
    logger.info("Found %d manifest entries.", len(records))

    if limit > 0:
        records = records[:limit]
        logger.info("Limiting processing to first %d records.", limit)

    extracted_rows: List[ExtractedMetadata] = []
    start_time = time.time()

    for idx, rec in enumerate(records, start=1):
        sha = rec.get("sha256")
        if not sha:
            continue
        pdf_path = raw_p / f"{sha}.pdf"

        if not pdf_path.exists():
            logger.warning("PDF file missing for hash %s: %s", sha, pdf_path)
            continue

        logger.debug("[%d/%d] Processing %s...", idx, len(records), sha[:12])
        meta = process_pdf_document(pdf_path, rec)
        extracted_rows.append(meta)

    # Write CSV
    fieldnames = [
        "doc_id",
        "section",
        "category",
        "title",
        "file_number",
        "published_date",
        "deadline_date",
        "issuing_authority",
        "total_pages",
        "file_size_bytes",
        "needs_review",
        "review_notes",
        "source_url",
        "cached_file_path"
    ]

    with open(output_p, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in extracted_rows:
            writer.writerow({
                "doc_id": r.doc_id,
                "section": r.section,
                "category": r.category,
                "title": r.title,
                "file_number": r.file_number or "",
                "published_date": r.published_date or "",
                "deadline_date": r.deadline_date or "",
                "issuing_authority": r.issuing_authority,
                "total_pages": r.total_pages,
                "file_size_bytes": r.file_size_bytes,
                "needs_review": r.needs_review,
                "review_notes": r.review_notes,
                "source_url": r.source_url,
                "cached_file_path": r.cached_file_path
            })

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("Source Register Generated Successfully!")
    logger.info("  Total documents processed: %d", len(extracted_rows))
    logger.info("  Clean extractions: %d", sum(1 for r in extracted_rows if not r.needs_review))
    logger.info("  Flagged for review: %d", sum(1 for r in extracted_rows if r.needs_review))
    logger.info("  Output saved to: %s", output_p.resolve())
    logger.info("  Elapsed time: %.2f seconds", elapsed)
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Generate source_register.csv from DTU cached PDFs and manifest."
    )
    parser.add_argument(
        "--manifest",
        default="data/manifest.jsonl",
        help="Path to manifest.jsonl (default: data/manifest.jsonl)"
    )
    parser.add_argument(
        "--raw-dir",
        default="data/raw",
        help="Path to raw cached PDF directory (default: data/raw)"
    )
    parser.add_argument(
        "--output",
        default="data/source_register.csv",
        help="Output CSV path (default: data/source_register.csv)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of documents to process (0 = all, default: 0)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)
    generate_source_register(
        manifest_path=args.manifest,
        raw_dir=args.raw_dir,
        output_csv=args.output,
        limit=args.limit
    )


if __name__ == "__main__":
    main()
