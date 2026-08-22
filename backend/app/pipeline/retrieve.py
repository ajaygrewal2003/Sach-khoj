from __future__ import annotations

import re
from typing import Any

from app.integrations.banidb import BaniDBClient
from app.integrations.gurbaninow import GurbaniNowClient
from app.pipeline.gurbani_topics import scripture_queries_for_claim
from app.pipeline.relevance import (
    claim_focus_tokens,
    filter_verses_for_claim,
    judge_verses_for_claim,
    verse_matches_claim,
)
from app.schemas import ExtractedClaim
from app.services.knowledge_base import get_knowledge_base

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
    """Keep a verse only when it shares the claim's distinctive subject."""
    if not verse_matches_claim(
        claim_text,
        translation=str(item.get("translation") or ""),
        excerpt=str(item.get("excerpt") or ""),
    ):
        return None
    overlap = len(
        claim_focus_tokens(claim_text)
        & claim_focus_tokens(f"{item.get('translation') or ''} {item.get('excerpt') or ''}")
    )
    score = 0.45 + 0.20 * min(max(overlap, 1) / 3.0, 1.0)
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

    # Search Gurbani using subject queries only — never the full claim sentence.
    for sq in await scripture_queries_for_claim(claim.text):
        hits = await banidb.search_for_claim(sq.query, searchtype=sq.searchtype, limit=4)
        scored = [_score_scripture_against_claim(claim.text, h) for h in hits]
        add_many([h for h in scored if h is not None], min_score=0.28)

    if _should_search_quoted_scripture(claim):
        ang_match = ANG_RE.search(claim.text) or ANG_RE.search(claim.quoted_gurbani or "")
        if ang_match:
            ang = int(ang_match.group(1))
            if 1 <= ang <= 1430:
                ang_hits = await banidb.get_ang(ang)
                keep_named_ang = [
                    {**h, "match_reason": "named_ang", "score": h.get("score") or 0.55} for h in ang_hits[:6]
                ]
                add_many(keep_named_ang, min_score=None)
                if len([e for e in evidence if e.get("source") in {"BaniDB", "GurbaniNow"}]) < 4:
                    extra_ang = await gnow.get_ang(ang)
                    add_many(
                        [{**h, "match_reason": "named_ang"} for h in extra_ang],
                        min_score=None,
                    )

        gurmukhi = claim.quoted_gurbani or (
            GURMUKHI_RE.search(claim.text).group(0) if GURMUKHI_RE.search(claim.text) else None
        )
        search_q = (gurmukhi or claim.text).strip()
        if gurmukhi or (search_q and len(search_q.split()) <= 12 and claim.category in SCRIPTURE_CATEGORIES):
            quoted_hits = await banidb.search_fuzzy(search_q[:80], limit=5)
            add_many(
                [{**h, "match_reason": "quoted_scripture"} for h in quoted_hits],
                min_score=None,
            )
            if len([e for e in evidence if e.get("source") in {"BaniDB", "GurbaniNow"}]) < 3:
                extra = await gnow.search(search_q[:80], results=8)
                add_many(
                    [{**h, "match_reason": "quoted_scripture"} for h in extra],
                    min_score=None,
                )

    scripture = [e for e in evidence if e.get("source") in {"BaniDB", "GurbaniNow"}]
    rest = [e for e in evidence if e.get("source") not in {"BaniDB", "GurbaniNow"}]
    named = [
        e
        for e in scripture
        if e.get("match_reason") in {"named_ang", "quoted_scripture"}
    ]
    topical = [
        e
        for e in scripture
        if e.get("match_reason") not in {"named_ang", "quoted_scripture"}
    ]
    topical = filter_verses_for_claim(claim.text, topical)
    topical.sort(key=lambda e: float(e.get("score") or 0.0), reverse=True)
    topical = await judge_verses_for_claim(claim.text, topical[:8])
    evidence = rest + named[:4] + topical[:3]

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
