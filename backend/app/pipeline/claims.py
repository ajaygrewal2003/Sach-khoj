from __future__ import annotations

import re
from typing import Any

from app.schemas import ClaimCategory, ExtractedClaim
from app.services.llm import CLAIM_SCHEMA_HINT, chat_json

GURMUKHI_RE = re.compile(r"[\u0A00-\u0A7F]{8,}")
ANG_RE = re.compile(r"\bang\s*[:#]?\s*(\d{1,4})\b", re.IGNORECASE)
GURU_CLAIM_RE = re.compile(
    r"(guru\s+(nanak|angad|amar\s*das|ram\s*das|arjan|hargobind|har\s*rai|har\s*krishan|tegh?\s*bahadur|gobind)\b|"
    r"ਗੁਰੂ\s+ਨਾਨਕ|ਸ੍ਰੀ\s+ਗੁਰੂ\s+ਗ੍ਰੰਥ)",
    re.IGNORECASE,
)
REHAT_RE = re.compile(r"\b(rehat|maryada|khalsa|amrit|kes|kesh|kirpan|kangha|kara|kachera|5\s*k)\b", re.IGNORECASE)
DOCTRINE_RE = re.compile(
    r"\b(rituals?|mukti|liberation|salvation|naam|nam simran|hukam|pilgrimage|tirath|"
    r"nitnem|janeu|karam\s*kand|idol|murti|formless|nirankar|physical\s+form|"
    r"worshipped|worship|meat|vegetarian|kutha|jhatka)\b",
    re.IGNORECASE,
)
HISTORY_RE = re.compile(
    r"\b(was\s+born|founded|invented|never\s+existed|converted\s+to|british\s+created|"
    r"1947|1984|operation\s+blue\s+star|panjab|punjab)\b",
    re.IGNORECASE,
)


async def extract_claims(text: str, *, language_hint: str | None = None) -> list[ExtractedClaim]:
    text = (text or "").strip()
    if not text:
        return []

    llm_claims = await _llm_extract(text, language_hint=language_hint)
    if llm_claims:
        return llm_claims
    return _heuristic_extract(text)


async def _llm_extract(text: str, *, language_hint: str | None) -> list[ExtractedClaim]:
    system = (
        "You extract atomic, checkable factual claims about Sikhism, Gurbani, Sikh history, "
        "and Rehat Maryada from social posts and articles. "
        + CLAIM_SCHEMA_HINT
    )
    user = f"Language hint: {language_hint or 'auto'}\n\nContent:\n{text[:8000]}"
    data = await chat_json(system, user)
    if not data:
        return []

    claims: list[ExtractedClaim] = []
    for item in data.get("claims") or []:
        claim_text = (item.get("text") or "").strip()
        if not claim_text:
            continue
        category = _normalize_category(item.get("category"))
        quoted = item.get("quoted_gurbani") or None
        claims.append(ExtractedClaim(text=claim_text, category=category, quoted_gurbani=quoted))
    return claims[:12]


def _heuristic_extract(text: str) -> list[ExtractedClaim]:
    """Fallback claim splitter when no LLM key is configured."""
    # Prefer sentence-ish splits; keep Gurmukhi blocks intact
    chunks = re.split(r"(?<=[।.?!\n])\s+", text)
    claims: list[ExtractedClaim] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if len(chunk) < 25:
            continue
        if not _looks_checkable(chunk):
            continue
        category = _infer_category(chunk)
        gurmukhi = None
        match = GURMUKHI_RE.search(chunk)
        if match:
            gurmukhi = match.group(0)
        claims.append(ExtractedClaim(text=chunk[:500], category=category, quoted_gurbani=gurmukhi))
        if len(claims) >= 8:
            break

    if not claims and len(text) >= 20:
        claims.append(
            ExtractedClaim(
                text=text[:500],
                category=_infer_category(text),
                quoted_gurbani=(GURMUKHI_RE.search(text).group(0) if GURMUKHI_RE.search(text) else None),
            )
        )
    return claims


def _looks_checkable(text: str) -> bool:
    if GURMUKHI_RE.search(text) or ANG_RE.search(text) or GURU_CLAIM_RE.search(text):
        return True
    if REHAT_RE.search(text) or HISTORY_RE.search(text):
        return True
    if DOCTRINE_RE.search(text):
        return True
    # Assertive factual phrasing
    return bool(re.search(r"\b(said|wrote|teaches|proves|means|is\s+from|quotes?)\b", text, re.I))


def _infer_category(text: str) -> ClaimCategory:
    if GURMUKHI_RE.search(text) or ANG_RE.search(text) or re.search(r"\b(misquot|fabricat|fake\s+shabad)\b", text, re.I):
        return "gurbani_misquote"
    if DOCTRINE_RE.search(text):
        return "doctrine"
    if REHAT_RE.search(text):
        return "rehat"
    if HISTORY_RE.search(text) or GURU_CLAIM_RE.search(text):
        return "historical"
    if re.search(r"\b(terror|anti.?national|hindu\s+sect|not\s+a\s+religion)\b", text, re.I):
        return "propaganda"
    return "other"


def _normalize_category(value: Any) -> ClaimCategory:
    allowed = {
        "gurbani_misquote",
        "out_of_context",
        "historical",
        "rehat",
        "doctrine",
        "propaganda",
        "other",
    }
    if isinstance(value, str) and value in allowed:
        return value  # type: ignore[return-value]
    return "other"
