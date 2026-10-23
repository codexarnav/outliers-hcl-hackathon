"""
Section-Aware Document Chunker
Extracts structured chunks with clause headers, tables, and Annex B metadata.
"""

import os
import re
import csv
import sys
import tempfile
import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Any
from pypdf import PdfReader

CLAUSE_PATTERN = re.compile(
    r'(R\.\s*1\([A-Z]\)\.\d+[^:\n]*:|Section\s+\d+[^:\n]*:|Q\d+:[^\n]*|TABLE\s+\d+:[^\n]*|Clause\s+\d+[^:\n]*:)',
    re.IGNORECASE
)

PAGE_MARKER_PATTERN = re.compile(r"(?:---|===|\[)?\s*Page\s+(\d+)\s*(?:---|===|\])?", re.IGNORECASE)

def extract_current_page(text_segment: str, default_page: int = 1) -> int:
    """Extracts explicit page marker from text if present, otherwise returns default."""
    matches = list(PAGE_MARKER_PATTERN.finditer(text_segment))
    if matches:
        try:
            return int(matches[-1].group(1))
        except ValueError:
            pass
    return default_page

def load_source_register(register_path: Path) -> Dict[str, Dict[str, Any]]:
    docs = {}
    if not register_path.exists():
        return docs
    with open(register_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            docs[row["doc_id"]] = row
    return docs

def ocr_image_bytes(image_data: bytes) -> str:
    """Extracts text from scanned image bytes using available OCR engines."""
    # 1. Try pytesseract if installed
    try:
        import pytesseract
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_data))
        text = pytesseract.image_to_string(img)
        if text.strip():
            return text.strip()
    except Exception:
        pass

    # 2. Try macOS native Vision OCR binary or script if available
    mac_bin = Path(__file__).resolve().parent.parent / "scripts" / "bin" / "ocr_mac"
    swift_script = Path(__file__).resolve().parent.parent / "scripts" / "ocr_vision.swift"
    if sys.platform == "darwin":
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(image_data)
                tmp_path = tmp.name
            try:
                cmd = None
                if mac_bin.exists():
                    cmd = [str(mac_bin), tmp_path]
                elif swift_script.exists() and shutil.which("swift"):
                    cmd = ["swift", str(swift_script), tmp_path]
                if cmd:
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                    if res.returncode == 0 and res.stdout.strip():
                        return res.stdout.strip()
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass

    # 3. Try tesseract CLI if in PATH
    tess_path = shutil.which("tesseract")
    if tess_path:
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(image_data)
                tmp_path = tmp.name
            try:
                res = subprocess.run([tess_path, tmp_path, "stdout"], capture_output=True, text=True, timeout=15)
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip()
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass

    return ""

