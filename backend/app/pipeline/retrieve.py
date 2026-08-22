from __future__ import annotations

import re
from typing import Any

from app.integrations.banidb import BaniDBClient
from app.integrations.gurbaninow import GurbaniNowClient
from app.schemas import ExtractedClaim
from app.services.knowledge_base import get_knowledge_base

ANG_RE = re.compile(r"\bang\s*[:#]?\s*(\d{1,4})\b", re.IGNORECASE)
GURMUKHI_RE = re.compile(r"[\u0A00-\u0A7F]{6,}")

# English doctrinal sentences must not be sent to Gurmukhi search APIs.
SCRIPTURE_CATEGORIES = {"gurbani_misquote", "out_of_context"}

MIN_KEEP_SCORE = 0.30


def _should_search_scripture_apis(claim: ExtractedClaim) -> bool:
    if claim.quoted_gurbani:
        return True
    if GURMUKHI_RE.search(claim.text or ""):
        return True
    if ANG_RE.search(claim.text or "") or ANG_RE.search(claim.quoted_gurbani or ""):
        return True
    return claim.category in SCRIPTURE_CATEGORIES


async def retrieve_evidence(claim: ExtractedClaim) -> list[dict[str, Any]]:
    """Stage 3 — gather grounded passages only (no invented citations)."""
    evidence: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def add_many(items: list[dict[str, Any]], *, min_score: float | None = MIN_KEEP_SCORE) -> None:
        for item in items:
            eid = item.get("id")
            if not eid or eid in seen_ids:
                continue
            score = item.get("score")
            if min_score is not None and score is not None and float(score) < min_score:
                continue
            seen_ids.add(eid)
            evidence.append(item)

    kb = get_knowledge_base()

    # Known-false first — these are curated, high-precision matches.
    add_many(kb.match_known_false(claim.text), min_score=0.42)

    category_map = {
        "rehat": "rehat",
        "historical": "history",
        "propaganda": "propaganda",
        "gurbani_misquote": "gurbani",
        "out_of_context": "gurbani",
        "doctrine": "doctrine",
    }
    curated_cat = category_map.get(claim.category)
    add_many(kb.search(claim.text, limit=6, category=curated_cat))

    if _should_search_scripture_apis(claim):
        banidb = BaniDBClient()
        gnow = GurbaniNowClient()
        ang_match = ANG_RE.search(claim.text) or ANG_RE.search(claim.quoted_gurbani or "")
        if ang_match:
            ang = int(ang_match.group(1))
            if 1 <= ang <= 1430:
                add_many(await banidb.get_ang(ang), min_score=None)
                if len([e for e in evidence if e.get("source") in {"BaniDB", "GurbaniNow"}]) < 4:
                    add_many(await gnow.get_ang(ang), min_score=None)

        gurmukhi = claim.quoted_gurbani or (
            GURMUKHI_RE.search(claim.text).group(0) if GURMUKHI_RE.search(claim.text) else None
        )
        search_q = (gurmukhi or claim.text).strip()
        # Only send short Gurmukhi / quote-like strings, never a long English essay.
        if gurmukhi or (search_q and len(search_q.split()) <= 12 and claim.category in SCRIPTURE_CATEGORIES):
            add_many(await banidb.search_fuzzy(search_q[:80], limit=5), min_score=None)
            if len([e for e in evidence if e.get("source") in {"BaniDB", "GurbaniNow"}]) < 3:
                add_many(await gnow.search(search_q[:80], results=8), min_score=None)

    # Keep the most relevant items only; drop a long tail of weak matches.
    evidence.sort(key=lambda e: float(e.get("score") or 0.0), reverse=True)
    return evidence[:8]
