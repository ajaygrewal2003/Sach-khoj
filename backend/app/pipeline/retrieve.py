from __future__ import annotations

import re
from typing import Any

from app.integrations.banidb import BaniDBClient
from app.integrations.gurbaninow import GurbaniNowClient
from app.pipeline.gurbani_topics import scripture_queries_for_claim
from app.schemas import ExtractedClaim
from app.services.knowledge_base import get_knowledge_base, topical_overlap

ANG_RE = re.compile(r"\bang\s*[:#]?\s*(\d{1,4})\b", re.IGNORECASE)
GURMUKHI_RE = re.compile(r"[\u0A00-\u0A7F]{6,}")

SCRIPTURE_CATEGORIES = {"gurbani_misquote", "out_of_context"}

MIN_KEEP_SCORE = 0.30


def _should_search_quoted_scripture(claim: ExtractedClaim) -> bool:
    if claim.quoted_gurbani:
        return True
    if GURMUKHI_RE.search(claim.text or ""):
        return True
    if ANG_RE.search(claim.text or "") or ANG_RE.search(claim.quoted_gurbani or ""):
        return True
    return claim.category in SCRIPTURE_CATEGORIES


def _score_scripture_against_claim(claim_text: str, item: dict[str, Any]) -> dict[str, Any] | None:
    blob = f"{item.get('translation') or ''} {item.get('excerpt') or ''} {item.get('reference') or ''}"
    distinctive, ratio = topical_overlap(claim_text, blob)
    if distinctive < 1 and ratio < 0.12:
        return None
    score = 0.22 + 0.55 * ratio + 0.23 * min(distinctive / 3.0, 1.0)
    return {**item, "score": round(score, 3), "match_reason": "scripture_topic"}


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

    banidb = BaniDBClient()
    gnow = GurbaniNowClient()

    # For every claim, try on-topic Gurbani (short queries only — never the full sentence).
    for sq in await scripture_queries_for_claim(claim.text):
        hits = await banidb.search_for_claim(sq.query, searchtype=sq.searchtype, limit=4)
        scored = [_score_scripture_against_claim(claim.text, h) for h in hits]
        add_many([h for h in scored if h is not None], min_score=0.28)

    if _should_search_quoted_scripture(claim):
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
        if gurmukhi or (search_q and len(search_q.split()) <= 12 and claim.category in SCRIPTURE_CATEGORIES):
            add_many(await banidb.search_fuzzy(search_q[:80], limit=5), min_score=None)
            if len([e for e in evidence if e.get("source") in {"BaniDB", "GurbaniNow"}]) < 3:
                add_many(await gnow.search(search_q[:80], results=8), min_score=None)

    # Prefer known-false and BaniDB, then curated, by score.
    # Cap scripture verses so they accompany, not bury, curated evidence.
    scripture = [e for e in evidence if e.get("source") in {"BaniDB", "GurbaniNow"}]
    rest = [e for e in evidence if e.get("source") not in {"BaniDB", "GurbaniNow"}]
    scripture.sort(key=lambda e: float(e.get("score") or 0.0), reverse=True)
    evidence = rest + scripture[:4]

    def _rank_key(e: dict[str, Any]) -> tuple[int, float]:
        src = e.get("source")
        bucket = 2
        if src == "Known False Claims Index":
            bucket = 0
        elif src in {"BaniDB", "GurbaniNow"}:
            bucket = 1
        return (bucket, -float(e.get("score") or 0.0))

    evidence.sort(key=_rank_key)
    return evidence[:10]
