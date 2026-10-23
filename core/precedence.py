"""
Annex A Source Precedence Policy Resolver
Implements deterministic conflict resolution across university documents:
1. Applicability filter (effective date + programme/batch scope)
2. Explicit supersession (valid only for Level 1 or 2)
3. Authority hierarchy (Level 1 > Level 2 > Level 3 > Level 4 > Level 5)
4. Recency (later effective_from wins among equal authority)
5. Unresolved conflict detection (returns conflict_flagged only on genuine contradiction)
6. Level 5 informational restriction & document instruction immunity (R8)
"""

import re
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip()[:10], "%Y-%m-%d")
    except ValueError:
        return None

def normalize_section_ref(text: str) -> str:
    """Normalizes section strings by stripping common prefixes and punctuation."""
    s = str(text or "").lower().strip()
    for prefix in ("clause ", "section ", "sec. ", "sec ", "rule "):
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
    return s.replace(" ", "")

def extract_clause_identifier(text: str) -> Optional[str]:
    """
    Extracts the canonical complete clause/section identifier.
    E.g. 'Clause R.1(B).22: Attendance' -> 'r.1(b).22'
         'Clause R.1(B).1' -> 'r.1(b).1'
         'Section 4.1' -> '4.1'
         'Clause 1' -> '1'
    """
    if not text:
        return None
    s = str(text).strip()
    m = re.search(
        r"(?:clause|section|sec\.?|rule)?\s*([a-zA-Z]\.\s*\d+(?:\([a-zA-Z0-9]+\))*\.\d+|\d+(?:\.\d+)*|[a-zA-Z]+\d+)",
        s,
        re.IGNORECASE
    )
    if m:
        return re.sub(r"\s+", "", m.group(1)).lower()
    return None

def is_clause_match(target_sec: str, chunk_sec: str) -> bool:
    """
    Matches target clause reference with chunk section accurately.
    Prevents prefix collisions like Clause R.1(B).1 matching R.1(B).10 (Comment 12).
    Allows heading text only after a clear boundary (e.g. colon, dash).
    """
    if not target_sec:
        # Whole document target supersedes all chunks of target doc
        return True
    if not chunk_sec:
        return False

    t_id = extract_clause_identifier(target_sec)
    c_id = extract_clause_identifier(chunk_sec)

    if t_id and c_id:
        return t_id == c_id

    # Fallback for non-standard section titles:
    # Match complete section identifier before boundary (colon, dash, etc.)
    t_base = re.split(r"[:\-\u2013\u2014]", target_sec, maxsplit=1)[0].strip().lower()
    c_base = re.split(r"[:\-\u2013\u2014]", chunk_sec, maxsplit=1)[0].strip().lower()
    t_clean = normalize_section_ref(t_base)
    c_clean = normalize_section_ref(c_base)

    return bool(t_clean and t_clean == c_clean)

def is_scope_applicable(doc_scope: str, student_val: str) -> bool:
    """
    Checks if student's programme or batch matches document scope.
    If student_val is 'ALL' (general query not specific to one student),
    general university policies remain applicable.
    """
    if not doc_scope or doc_scope.strip().upper() == "ALL":
        return True
    if not student_val or student_val.strip().upper() == "ALL":
        return True

    allowed = [s.strip().lower() for s in doc_scope.split(",")]
    s_val = student_val.strip().lower()

    for item in allowed:
        if item.endswith("+"):
            try:
                base_year = int(item[:-1])
                if int(s_val) >= base_year:
                    return True
            except ValueError:
                pass
        elif item == s_val:
            return True
    return False

