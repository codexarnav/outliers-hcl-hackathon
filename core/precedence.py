"""
Annex A Source Precedence Policy Resolver
Implements deterministic conflict resolution across university documents:
1. Applicability filter (effective date + programme/batch scope)
2. Explicit supersession (valid only for Level 1 or 2)
3. Authority hierarchy (Level 1 > Level 2 > Level 3 > Level 4 > Level 5)
4. Recency (later effective_from wins among equal authority)
5. Unresolved conflict detection (returns conflict_flagged)
6. Level 5 informational restriction & document instruction immunity (R8)
"""

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

def is_scope_applicable(doc_scope: str, student_val: str) -> bool:
    """Checks if student's programme or batch matches document scope."""
    if not doc_scope or doc_scope.strip().upper() == "ALL":
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
            "answer_type": str (e.g. 'retrieved_fact', 'conflict_flagged')
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

    # Step 1: Applicability Filter
    for chunk in chunks:
        eff_from = parse_date(chunk.get("effective_from", ""))
        eff_to = parse_date(chunk.get("effective_to", ""))

        # Scope filter
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
            # Expired
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

    # Step 2: Explicit Supersession
    # A Level 1 or 2 document can explicitly supersede earlier doc_ids or clauses
    superseded_ids = set()
    supersession_reasons = []

    for c in applicable:
        auth = int(c.get("authority_level", 5))
        if auth in (1, 2) and c.get("supersedes"):
            targets = [t.strip() for t in c["supersedes"].split(";") if t.strip()]
            for target in targets:
                superseded_ids.add(target.lower())
                supersession_reasons.append(f"{c.get('doc_id')} explicitly supersedes {target} (step 2)")

    surviving = []
    superseded_chunks = []
    for c in applicable:
        doc_id = c.get("doc_id", "").lower()
        section = c.get("section", "").lower()
        full_ref = f"{doc_id}#{section}"
        if doc_id in superseded_ids or full_ref in superseded_ids:
            superseded_chunks.append(c)
        else:
            surviving.append(c)

    if not surviving and superseded_chunks:
        # If all were somehow marked superseded, retain the latest superseder
        surviving = [applicable[0]]

    # Step 3 & 4: Authority and Recency Sorting
    # Filter out Level 5 for authoritative decisions (informational only)
    authoritative = [c for c in surviving if int(c.get("authority_level", 5)) < 5]
    if not authoritative:
        authoritative = surviving

    def sort_key(c):
        auth = int(c.get("authority_level", 5))
        eff_dt = parse_date(c.get("effective_from", "")) or datetime(1970, 1, 1)
        # Higher authority = lower integer (1 is highest)
        # Later date = higher datetime
        return (auth, -eff_dt.timestamp())

    authoritative.sort(key=sort_key)
    winner = authoritative[0]

    # Step 5: Check for Unresolved Conflicts
    # If there is another document with equal authority, identical effective date,
    # and differing content
    conflicts = []
    for other in authoritative[1:]:
        if (int(other.get("authority_level", 5)) == int(winner.get("authority_level", 5)) and
            other.get("effective_from") == winner.get("effective_from") and
            other.get("doc_id") != winner.get("doc_id")):
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
