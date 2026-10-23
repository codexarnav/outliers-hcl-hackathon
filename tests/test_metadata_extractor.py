"""
Unit tests for metadata_extractor.py (regex and rule-based parsing).
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from extractor.metadata_extractor import (
    extract_file_number,
    extract_published_date,
    extract_deadline_date,
    detect_issuing_authority,
    classify_document,
    process_pdf_document,
    ExtractedMetadata
)


def test_extract_file_number_from_text():
    sample_text = """
    DELHI TECHNOLOGICAL UNIVERSITY
    Shahbad Daulatpur, Bawana Road, Delhi-110042
    F.No. DTU/Acad-UG/2026/1042
    Dated: 15.10.2026
    CIRCULAR
    """
    fn = extract_file_number(sample_text)
    assert fn is not None
    assert "DTU/Acad-UG/2026/1042" in fn


def test_extract_gem_bid_number_from_title():
    title = "NIT FOR Single Nozzle 3D printer (Bid Number: GEM/2026/B/8183895)"
    fn = extract_file_number("", title=title)
    assert fn == "GEM/2026/B/8183895"


def test_extract_published_date():
    text = "DELHI TECHNOLOGICAL UNIVERSITY\nDated: 18.09.2026\nNotice"
    assert extract_published_date(text, manifest_date=None) == "18.09.2026"
    # Manifest date takes priority
    assert extract_published_date(text, manifest_date="20.09.2026") == "20.09.2026"


def test_extract_deadline_date():
    text = """
    Applications are invited for contract positions.
    The last date for submission of online application is 15th November 2026 upto 5:00 PM.
    """
    deadline = extract_deadline_date(text)
    assert deadline is not None
    assert "15th November 2026" in deadline


def test_detect_issuing_authority():
    text = "Office of the Controller of Examinations\nResults of B.Tech 4th Semester"
    authority = detect_issuing_authority(text, title="Result Notice")
    assert authority == "Controller of Examinations"

    text2 = "Department of Computer Science & Engineering\nNotice for Lab Allotment"
    authority2 = detect_issuing_authority(text2, title="Lab Schedule")
    assert authority2 == "Department of Computer Science & Engineering"


def test_classify_document():
    assert classify_document("tenders", "NIT for Lab Equipment", "") == "Tender / Procurement"
    assert classify_document("jobs", "Engagement of Assistant Professor", "") == "Job / Recruitment"
    assert classify_document("notices", "Date Sheet for Mid Term Examination", "") == "Examination / Date Sheet"
    assert classify_document("notices", "Circular regarding Attendance", "") == "Circular"
    assert classify_document("notices", "General Guidelines", "") == "General Notice"


def test_process_pdf_document_mocked(tmp_path):
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    mock_manifest = {
        "sha256": "abcdef123456",
        "section": "notices",
        "title": "Date Sheet for B.Tech",
        "publication_date": "10.10.2026",
        "original_url": "https://dtu.ac.in/datesheet.pdf",
        "file_size_bytes": 1024
    }

    mock_text = """
    DELHI TECHNOLOGICAL UNIVERSITY
    F.No. DTU/COE/2026/88
    Date: 10.10.2026
    Date Sheet for End Term Examination
    Controller of Examinations
    """

    with patch("extractor.metadata_extractor.extract_text_from_pdf", return_value=(mock_text, 2)):
        meta = process_pdf_document(pdf_file, mock_manifest)
        assert isinstance(meta, ExtractedMetadata)
        assert meta.doc_id == "abcdef123456"
        assert meta.category == "Examination / Date Sheet"
        assert "DTU/COE/2026/88" in meta.file_number
        assert meta.published_date == "10.10.2026"
        assert meta.issuing_authority == "Controller of Examinations"
        assert meta.total_pages == 2
        assert meta.needs_review is False
