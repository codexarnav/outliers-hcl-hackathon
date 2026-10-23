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
    """Checks whether two same-level, same-date candidate documents have conflicting claims."""
    text_a = item_a.get("text", "")
    text_b = item_b.get("text", "")

    # Extract percentage and mark values
    nums_a = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", text_a))
    nums_b = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", text_b))

    # If both cite numerical thresholds and they disagree completely on those numbers:
    if nums_a and nums_b and not (nums_a & nums_b):
        return True

    # If both reference passing or eligibility with opposite verdicts:
    lower_a = text_a.lower()
    lower_b = text_b.lower()
    if ("pass" in lower_a and "fail" in lower_b) or ("eligible" in lower_a and "detained" in lower_b):
        return True

    return False

def resolve_precedence(
    chunks: List[Dict[str, Any]],
    as_of_date: str = "2026-10-23",
    programme: str = "ALL",
    batch_year: str = "ALL"
) -> Dict[str, Any]:
    """
    Applies the Annex A Source Precedence Policy over candidate chunks or rules.
    Returns:
        {
            "winning_chunk": Dict or None,
            "applicable_chunks": List[Dict],
            "upcoming_chunks": List[Dict],
            "superseded_chunks": List[Dict],
            "conflicts_detected": List[Dict],
            "precedence_decision": str,
            "answer_type": str ('retrieved_fact', 'conflict_flagged', 'informational_only', 'not_found')
        }
    """
    if not chunks:
        return {
            "winning_chunk": None,
            "applicable_chunks": [],
            "upcoming_chunks": [],
            "superseded_chunks": [],
            "conflicts_detected": [],
            "precedence_decision": "No candidate sources provided.",
            "answer_type": "not_found"
        }

    as_of_dt = parse_date(as_of_date) or datetime.now()

    applicable = []
    upcoming = []

    # Step 1: Applicability Filter (as_of_date, scope_programmes, scope_batches)
    for chunk in chunks:
        eff_from = parse_date(chunk.get("effective_from", ""))
        eff_to = parse_date(chunk.get("effective_to", ""))

        # Scope filter (cohort & programme)
        p_scope = chunk.get("scope_programmes", "ALL")
        b_scope = chunk.get("scope_batches", "ALL")
        if not is_scope_applicable(p_scope, programme):
            continue
        if not is_scope_applicable(b_scope, batch_year):
            continue

        if eff_from and eff_from > as_of_dt:
            upcoming.append(chunk)
            continue

        if eff_to and eff_to < as_of_dt:
            # Expired document
            continue

        applicable.append(chunk)

    if not applicable:
        decision = "No currently effective sources found."
        if upcoming:
            decision += f" Found {len(upcoming)} upcoming future circular(s) effective after {as_of_date}."
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
                superseded_targets.append((t_doc.strip().lower(), normalize_section_ref(t_sec)))
                supersession_reasons.append(f"{c.get('doc_id')} explicitly supersedes {target} (step 2)")

    surviving = []
    superseded_chunks = []
    for c in applicable:
        c_doc = c.get("doc_id", "").strip().lower()
        c_sec_norm = normalize_section_ref(c.get("section", ""))
        is_superseded = False

        for t_doc, t_sec_norm in superseded_targets:
            if t_doc == c_doc:
                if not t_sec_norm or t_sec_norm == c_sec_norm or t_sec_norm in c_sec_norm or c_sec_norm in t_sec_norm:
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
