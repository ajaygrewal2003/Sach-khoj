"""Claim understanding and verse relevance.

Retrieval used to search leftover English words from the claim ("completely",
"forbids", "Lord") and then quote whatever BaniDB returned. This module is the
gate: understand the claim's subject first, search only for that subject, and
keep a verse only if it is actually about the same subject.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.knowledge_base import (
    WEAK_SUBJECT_TOKENS,
    content_tokens,
    core_subject_tokens,
    expand_tokens,
)
from app.services.llm import chat_json

# Rhetoric / intensifiers / generic Sikh vocabulary. Never use these as BaniDB queries.
FILLER_QUERY_TOKENS = {
    "sikh",
    "sikhi",
    "sikhism",
    "sikhs",
    "teach",
    "teaches",
    "teaching",
    "taught",
    "claim",
    "claims",
    "people",
    "person",
    "religion",
    "religious",
    "specific",
    "according",
    "says",
    "said",
    "must",
    "only",
    "true",
    "false",
    "always",
    "never",
    "everyone",
    "anyone",
    "completely",
    "totally",
    "entirely",
    "fully",
    "forbids",
    "forbid",
    "forbidden",
    "prohibits",
    "prohibit",
    "emphasize",
    "emphasizes",
    "lord",
    "one",
    "saved",
    "fulfilled",
    "comforted",
    "meditating",
    "meditation",
    "master",
    "himself",
    "myself",
    "yourself",
    "itself",
    "divine",
    "god",
    "waheguru",
    "guru",
    "gurus",
    "gurbani",
    "bani",
    "shabad",
    "granth",
    "truth",
    "word",
    "holy",
    "sacred",
    "spiritual",
    "practice",
    "practices",
}

# Verbs and generic nouns that should not, by themselves, justify keeping a verse.
FOCUS_DROP = WEAK_SUBJECT_TOKENS | FILLER_QUERY_TOKENS | {
    "eat",
    "eats",
    "ate",
    "eaten",
    "eating",
    "food",
    "drink",
    "living",
    "life",
    "live",
    "lives",
    "world",
    "way",
    "means",
    "thing",
    "things",
    "make",
    "made",
    "given",
    "give",
    "come",
    "comes",
    "go",
    "goes",
    "take",
    "takes",
    "taken",
    "keep",
    "keeps",
    "kept",
    "need",
    "needs",
    "allow",
    "allows",
    "allowed",
    "require",
    "requires",
    "required",
    "ban",
    "bans",
    "banned",
    "restriction",
    "restrictions",
    "narrative",
    "idea",
    "core",
    "teachings",
}


_WORD_RE = re.compile(r"[\w\u0A00-\u0A7F]+", re.UNICODE)
_GURMUKHI_RE = re.compile(r"[\u0A00-\u0A7F]")


def has_gurmukhi(text: str) -> bool:
    return bool(_GURMUKHI_RE.search(text or ""))


def claim_focus_tokens(text: str) -> set[str]:
    """Noun-like subject of the claim — what verses must be about."""
    core = expand_tokens(core_subject_tokens(text))
    focus = core - FOCUS_DROP
    return focus if focus else core


def is_filler_query(query: str) -> bool:
    """True for empty, overlong, or rhetoric-only searches (completely, forbids, Lord)."""
    query = (query or "").strip()
    if not query or len(query) > 40:
        return True
    if has_gurmukhi(query):
        return False
    words = [w.lower() for w in _WORD_RE.findall(query) if len(w) > 1]
    if not words:
        return True
    return all(w in FILLER_QUERY_TOKENS for w in words)


def is_usable_search_query(query: str, *, claim_focus: set[str], require_focus: bool = True) -> bool:
    """True if this string is a safe BaniDB search. LLM queries must share the claim's subject."""
    query = (query or "").strip()
    if is_filler_query(query):
        return False
    if has_gurmukhi(query) or not require_focus:
        return True
    words = [w.lower() for w in _WORD_RE.findall(query) if len(w) > 1]
    q_tokens = expand_tokens(core_subject_tokens(query) or set(words))
    if claim_focus and not (q_tokens & claim_focus) and not (set(words) & claim_focus):
        return False
    return True


DIETARY_CONTEXT = {
    "eat",
    "eats",
    "eating",
    "ate",
    "eaten",
    "meat",
    "animal",
    "animals",
    "kutha",
    "halal",
    "jhatka",
    "fish",
    "deer",
    "goat",
    "killed",
    "slaughter",
    "vegetarian",
}