def check_genuine_conflict(item_a: Dict[str, Any], item_b: Dict[str, Any]) -> bool:
    """
    Checks whether two same-level, same-date candidate documents make incompatible claims.
    Compares specific rule thresholds (percentages, CGPA, credits, marks, duration) and
    opposing policy verdicts, rather than requiring all numbers to differ (Comment 11).
    """
    text_a = item_a.get("text", "")
    text_b = item_b.get("text", "")
    lower_a = text_a.lower()
    lower_b = text_b.lower()

    # 1. Compare percentage thresholds (e.g. 75% vs 80% even when sharing clause numbers)
    pcts_a = set(re.findall(r"\b\d+(?:\.\d+)?\s*%", text_a))
    pcts_b = set(re.findall(r"\b\d+(?:\.\d+)?\s*%", text_b))
    if pcts_a and pcts_b and pcts_a != pcts_b:
        return True

    # 2. Compare metric-specific values (CGPA, credits, marks, days/duration, fees)
    metrics = [
        (r"\b(?:cgpa|sgpa|gpa)\s*(?:of|is|>=|<=|:)?\s*(\d+(?:\.\d+)?)", "gpa"),
        (r"\b(\d+(?:\.\d+)?)\s*credits?\b", "credits"),
        (r"\b(\d+(?:\.\d+)?)\s*marks?\b", "marks"),
        (r"\b(\d+)\s*(?:days?|weeks?|months?)\b", "duration"),
        (r"(?:rs\.?|inr)\s*([\d,]+)", "fee")
    ]
    for pattern, _ in metrics:
        vals_a = set(re.findall(pattern, lower_a))
        vals_b = set(re.findall(pattern, lower_b))
        if vals_a and vals_b and vals_a != vals_b:
            return True

    # 3. Opposing policy verdicts
    verdict_pairs = [
        (r"\beligible\b", r"\b(?:not\s+eligible|ineligible|barred|detained)\b"),
        (r"\bpermitted\b", r"\b(?:not\s+permitted|prohibited|strictly\s+barred)\b"),
        (r"\bmandatory\b", r"\boptional\b")
    ]
    for pos_pat, neg_pat in verdict_pairs:
        a_has_pos = bool(re.search(pos_pat, lower_a)) and not bool(re.search(neg_pat, lower_a))
        b_has_neg = bool(re.search(neg_pat, lower_b))
        b_has_pos = bool(re.search(pos_pat, lower_b)) and not bool(re.search(neg_pat, lower_b))
        a_has_neg = bool(re.search(neg_pat, lower_a))

        if (a_has_pos and b_has_neg) or (b_has_pos and a_has_neg):
            return True

    return False

