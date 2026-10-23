"""
Metadata Extractor Module.
Applies Regex and heuristic rules to cached PDFs to extract structured administrative metadata.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

from pypdf import PdfReader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex Patterns
# ---------------------------------------------------------------------------

# File / Reference Number patterns
FILE_NUMBER_PATTERNS = [
    # Explicit F.No. / Ref No. / File No.
    re.compile(
        r'(?:F\.?\s*No\.?|Ref\.?\s*(?:No\.?)?|File\s*No\.?|Circular\s*No\.?|Notice\s*No\.?|Order\s*No\.?|NIT\s*No\.?|Advt\.?\s*No\.?)\s*[:=\-\s]\s*([A-Za-z0-9\-\.\/\(\)]+(?:[\s\/_\-][A-Za-z0-9\-\.\/\(\)]+)*)',
        re.IGNORECASE
    ),
    # University specific prefixes (e.g. DTU/Acad/..., DTU/Estt/..., COE/...)
    re.compile(
        r'\b((?:DTU|COE|ACAD|ESTT|PURCHASE|EXAM|GEN|SEC)[A-Za-z0-9\.\-\/\_]{4,40})\b',
        re.IGNORECASE
    ),
    # Standard Indian Government / University file numbering: No. F.X/Y/...
    re.compile(
        r'\b(No\.\s*F\.?[A-Za-z0-9\-\.\/\(\)\s]{4,40})\b',
        re.IGNORECASE
    )
]

# Date patterns
DATE_REGEX_1 = re.compile(r'\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b')
DATE_REGEX_2 = re.compile(
    r'\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[,.\s]+\d{4})\b',
    re.IGNORECASE
)

# Published Date context patterns
PUBLISHED_DATE_PATTERNS = [
    re.compile(r'(?:Dated?|Date\s*of\s*issue|Date)\s*[:=\-\s]\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})', re.IGNORECASE),
    re.compile(r'(?:Dated?|Date\s*of\s*issue|Date)\s*[:=\-\s]\s*(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4})', re.IGNORECASE)
]

# Deadline / Submission Date context patterns
DEADLINE_PATTERNS = [
    re.compile(
        r'(?:last\s*date|closing\s*date|submission\s*deadline|deadline|due\s*date|bid\s*submission\s*end\s*date|bid\s*submission\s*closing\s*date)(?:[^\n\.\,]{0,40})?[:=\-\s]\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}(?:\s*(?:at|upto|by)?\s*\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm|hrs|hours)?)?)',
        re.IGNORECASE
    ),
    re.compile(
        r'(?:last\s*date|closing\s*date|submission\s*deadline|deadline|due\s*date|bid\s*submission\s*end\s*date)(?:[^\n\.\,]{0,40})?[:=\-\s]\s*(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4}(?:\s*(?:at|upto|by)?\s*\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm|hrs|hours)?)?)',
        re.IGNORECASE
    ),
    re.compile(
        r'(?:on\s+or\s+before|upto|latest\s+by)\s+(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})',
        re.IGNORECASE
    )
]

# Department / Authority Keyword Map
AUTHORITY_KEYWORDS = [
    ("Office of the Dean Academic", ["dean academic", "dean (academic)", "academic branch", "academic-ug", "academic-pg"]),
    ("Office of the Registrar", ["registrar", "office of the registrar", "administration"]),
    ("Controller of Examinations", ["controller of examinations", "examination branch", "conduct branch", "coe"]),
    ("Dean Student Welfare", ["dean student welfare", "dsw", "student welfare"]),
    ("Dean (Research & Development)", ["dean r&d", "dean (r&d)", "research & development", "r & d"]),
    ("Estate Office / Security Office", ["estate officer", "estate office", "security office", "security officer", "vehicle"]),
    ("Hostel Office", ["hostel office", "chief warden", "warden", "hostel"]),
    ("Store & Purchase Branch", ["store & purchase", "purchase branch", "store branch", "procurement"]),
    ("Recruitment & Establishment", ["establishment branch", "recruitment cell", "recruitment", "personnel branch"]),
    ("Department of Computer Science & Engineering", ["computer science", "dce", "cse"]),
    ("Department of Information Technology", ["information technology", "it department"]),
    ("Department of Electronics & Communication", ["electronics", "ece", "ece department"]),
    ("Department of Electrical Engineering", ["electrical engineering", "ee department"]),
    ("Department of Mechanical Engineering", ["mechanical engineering", "dme"]),
    ("Department of Civil Engineering", ["civil engineering"]),
    ("Department of Applied Physics", ["applied physics"]),
    ("Department of Applied Chemistry", ["applied chemistry"]),
    ("Department of Applied Mathematics", ["applied mathematics"]),
    ("Delhi School of Management", ["delhi school of management", "dsm"]),
    ("Office of Vice Chancellor", ["vice chancellor", "vc office", "hon'ble vice chancellor"])
]


@dataclass
class ExtractedMetadata:
    doc_id: str
    section: str
    category: str
    title: str
    file_number: Optional[str]
    published_date: Optional[str]
    deadline_date: Optional[str]
    issuing_authority: str
    total_pages: int
    file_size_bytes: int
    source_url: str
    cached_file_path: str
    needs_review: bool
    review_notes: str


def extract_text_from_pdf(pdf_path: Path, max_pages: int = 3) -> Tuple[str, int]:
    """Extract raw text from the first max_pages of a PDF.

    Returns (text_content, total_pages).
    """
    try:
        reader = PdfReader(str(pdf_path))
        total_pages = len(reader.pages)
        pages_to_extract = min(total_pages, max_pages)

        extracted_text = []
        for i in range(pages_to_extract):
            page = reader.pages[i]
            page_text = page.extract_text()
            if page_text:
                extracted_text.append(page_text)

        full_text = "\n".join(extracted_text)
        return full_text, total_pages
    except Exception as e:
        logger.warning("Error reading PDF %s: %s", pdf_path, e)
        return "", 0


def extract_file_number(text: str, title: Optional[str] = None) -> Optional[str]:
    """Extract official file / reference number using regex rules from text and title."""
    # 1. Check title for explicit Bid Number or Advt No.
    if title:
        gem_match = re.search(r'\b(GEM/\d{4}/[A-Z]/\d+)\b', title, re.IGNORECASE)
        if gem_match:
            return gem_match.group(1).strip()
        bid_match = re.search(r'(?:Bid|NIT|NIQ|Advt\.?)\s*Number\s*[:=\-\s]\s*([^\)\n,;]+)', title, re.IGNORECASE)
        if bid_match:
            return bid_match.group(1).strip()

    if not text:
        return None

    # Search in top 2500 characters where headers / reference numbers reside
    header_chunk = text[:2500]

    # GeM bid number inside text
    gem_text_match = re.search(r'\b(GEM/\d{4}/[A-Z]/\d+)\b', header_chunk, re.IGNORECASE)
    if gem_text_match:
        return gem_text_match.group(1).strip()

    for pattern in FILE_NUMBER_PATTERNS:
        match = pattern.search(header_chunk)
        if match:
            candidate = match.group(1).strip()
            # Clean up newlines
            candidate = re.sub(r'[\r\n]+', ' ', candidate)
            # Clean up trailing noise words like Dated, Notice, Circular
            candidate = re.sub(r'(?i)\s*(?:dated?|notice|circular|date:?)\b.*$', '', candidate)
            candidate = re.sub(r'[\s,;:.]+$', '', candidate).strip()
            # Filter out false positives
            if len(candidate) >= 4 and not candidate.lower().startswith("http") and not candidate.lower().startswith("dtu.ac.in"):
                return candidate

    return None


def extract_published_date(text: str, manifest_date: Optional[str]) -> Optional[str]:
    """Extract published date, prioritizing manifest then regex from PDF text."""
    # If manifest already provided a clean DD.MM.YYYY date, use it as primary
    if manifest_date and manifest_date.strip():
        return manifest_date.strip()

    if not text:
        return None

    header_chunk = text[:2000]
    for pattern in PUBLISHED_DATE_PATTERNS:
        match = pattern.search(header_chunk)
        if match:
            return match.group(1).strip()

    # Generic date search in top 500 characters
    match1 = DATE_REGEX_1.search(text[:500])
    if match1:
        return match1.group(1).strip()

    match2 = DATE_REGEX_2.search(text[:500])
    if match2:
        return match2.group(1).strip()

    return None


def extract_deadline_date(text: str) -> Optional[str]:
    """Extract submission / application deadline date using regex rules."""
    if not text:
        return None

    for pattern in DEADLINE_PATTERNS:
        match = pattern.search(text)
        if match:
            candidate = match.group(1).strip()
            candidate = re.sub(r'[\s,;.]+$', '', candidate)
            return candidate

    return None


def detect_issuing_authority(text: str, title: str) -> str:
    """Identify the issuing department or university authority using keyword rules."""
    combined = (title + "\n" + text[:2500]).lower()

    for authority_name, keywords in AUTHORITY_KEYWORDS:
        if any(kw in combined for kw in keywords):
            return authority_name

    # Check footer / end of text for signature lines
    footer_chunk = text[-1000:].lower() if len(text) > 1000 else ""
    for authority_name, keywords in AUTHORITY_KEYWORDS:
        if any(kw in footer_chunk for kw in keywords):
            return authority_name

    return "Delhi Technological University (General)"


def classify_document(section: str, title: str, text: str) -> str:
    """Classify administrative document into category."""
    combined = (title + " " + text[:1500]).lower()

    if section == "tenders" or any(kw in combined for kw in ["tender", "e-tender", "rfp", "bid", "quotation"]):
        if "corrigendum" in combined or "extension" in combined:
            return "Tender Corrigendum"
        return "Tender / Procurement"

    if section == "jobs" or any(kw in combined for kw in ["recruitment", "walk-in-interview", "advertisement", "engagement of", "vacancy"]):
        return "Job / Recruitment"

    if any(kw in combined for kw in ["date sheet", "examination schedule", "mid term", "end term", "practical exam", "datesheet"]):
        return "Examination / Date Sheet"

    if any(kw in combined for kw in ["result", "shortlisted", "selected candidates", "merit list"]):
        return "Result / Shortlist"

    if "circular" in combined:
        return "Circular"

    if "office order" in combined or "order" in combined:
        return "Office Order"

    if any(kw in combined for kw in ["fee", "scholarship", "fellowship", "financial assistance"]):
        return "Scholarship / Student Affairs"

    return "General Notice"


def process_pdf_document(
    pdf_path: Path,
    manifest_record: Dict[str, Any]
) -> ExtractedMetadata:
    """Process a single cached PDF and produce ExtractedMetadata."""
    doc_id = manifest_record.get("sha256", pdf_path.stem)
    section = manifest_record.get("section", "notices")
    title = manifest_record.get("title", "Untitled Document").strip()
    manifest_date = manifest_record.get("publication_date")
    source_url = manifest_record.get("original_url", "")
    file_size_bytes = manifest_record.get("file_size_bytes", pdf_path.stat().st_size if pdf_path.exists() else 0)

    # 1. Extract text
    text, total_pages = extract_text_from_pdf(pdf_path, max_pages=3)

    # 2. Extract fields via regex and rules
    file_number = extract_file_number(text, title=title)
    published_date = extract_published_date(text, manifest_date)
    deadline_date = extract_deadline_date(text)
    issuing_authority = detect_issuing_authority(text, title)
    category = classify_document(section, title, text)

    # 3. Determine Review Flag (Auto-extract + Manual Review)
    review_reasons = []
    if total_pages == 0 or len(text.strip()) < 50:
        review_reasons.append("Empty/Scanned text (may require OCR)")
    if not file_number:
        review_reasons.append("Missing file number")
    if not published_date:
        review_reasons.append("Missing publication date")
    if section in ["tenders", "jobs"] and not deadline_date:
        review_reasons.append(f"Missing deadline for {section}")

    needs_review = len(review_reasons) > 0
    review_notes = "; ".join(review_reasons) if review_reasons else "Clean extraction"

    return ExtractedMetadata(
        doc_id=doc_id,
        section=section,
        category=category,
        title=title,
        file_number=file_number,
        published_date=published_date,
        deadline_date=deadline_date,
        issuing_authority=issuing_authority,
        total_pages=total_pages,
        file_size_bytes=file_size_bytes,
        source_url=source_url,
        cached_file_path=str(pdf_path),
        needs_review=needs_review,
        review_notes=review_notes
    )