def verse_matches_claim(claim_text: str, translation: str = "", excerpt: str = "") -> bool:
    """Hard floor: verse must share the claim's distinctive subject, not a filler word."""
    blob = f"{translation or ''} {excerpt or ''}"
    if not blob.strip():
        return False
    claim_raw = core_subject_tokens(claim_text) - FOCUS_DROP
    if not claim_raw:
        claim_raw = core_subject_tokens(claim_text)
    focus = expand_tokens(claim_raw)
    verse_core = expand_tokens(core_subject_tokens(blob))
    if not (focus & verse_core):
        return False
    # Diet claims: 'flesh' in Gurbani often means the body, not food. Require eating/meat context.
    if _is_diet_claim(focus):
        return _diet_context_ok(focus, blob)
    return True


def _is_diet_claim(focus: set[str]) -> bool:
    return bool(focus & {"meat", "flesh", "kutha", "jhatka", "vegetarian", "maas", "halal"})


def _diet_context_ok(focus: set[str], blob: str) -> bool:
    if not _is_diet_claim(focus):
        return True
    tokens = content_tokens(blob)
    return bool(tokens & DIETARY_CONTEXT)


def filter_verses_for_claim(claim_text: str, verses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop verses that only share rhetoric (completely, Lord, saved, fulfilled)."""
    kept: list[dict[str, Any]] = []
    for verse in verses:
        if verse_matches_claim(
            claim_text,
            translation=str(verse.get("translation") or ""),
            excerpt=str(verse.get("excerpt") or ""),
        ):
            kept.append(verse)
    return kept


async def understand_claim_subject(claim_text: str) -> dict[str, Any]:
    """Ask the model what the claim is actually about before searching Gurbani."""
    focus = sorted(claim_focus_tokens(claim_text))
    data = await chat_json(
        (
            "You understand claims about Sikhism so we can search Sri Guru Granth Sahib Ji. "
            "Return ONLY JSON: "
            '{"subject": "3-8 word topic", "gurbani_relevant": true, '
            '"queries": [{"q": "flesh", "lang": "en"}]}. '
            "subject = the real topic (diet/meat, caste, formless God, pilgrimage), "
            "NOT the claim's rhetoric (completely, forbids, always). "
            "Each q is 1-3 words that would appear IN a verse about that topic. "
            "Prefer concrete nouns (meat, flesh, caste, formless, pilgrimage, woman) "
            "and Gurmukhi headwords (ਮਾਸ, ਨਿਰੰਕਾਰ, ਜਾਤਿ, ਤੀਰਥ, ਇਸਤ੍ਰੀ) when useful. "
            "Never use filler: completely, totally, forbids, Lord, Guru, saved, fulfilled, Sikh. "
            "If Gurbani would not discuss this (modern history, dates, British politics), "
            'set gurbani_relevant false and queries [].'
        ),
        f"Claim:\n{claim_text[:1500]}\nFocus tokens already detected: {focus}",
        max_tokens=400,
    )
    if not data:
        return {
            "subject": " ".join(focus[:8]) if focus else claim_text[:80],
            "gurbani_relevant": bool(focus),
            "queries": [],
        }
    queries = []
    for item in data.get("queries") or []:
        q = (item.get("q") or "").strip()
        lang = (item.get("lang") or "en").lower()
        if not q or len(q.split()) > 3:
            continue
        queries.append({"q": q, "lang": lang})
    return {
        "subject": (data.get("subject") or " ".join(focus[:8]) or "unspecified")[:120],
        "gurbani_relevant": bool(data.get("gurbani_relevant", True)),
        "queries": queries,
    }


async def judge_verses_for_claim(claim_text: str, verses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """LLM keep/drop on top of the lexical floor. Cannot override a lexical reject."""
    lexical = filter_verses_for_claim(claim_text, verses)
    if not lexical:
        return []
    compact = [
        {
            "id": v.get("id"),
            "reference": v.get("reference"),
            "translation": (v.get("translation") or "")[:280],
        }
        for v in lexical
    ]
    focus = sorted(claim_focus_tokens(claim_text))
    data = await chat_json(
        (
            "You are a careful Gurbani research assistant. "
            "Keep a verse ONLY if a knowledgeable reader would use it to discuss THIS claim's subject. "
            "Reject verses that merely share a filler/intensifier (completely, totally, Lord, saved, "
            "fulfilled, comforted, meditating) or that are about a different topic. "
            'Return JSON {"keep_ids": ["id", ...]}.'
        ),
        f"Claim: {claim_text[:1500]}\nSubject tokens: {focus}\nVerses: {compact}",
        max_tokens=400,
    )
    if not data:
        return lexical
    keep = {str(x) for x in (data.get("keep_ids") or [])}
    if not keep:
        return []
    return [v for v in lexical if str(v.get("id")) in keep]
