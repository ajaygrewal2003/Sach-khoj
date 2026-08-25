from __future__ import annotations

import re
from typing import Any

from app.integrations.banidb import BaniDBClient
from app.integrations.gurbaninow import GurbaniNowClient
from app.pipeline.gurbani_topics import scripture_queries_for_claim
from app.pipeline.relevance import (
    ClaimBrief,
    analyze_claim,
    claim_focus_tokens,
    filter_passages_for_claim,
    judge_evidence_for_claim,
    verse_matches_claim,
)
from app.schemas import ExtractedClaim
from app.services.knowledge_base import get_knowledge_base
from app.services.semantic_index import get_semantic_index

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


def _score_scripture_against_claim(
    claim_text: str,
    item: dict[str, Any],
    brief: ClaimBrief | None = None,
) -> dict[str, Any] | None:
    """Lexical prefilter for verses (fallback floor; the judge is the real gate)."""
    blob = f"{item.get('translation') or ''} {item.get('excerpt') or ''}"
    from app.pipeline.relevance import passage_matches_claim

    if not passage_matches_claim(claim_text, blob, brief=brief):
        return None
    overlap = len(claim_focus_tokens(claim_text) & claim_focus_tokens(blob))
    score = 0.45 + 0.20 * min(max(overlap, 1) / 3.0, 1.0)
    return {**item, "score": round(score, 3), "match_reason": "scripture_topic"}


async def _corpus_candidates(
    claim: ExtractedClaim,
    brief: ClaimBrief,
) -> list[dict[str, Any]]:
    """Curated + known-false candidates by MEANING; lexical TF-IDF as fallback."""
    semantic = await get_semantic_index().search(
        brief.expanded_query(claim.text), top_k=10, min_sim=0.25
    )
    if semantic is not None:
        return semantic

    kb = get_knowledge_base()
    category_map = {
        "rehat": "rehat",
        "historical": "history",
        "propaganda": "propaganda",
        "gurbani_misquote": "gurbani",
        "out_of_context": "gurbani",
        "doctrine": "doctrine",
    }
    candidates = kb.match_known_false(claim.text)
    candidates += kb.search(claim.text, limit=6, category=category_map.get(claim.category))
    return candidates


async def retrieve_evidence(
    claim: ExtractedClaim,
    brief: ClaimBrief | None = None,
) -> list[dict[str, Any]]:
    """Stage 3 — gather grounded passages only (no invented citations).

    General flow for ANY claim:
      1. Understand the claim (brief).
      2. Retrieve curated/known-false by meaning.
      3. Retrieve Gurbani via the brief's subject queries.
      4. One general judge gates everything that wasn't explicitly quoted.
    """
    evidence: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    brief = brief or await analyze_claim(claim.text)

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

    add_many(await _corpus_candidates(claim, brief), min_score=0.25)

    banidb = BaniDBClient()
    gnow = GurbaniNowClient()

    # Search Gurbani using the understood subject — never the full claim sentence.
    for sq in await scripture_queries_for_claim(claim.text, brief=brief):
        hits = await banidb.search_for_claim(sq.query, searchtype=sq.searchtype, limit=4)
        scored = [_score_scripture_against_claim(claim.text, h, brief) for h in hits]
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

    # The user explicitly cited these — keep them out of the judge.
    exempt = [
        e for e in evidence if e.get("match_reason") in {"named_ang", "quoted_scripture"}
    ]
    candidates = [
        e for e in evidence if e.get("match_reason") not in {"named_ang", "quoted_scripture"}
    ]

    # ONE general gate over every candidate — curated notes, known-false, verses.
    candidates.sort(key=lambda e: float(e.get("score") or 0.0), reverse=True)
    judged = await judge_evidence_for_claim(claim.text, candidates[:14], brief)

    scripture = [e for e in judged if e.get("source") in {"BaniDB", "GurbaniNow"}]
    rest = [e for e in judged if e.get("source") not in {"BaniDB", "GurbaniNow"}]
    evidence = rest + exempt[:4] + scripture[:3]

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