def chunk_pdf(file_path: Path, doc_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    reader = PdfReader(str(file_path))
    chunks = []
    doc_id = doc_metadata.get("doc_id", file_path.stem)

    for page_idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text = text.strip()

        # If page has no embedded text stream (e.g. scanned PDF), attempt OCR on embedded images
        if not text and hasattr(page, "images") and len(page.images) > 0:
            extracted_parts = []
            for img in page.images:
                img_text = ocr_image_bytes(img.data)
                if img_text:
                    extracted_parts.append(img_text)
            if extracted_parts:
                text = "\n\n".join(extracted_parts).strip()

        # If still no text (e.g. OCR unavailable or textless page), fallback to document metadata on first page
        if not text:
            if page_idx == 0:
                text = (
                    f"{doc_metadata.get('title', '')}\n"
                    f"Issued by: {doc_metadata.get('issuer', 'University Administration')}\n"
                    f"Document ID: {doc_id}\n"
                    f"Effective From: {doc_metadata.get('effective_from', '')}"
                )
            else:
                continue

        page_num = page_idx + 1

        # Check for clauses in page text
        split_points = [m.start() for m in CLAUSE_PATTERN.finditer(text)]

        if not split_points or len(split_points) == 1:
            # Single section on this page or standard paragraph
            # Extract section name if present
            first_match = CLAUSE_PATTERN.search(text)
            section_name = first_match.group(0).strip(":") if first_match else f"Page {page_num}"
            chunk_id = f"{doc_id}_P{page_num}_0"
            chunks.append({
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "title": doc_metadata.get("title", ""),
                "section": section_name,
                "page": page_num,
                "text": text,
                "authority_level": int(doc_metadata.get("authority_level", 1)),
                "version": doc_metadata.get("version", "1.0"),
                "effective_from": doc_metadata.get("effective_from", "2024-07-01"),
                "effective_to": doc_metadata.get("effective_to", ""),
                "supersedes": doc_metadata.get("supersedes", ""),
                "scope_programmes": doc_metadata.get("scope_programmes", "ALL"),
                "scope_batches": doc_metadata.get("scope_batches", "ALL"),
                "provenance": doc_metadata.get("provenance", ""),
            })
        else:
            # Handle text continuation before first heading on this page (Comment 3)
            if split_points[0] > 0:
                leading_text = text[:split_points[0]].strip()
                if leading_text:
                    if chunks:
                        # Append continuation text to previous clause chunk
                        chunks[-1]["text"] = chunks[-1]["text"] + "\n\n" + leading_text
                    else:
                        chunk_id = f"{doc_id}_P{page_num}_0"
                        chunks.append({
                            "chunk_id": chunk_id,
                            "doc_id": doc_id,
                            "title": doc_metadata.get("title", ""),
                            "section": f"Page {page_num} Preamble",
                            "page": page_num,
                            "text": leading_text,
                            "authority_level": int(doc_metadata.get("authority_level", 1)),
                            "version": doc_metadata.get("version", "1.0"),
                            "effective_from": doc_metadata.get("effective_from", "2024-07-01"),
                            "effective_to": doc_metadata.get("effective_to", ""),
                            "supersedes": doc_metadata.get("supersedes", ""),
                            "scope_programmes": doc_metadata.get("scope_programmes", "ALL"),
                            "scope_batches": doc_metadata.get("scope_batches", "ALL"),
                            "provenance": doc_metadata.get("provenance", ""),
                        })

            # Multiple clauses on one page -> split into clause chunks
            for idx in range(len(split_points)):
                start = split_points[idx]
                end = split_points[idx + 1] if idx + 1 < len(split_points) else len(text)
                section_text = text[start:end].strip()

                m = CLAUSE_PATTERN.search(section_text)
                section_name = m.group(0).strip(":") if m else f"Page {page_num} Sec {idx+1}"

                chunk_id = f"{doc_id}_P{page_num}_{idx+1}"
                chunks.append({
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "title": doc_metadata.get("title", ""),
                    "section": section_name,
                    "page": page_num,
                    "text": section_text,
                    "authority_level": int(doc_metadata.get("authority_level", 1)),
                    "version": doc_metadata.get("version", "1.0"),
                    "effective_from": doc_metadata.get("effective_from", "2024-07-01"),
                    "effective_to": doc_metadata.get("effective_to", ""),
                    "supersedes": doc_metadata.get("supersedes", ""),
                    "scope_programmes": doc_metadata.get("scope_programmes", "ALL"),
                    "scope_batches": doc_metadata.get("scope_batches", "ALL"),
                    "provenance": doc_metadata.get("provenance", ""),
                })

    return chunks

def chunk_text_file(file_path: Path, doc_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    with open(file_path, "r", encoding="utf-8") as f:
        full_text = f.read()

    doc_id = doc_metadata.get("doc_id", file_path.stem)
    matches = list(CLAUSE_PATTERN.finditer(full_text))
    chunks = []

    if not matches:
        chunks.append({
            "chunk_id": f"{doc_id}_0",
            "doc_id": doc_id,
            "title": doc_metadata.get("title", ""),
            "section": "General",
            "page": extract_current_page(full_text, default_page=1),
            "text": full_text.strip(),
            "authority_level": int(doc_metadata.get("authority_level", 1)),
            "version": doc_metadata.get("version", "1.0"),
            "effective_from": doc_metadata.get("effective_from", "2024-07-01"),
            "effective_to": doc_metadata.get("effective_to", ""),
            "supersedes": doc_metadata.get("supersedes", ""),
            "scope_programmes": doc_metadata.get("scope_programmes", "ALL"),
            "scope_batches": doc_metadata.get("scope_batches", "ALL"),
            "provenance": doc_metadata.get("provenance", ""),
        })
        return chunks

    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
        clause_text = full_text[start:end].strip()
        section_name = match.group(0).strip(":")

        # Extract explicit page marker from text preceding match (Comment 2)
        page_num = extract_current_page(full_text[:start], default_page=1)

        chunks.append({
            "chunk_id": f"{doc_id}_C{idx+1}",
            "doc_id": doc_id,
            "title": doc_metadata.get("title", ""),
            "section": section_name,
            "page": page_num,
            "text": clause_text,
            "authority_level": int(doc_metadata.get("authority_level", 1)),
            "version": doc_metadata.get("version", "1.0"),
            "effective_from": doc_metadata.get("effective_from", "2024-07-01"),
            "effective_to": doc_metadata.get("effective_to", ""),
            "supersedes": doc_metadata.get("supersedes", ""),
            "scope_programmes": doc_metadata.get("scope_programmes", "ALL"),
            "scope_batches": doc_metadata.get("scope_batches", "ALL"),
            "provenance": doc_metadata.get("provenance", ""),
        })

    return chunks

def chunk_all_documents(docs_dir: Path, register_path: Path) -> List[Dict[str, Any]]:
    register = load_source_register(register_path)
    all_chunks = []

    # Priority to text transcriptions if available, otherwise PDF
    processed_doc_ids = set()

    # 1. Process text companions (e.g. DTU-ORD-2024.txt)
    for file_name in os.listdir(docs_dir):
        if file_name.endswith(".txt"):
            file_path = docs_dir / file_name
            doc_id = file_path.stem
            meta = register.get(doc_id, {
                "doc_id": doc_id,
                "title": file_name,
                "authority_level": 1,
                "version": "1.0",
                "effective_from": "2024-07-01",
                "effective_to": "",
                "supersedes": "",
                "scope_programmes": "ALL",
                "scope_batches": "ALL",
            })
            chunks = chunk_text_file(file_path, meta)
            all_chunks.extend(chunks)
            processed_doc_ids.add(doc_id)
            print(f"[OK] Chunked {file_name}: {len(chunks)} clause chunks extracted.")

    # 2. Process PDFs (excluding already processed via text)
    for file_name in os.listdir(docs_dir):
        if not file_name.endswith(".pdf"):
            continue
        file_path = docs_dir / file_name
        doc_id = file_path.stem
        if doc_id in processed_doc_ids:
            continue
        meta = register.get(doc_id, {
            "doc_id": doc_id,
            "title": file_name,
            "authority_level": 2,
            "version": "1.0",
            "effective_from": "2024-07-01",
            "effective_to": "",
            "supersedes": "",
            "scope_programmes": "ALL",
            "scope_batches": "ALL",
        })
        chunks = chunk_pdf(file_path, meta)
        all_chunks.extend(chunks)
        print(f"[OK] Chunked {file_name}: {len(chunks)} chunks extracted.")

    return all_chunks

if __name__ == "__main__":
    docs_dir = Path("data/documents")
    reg_path = Path("data/source_register.csv")
    chunks = chunk_all_documents(docs_dir, reg_path)
    print(f"Total chunks extracted across corpus: {len(chunks)}")
