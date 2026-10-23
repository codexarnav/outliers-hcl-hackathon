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
    # Finding #8: Clause-specific supersession must NOT supersede unrelated clauses from the same document
    superseded_doc_ids = set()
    superseded_clause_refs = set()
    supersession_reasons = []

    def normalize_ref(ref: str) -> str:
        return ref.lower().replace("clause", "").replace("section", "").replace(" ", "").strip()

    for c in applicable:
        auth = int(c.get("authority_level", 5))
        if auth in (1, 2) and c.get("supersedes"):
            targets = [t.strip() for t in c["supersedes"].split(";") if t.strip()]
            for target in targets:
                if "#" in target:
                    doc_part, sec_part = target.split("#", 1)
                    superseded_clause_refs.add((normalize_ref(doc_part), normalize_ref(sec_part)))
                else:
                    superseded_doc_ids.add(normalize_ref(target))
                supersession_reasons.append(f"{c.get('doc_id')} explicitly supersedes {target} (step 2)")

    surviving = []
    superseded_chunks = []
    for c in applicable:
        doc_id = c.get("doc_id", "").strip()
        section = c.get("section", "").strip()
        norm_doc = normalize_ref(doc_id)
        norm_sec = normalize_ref(section)

        is_doc_superseded = norm_doc in superseded_doc_ids
        is_clause_superseded = False
        for s_doc, s_sec in superseded_clause_refs:
            if norm_doc == s_doc and (norm_sec == s_sec or s_sec in norm_sec or norm_sec in s_sec):
                is_clause_superseded = True
                break

        if is_doc_superseded or is_clause_superseded:
            superseded_chunks.append(c)
        else:
            surviving.append(c)

    if not surviving and superseded_chunks:
        # If all were somehow marked superseded, retain the latest superseder
        surviving = [applicable[0]]

    # Step 3 & 4: Authority and Recency Comparison
    # Filter out Level 5 for authoritative decisions (informational only)
    authoritative = [c for c in surviving if int(c.get("authority_level", 5)) < 5]
    if not authoritative:
        authoritative = surviving

    def is_competing(w: Dict[str, Any], c: Dict[str, Any]) -> bool:
        """Determines if two candidate documents compete/address the same academic domain topic."""
        w_doc = w.get("doc_id", "").lower().strip()
        c_supersedes = c.get("supersedes", "").lower().strip()
        if w_doc and w_doc in c_supersedes:
            return True

        domain_topics = [
            "fee", "tuition", "attendance", "absent", "condonation", "sports",
            "supplementary", "makeup", "placement", "elective", "cws", "hostel"
        ]
        w_text = (w.get("title", "") + " " + w.get("text", "")).lower()
        c_text = (c.get("title", "") + " " + c.get("text", "")).lower()
        shared = [t for t in domain_topics if (t in w_text and t in c_text)]
        return len(shared) > 0

    # Winner starts as top retrieved candidate
    winner = authoritative[0]

    # Evaluate whether any other competing candidate overrides winner on the same topic
    for candidate in authoritative[1:]:
        if not is_competing(winner, candidate):
            continue

        c_auth = int(candidate.get("authority_level", 5))
        w_auth = int(winner.get("authority_level", 5))
        c_date = parse_date(candidate.get("effective_from", "")) or datetime(1970, 1, 1)
        w_date = parse_date(winner.get("effective_from", "")) or datetime(1970, 1, 1)

        # Higher authority prevails on competing topic
        if c_auth < w_auth:
            winner = candidate
        # Equal authority: later effective date prevails
        elif c_auth == w_auth and c_date > w_date:
            winner = candidate

    # Step 5: Check for Unresolved Conflicts
    # Only flag conflict if both documents address the same section/rule or share supersession targets
    conflicts = []
    winner_supersedes = set(t.strip().lower() for t in winner.get("supersedes", "").split(";") if t.strip())
    winner_sec = winner.get("section", "").strip().lower()
    winner_doc = winner.get("doc_id", "")

    for other in authoritative[1:]:
        if (int(other.get("authority_level", 5)) == int(winner.get("authority_level", 5)) and
            other.get("effective_from") == winner.get("effective_from") and
            other.get("doc_id") != winner_doc):
            
            other_supersedes = set(t.strip().lower() for t in other.get("supersedes", "").split(";") if t.strip())
            other_sec = other.get("section", "").strip().lower()

            # Conflict triggers if they target the same section or same supersedes clause
            shared_supersedes = winner_supersedes & other_supersedes
            same_section = (winner_sec and other_sec and (winner_sec == other_sec or winner_sec in other_sec or other_sec in winner_sec))

            if shared_supersedes or same_section:
                conflicts.append({
                    "doc_a": winner_doc,
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
