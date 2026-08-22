from __future__ import annotations

import re
from typing import Any

from app.integrations.banidb import BaniDBClient
from app.integrations.gurbaninow import GurbaniNowClient
from app.schemas import ExtractedClaim
from app.services.knowledge_base import get_knowledge_base

ANG_RE = re.compile(r"\bang\s*[:#]?\s*(\d{1,4})\b", re.IGNORECASE)
GURMUKHI_RE = re.compile(r"[\u0A00-\u0A7F]{6,}")


async def retrieve_evidence(claim: ExtractedClaim) -> list[dict[str, Any]]:
    """Stage 3 — gather grounded passages only (no invented citations)."""
    evidence: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def add_many(items: list[dict[str, Any]]) -> None:
        for item in items:
            eid = item.get("id")
            if not eid or eid in seen_ids:
                continue
            seen_ids.add(eid)
            evidence.append(item)

    kb = get_knowledge_base()
    add_many(kb.match_known_false(claim.text))

    # Category-aware curated retrieval
    category_map = {
        "rehat": "rehat",
        "historical": "history",
        "propaganda": "propaganda",
        "gurbani_misquote": "gurbani",
        "out_of_context": "gurbani",
    }
    curated_cat = category_map.get(claim.category)
    add_many(kb.search(claim.text, limit=4, category=curated_cat))

    query = (claim.quoted_gurbani or claim.text).strip()
    banidb = BaniDBClient()
    gnow = GurbaniNowClient()

    # Ang-specific lookups
    ang_match = ANG_RE.search(claim.text) or (ANG_RE.search(claim.quoted_gurbani or ""))
    if ang_match:
        ang = int(ang_match.group(1))
        if 1 <= ang <= 1430:
            add_many(await banidb.get_ang(ang))
            if len(evidence) < 6:
                add_many(await gnow.get_ang(ang))

    # Gurbani / quote search
    needs_gurbani = claim.category in {"gurbani_misquote", "out_of_context", "other"} or bool(
        claim.quoted_gurbani or GURMUKHI_RE.search(claim.text)
    )
    if needs_gurbani and query:
        # Prefer shorter Gurmukhi snippets for search APIs
        gurmukhi = claim.quoted_gurbani or (GURMUKHI_RE.search(claim.text).group(0) if GURMUKHI_RE.search(claim.text) else None)
        search_q = gurmukhi or query[:80]
        add_many(await banidb.search_fuzzy(search_q, limit=5))
        if len([e for e in evidence if e.get("source") in {"BaniDB", "GurbaniNow"}]) < 3:
            add_many(await gnow.search(search_q, results=8))

    # Historical/rehat already covered by curated; add a broader search if sparse
    if len(evidence) < 3:
        add_many(kb.search(claim.text, limit=5))

    return evidence[:12]