def resolve_precedence(
    chunks: List[Dict[str, Any]],
    as_of_date: Optional[str] = None,
    programme: Optional[str] = None,
    batch_year: Optional[str] = None
) -> Dict[str, Any]:
    """
    Annex A Deterministic Precedence Resolver.
    """
    if not chunks:
        return {
            "winning_chunk": None,
            "applicable_chunks": [],
            "upcoming_chunks": [],
            "superseded_chunks": [],
            "conflicts_detected": [],
            "precedence_decision": "No chunks provided for precedence resolution.",
            "answer_type": "not_found"
        }

    if not as_of_date:
        as_of_date = datetime.now().strftime("%Y-%m-%d")

    target_dt = parse_date(as_of_date) or datetime.now()

    # Step 1: Applicability Filter
    applicable = []
    upcoming = []
    excluded_scope = []

    for c in chunks:
        # Check scope (programme & batch)
        p_scope = c.get("scope_programmes", "ALL")
        b_scope = c.get("scope_batches", "ALL")

        p_match = is_scope_applicable(p_scope, programme or "ALL")
        b_match = is_scope_applicable(b_scope, batch_year or "ALL")

        if not (p_match and b_match):
            excluded_scope.append(c)
            continue

        eff_from = parse_date(c.get("effective_from", ""))
        eff_to = parse_date(c.get("effective_to", ""))

        # Check effective window
        if eff_from and eff_from > target_dt:
            # Future rule: cannot be applied for this as_of_date
            upcoming.append(c)
            continue

        if eff_to and eff_to < target_dt:
            # Expired rule
            continue

        applicable.append(c)

    if not applicable:
        decision = "No authoritative document is applicable as of the requested date."
        if upcoming:
            decision = f"Requested query date ({as_of_date}) precedes effective date of available document(s) ({upcoming[0].get('doc_id')})."
        return {
            "winning_chunk": None,
            "applicable_chunks": [],
            "upcoming_chunks": upcoming,
            "superseded_chunks": [],
            "conflicts_detected": [],
            "precedence_decision": decision,
            "answer_type": "not_found"
        }

    # Step 2: Explicit Supersession (Normalized clause & doc matching)
    superseded_targets = []
    supersession_reasons = []

    for c in applicable:
        auth = int(c.get("authority_level", 5))
        if auth in (1, 2) and c.get("supersedes"):
            targets = [t.strip() for t in c["supersedes"].split(";") if t.strip()]
            for target in targets:
                t_doc, _, t_sec = target.partition("#")
                superseded_targets.append((t_doc.strip().lower(), t_sec.strip()))
                supersession_reasons.append(f"{c.get('doc_id')} explicitly supersedes {target} (step 2)")

    surviving = []
    superseded_chunks = []
    for c in applicable:
        c_doc = c.get("doc_id", "").strip().lower()
        c_sec = c.get("section", "")
        is_superseded = False

        for t_doc, t_sec in superseded_targets:
            if t_doc == c_doc:
                if is_clause_match(t_sec, c_sec):
                    is_superseded = True
                    break

        if is_superseded:
            superseded_chunks.append(c)
        else:
            surviving.append(c)

    if not surviving and superseded_chunks:
        # Retain the most recent active superseder
        surviving = [applicable[0]]

    # Step 3 & 4: Authority and Recency Filtering
    # Exclude Level 5 (Informational / Unofficial) from authoritative decisions
    authoritative = [c for c in surviving if int(c.get("authority_level", 5)) < 5]
    level_5_chunks = [c for c in surviving if int(c.get("authority_level", 5)) >= 5]

    if not authoritative:
        # Only Level 5 sources found: strictly informational per Annex A
        return {
            "winning_chunk": None,
            "applicable_chunks": [],
            "informational_chunks": level_5_chunks,
            "upcoming_chunks": upcoming,
            "superseded_chunks": superseded_chunks,
            "conflicts_detected": [],
            "precedence_decision": "Only Level 5 informational / unofficial sources found. Cannot be cited as authoritative university regulations per Annex A.",
            "answer_type": "informational_only"
        }

    def sort_key(c):
        auth = int(c.get("authority_level", 5))
        eff_dt = parse_date(c.get("effective_from", "")) or datetime(1970, 1, 1)
        # Higher authority = lower integer (Level 1 beats Level 2)
        # Later date = higher timestamp
        return (auth, -eff_dt.timestamp())

    authoritative.sort(key=sort_key)
    winner = authoritative[0]

    # Step 5: Check for Genuine Unresolved Conflicts
    # Only flag conflict if another candidate with equal authority and identical effective date has conflicting claims
    conflicts = []
    for other in authoritative[1:]:
        if (int(other.get("authority_level", 5)) == int(winner.get("authority_level", 5)) and
            other.get("effective_from") == winner.get("effective_from") and
            other.get("doc_id") != winner.get("doc_id")):
            if check_genuine_conflict(winner, other):
                conflicts.append({
                    "doc_a": winner.get("doc_id"),
                    "doc_b": other.get("doc_id"),
                    "chunk_a": winner,
                    "chunk_b": other,
                    "chunk_1": winner,
                    "chunk_2": other,
                    "authority_level": winner.get("authority_level"),
                    "effective_from": winner.get("effective_from")
                })

    if conflicts:
        return {
            "winning_chunk": winner,
            "applicable_chunks": authoritative,
            "upcoming_chunks": upcoming,
            "superseded_chunks": superseded_chunks,
            "conflicts_detected": conflicts,
            "precedence_decision": f"Unresolved conflict between {winner.get('doc_id')} and {conflicts[0]['doc_b']} at authority level {winner.get('authority_level')}. Flagged for review.",
            "answer_type": "conflict_flagged"
        }

    # Construct decision explanation
    decision_parts = []
    if supersession_reasons:
        decision_parts.extend(supersession_reasons)
    else:
        decision_parts.append(f"{winner.get('doc_id')} (Level {winner.get('authority_level')}, effective {winner.get('effective_from')}) prevails by authority/recency (steps 3-4)")

    if upcoming:
        decision_parts.append(f"Note: {len(upcoming)} upcoming future document(s) detected effective after {as_of_date}.")

    return {
        "winning_chunk": winner,
        "applicable_chunks": authoritative,
        "upcoming_chunks": upcoming,
        "superseded_chunks": superseded_chunks,
        "conflicts_detected": [],
        "precedence_decision": "; ".join(decision_parts),
        "answer_type": "retrieved_fact"
    }

if __name__ == "__main__":
    # Test Annex A.3 worked example from PS:
    # Academic Regulations level 1 effective 2024-07-01 min attendance 75%
    # Circular ACAD-2026-08 level 2 effective 2026-08-01 supersedes clause: 80%
    # Department FAQ level 4 effective 2026-09-15 "65% is enough"
    test_chunks = [
        {"doc_id": "ACAD-REG-2024", "section": "Clause 7.2", "authority_level": 1, "effective_from": "2024-07-01", "supersedes": "", "text": "Minimum attendance is 75%."},
        {"doc_id": "ACAD-2026-08", "section": "Section 1", "authority_level": 2, "effective_from": "2026-08-01", "supersedes": "ACAD-REG-2024#Clause 7.2", "text": "Minimum attendance is 80%."},
        {"doc_id": "DEPT-FAQ", "section": "Q3", "authority_level": 4, "effective_from": "2026-09-15", "supersedes": "", "text": "65% is enough."}
    ]

    print("=== Testing Annex A.3 Worked Example ===")
    res = resolve_precedence(test_chunks, as_of_date="2026-10-06")
    print("Winner:", res["winning_chunk"]["doc_id"], "-", res["winning_chunk"]["text"])
    print("Decision:", res["precedence_decision"])
    assert res["winning_chunk"]["doc_id"] == "ACAD-2026-08", "Failed Annex A.3 worked example!"
    print("[PASS] Annex A.3 Worked Example passed exactly!")
