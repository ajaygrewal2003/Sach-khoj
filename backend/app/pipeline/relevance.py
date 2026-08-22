"""Claim understanding and verse relevance — for every claim, not one topic.

Pipeline for any input:
1. Understand the claim's real subject (ignore rhetoric like "completely" / "forbids").
2. Search Gurbani with short subject terms (or skip if Gurbani would not discuss it).
3. Keep a verse only if it is about that same subject, in the same sense.
4. Quote only those verses. Wrong Ang is worse than no Ang.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from app.services.knowledge_base import (
    WEAK_SUBJECT_TOKENS,
    content_tokens,
    core_subject_tokens,
    expand_tokens,
)
from app.services.llm import chat_json, embed_texts

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

# Too common to search alone when the claim is not already mapped to a topic.
SKIP_AS_SOLO_QUERY = FOCUS_DROP | {
    "fire",
    "water",
    "earth",
    "air",
    "time",
    "year",
    "years",
    "day",
    "night",
    "body",
    "mind",
    "heart",
    "love",
    "death",
    "name",
    "great",
    "many",
    "human",
    "being",
    "beings",
    "created",
    "creating",
    "century",
    "system",
    "believes",
    "summaries",
    "maryada",
    "according",
    "identity",
    "prove",
    "proves",
    "inherently",
}

# Ambiguous Gurbani English: the verse must also carry the claim's sense of the word.
POLYSEMY_CONTEXT: dict[str, frozenset[str]] = {
    "flesh": frozenset(
        {
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
    ),
    "form": frozenset(
        {
            "formless",
            "idol",
            "image",
            "physical",
            "shape",
            "shapeless",
            "nirankar",
            "worship",
            "statue",
            "murti",
            "feature",
            "features",
        }
    ),
    "amrit": frozenset({"naam", "ambrosial", "nectar", "baptism", "initiation", "khande", "sword", "immortal"}),
}

_WORD_RE = re.compile(r"[\w\u0A00-\u0A7F]+", re.UNICODE)
_GURMUKHI_RE = re.compile(r"[\u0A00-\u0A7F]")

SEMANTIC_DROP_BELOW = 0.14


@dataclass
class ClaimBrief:
    """What the claim is actually about — used for search, keep/drop, and quoting."""

    subject: str
    about: list[str] = field(default_factory=list)
    not_about: list[str] = field(default_factory=list)
    gurbani_relevant: bool = True
    llm_queries: list[dict[str, str]] = field(default_factory=list)
    focus_tokens: set[str] = field(default_factory=set)

    def prompt_block(self) -> str:
        about = ", ".join(self.about) or "(infer from the claim)"
        not_about = ", ".join(self.not_about) or "filler words and unrelated spiritual catchphrases"
        return (
            f"Claim subject: {self.subject}\n"
            f"A relevant verse would discuss: {about}\n"
            f"Do NOT quote verses that are really about: {not_about}"
        )


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
    """True if this string is a safe BaniDB search. LLM queries must not be filler."""
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


def verse_matches_claim(claim_text: str, translation: str = "", excerpt: str = "") -> bool:
    """Hard floor for any claim: same subject, same sense — not a shared filler word."""
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
    return _same_sense(focus, blob)


def _same_sense(focus: set[str], blob: str) -> bool:
    """Drop false-friend matches (flesh=body vs flesh=food, form=shape vs form=idol)."""
    tokens = content_tokens(blob)
    for word, context in POLYSEMY_CONTEXT.items():
        if word not in tokens:
            continue
        if word not in focus and not (focus & context):
            continue
        if not ((tokens & context) - {word}):
            return False
    return True


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


def _heuristic_brief(claim_text: str) -> ClaimBrief:
    focus = claim_focus_tokens(claim_text)
    subject = " ".join(sorted(focus)[:8]) if focus else (claim_text[:80] or "unspecified")
    return ClaimBrief(
        subject=subject,
        about=sorted(focus)[:12],
        not_about=[
            "intensifiers like completely/totally",
            "generic lines about the Lord saving or fulfilling someone",
        ],
        gurbani_relevant=bool(focus),
        llm_queries=[],
        focus_tokens=focus,
    )


async def analyze_claim(claim_text: str) -> ClaimBrief:
    """Understand ANY claim before searching — subject, relevant verse themes, search terms."""
    heuristic = _heuristic_brief(claim_text)
    data = await chat_json(
        (
            "You are a Sikh studies research assistant preparing a Gurbani search. "
            "This must work for ANY claim (diet, caste, history, Rehat, gender, ritual, quotes, novel topics). "
            "Return ONLY JSON: "
            '{"subject": "short topic in 4-10 words", '
            '"about": ["what a relevant Guru Granth verse would actually discuss"], '
            '"not_about": ["false-friend themes the same English word might hit"], '
            '"gurbani_relevant": true, '
            '"queries": [{"q": "eat meat", "lang": "en"}]}. '
            "subject = the real issue, NOT rhetoric (completely, forbids, always, never). "
            "Each q is 1-3 words that would appear IN a verse about that subject. "
            "Prefer concrete nouns and, when useful, Gurmukhi headwords. "
            "Never use filler: completely, totally, forbids, Lord, Guru, saved, fulfilled, Sikh, God. "
            "If Sri Guru Granth Sahib Ji would not discuss this (modern dates, British politics, "
            "census figures), set gurbani_relevant false and queries []."
        ),
        f"Claim:\n{claim_text[:1500]}\nHeuristic focus tokens: {sorted(heuristic.focus_tokens)}",
        max_tokens=500,
    )
    if not data:
        return heuristic

    queries: list[dict[str, str]] = []
    for item in data.get("queries") or []:
        q = (item.get("q") or "").strip()
        lang = (item.get("lang") or "en").lower()
        if not q or len(q.split()) > 3:
            continue
        queries.append({"q": q, "lang": lang})

    about = [str(x).strip() for x in (data.get("about") or []) if str(x).strip()]
    not_about = [str(x).strip() for x in (data.get("not_about") or []) if str(x).strip()]
    return ClaimBrief(
        subject=(data.get("subject") or heuristic.subject)[:160],
        about=about or heuristic.about,
        not_about=not_about or heuristic.not_about,
        gurbani_relevant=bool(data.get("gurbani_relevant", True)),
        llm_queries=queries,
        focus_tokens=heuristic.focus_tokens,
    )


async def understand_claim_subject(claim_text: str) -> dict[str, Any]:
    """Back-compat wrapper used by query planning."""
    brief = await analyze_claim(claim_text)
    return {
        "subject": brief.subject,
        "gurbani_relevant": brief.gurbani_relevant,
        "queries": brief.llm_queries,
        "about": brief.about,
        "not_about": brief.not_about,
    }


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def rerank_verses_semantically(
    claim_text: str,
    verses: list[dict[str, Any]],
    brief: ClaimBrief | None = None,
) -> list[dict[str, Any]]:
    """General semantic gate: drop verses whose meaning is far from the claim subject."""
    if not verses:
        return []
    subject = brief.subject if brief else claim_text[:200]
    query = f"Subject: {subject}. Claim: {claim_text[:500]}"
    verse_texts = [(v.get("translation") or v.get("excerpt") or "")[:500] for v in verses]
    vectors = await embed_texts([query, *verse_texts])
    if not vectors or len(vectors) != len(verses) + 1:
        return verses
    qvec = vectors[0]
    scored: list[tuple[float, dict[str, Any]]] = []
    for verse, vec in zip(verses, vectors[1:], strict=True):
        sim = _cosine(qvec, vec)
        item = {**verse, "semantic_score": round(sim, 3)}
        if sim >= SEMANTIC_DROP_BELOW:
            scored.append((sim, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


async def judge_verses_for_claim(
    claim_text: str,
    verses: list[dict[str, Any]],
    brief: ClaimBrief | None = None,
) -> list[dict[str, Any]]:
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
    brief = brief or _heuristic_brief(claim_text)
    data = await chat_json(
        (
            "You are a careful Gurbani research assistant. This filter applies to EVERY kind of claim. "
            "Keep a verse ONLY if a knowledgeable reader would cite it for THIS claim's subject, "
            "in the same sense of the words. "
            "Reject: filler-word hits (completely, totally, Lord, saved, fulfilled); "
            "wrong sense (flesh as the body vs flesh as food; form as shape vs formless God); "
            "and any other different topic. "
            'Return JSON {"keep_ids": ["id", ...]}.'
        ),
        f"{brief.prompt_block()}\nClaim: {claim_text[:1500]}\nVerses: {compact}",
        max_tokens=400,
    )
    if not data:
        return lexical
    keep = {str(x) for x in (data.get("keep_ids") or [])}
    if not keep:
        return []
    return [v for v in lexical if str(v.get("id")) in keep]
