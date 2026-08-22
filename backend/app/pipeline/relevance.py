"""Claim understanding and evidence relevance — general, for ANY claim.

The intelligence lives in two general mechanisms, not topic lists:

1. `analyze_claim` — the model reads the claim and produces a ClaimBrief:
   the real subject, what relevant sources would discuss, false-friend
   senses to avoid, and search terms (synonyms/related concepts). This works
   for alcohol, meat, caste, history, or a topic nobody anticipated.
2. `judge_evidence_for_claim` — one general keep/drop judge that scores
   EVERY candidate evidence item (curated note, known-false pattern, verse)
   against the brief.

The token heuristics at the top of this file are a degraded FALLBACK for
running without an API key (tests/CI). They are not the primary path and
should not be extended topic by topic.
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

# ---------------------------------------------------------------------------
# Heuristic fallback vocabulary (no-LLM mode only)
# ---------------------------------------------------------------------------

# Rhetoric / intensifiers / generic Sikh vocabulary. Never useful as searches.
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
    "spiritually",
    "practice",
    "practices",
}

# Verbs and generic nouns that cannot define a subject by themselves.
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
    "harmful",
}

# Too common to search alone when nothing better is available.
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

# Generic religious boilerplate: sharing only these words is not a subject match.
BOILERPLATE_TOKENS = {
    "sikh",
    "sikhi",
    "sikhism",
    "sikhs",
    "guru",
    "gurus",
    "gurbani",
    "bani",
    "rehat",
    "maryada",
    "discipline",
    "amritdhari",
    "khalsa",
}

# Ambiguous Gurbani English: the verse must also carry the claim's sense.
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
    "amrit": frozenset(
        {"naam", "ambrosial", "nectar", "baptism", "initiation", "khande", "sword", "immortal"}
    ),
}

_WORD_RE = re.compile(r"[\w\u0A00-\u0A7F]+", re.UNICODE)
_GURMUKHI_RE = re.compile(r"[\u0A00-\u0A7F]")


def has_gurmukhi(text: str) -> bool:
    return bool(_GURMUKHI_RE.search(text or ""))


def claim_focus_tokens(text: str) -> set[str]:
    """Noun-like subject of the claim — heuristic fallback."""
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
    """True if this string is a safe BaniDB search."""
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


# ---------------------------------------------------------------------------
# ClaimBrief — the model's understanding of the claim
# ---------------------------------------------------------------------------


@dataclass
class ClaimBrief:
    """What the claim is actually about — drives search, keep/drop, and quoting."""

    subject: str
    about: list[str] = field(default_factory=list)
    not_about: list[str] = field(default_factory=list)
    gurbani_relevant: bool = True
    llm_queries: list[dict[str, str]] = field(default_factory=list)
    # Model-proposed synonyms / related concepts (alcohol→intoxicants/wine, …).
    search_terms: list[str] = field(default_factory=list)
    focus_tokens: set[str] = field(default_factory=set)

    def prompt_block(self) -> str:
        about = ", ".join(self.about) or "(infer from the claim)"
        not_about = ", ".join(self.not_about) or "filler words and unrelated spiritual catchphrases"
        terms = ", ".join(self.search_terms) or "(none)"
        return (
            f"Claim subject: {self.subject}\n"
            f"A relevant source would discuss: {about}\n"
            f"Related terms: {terms}\n"
            f"Do NOT use material that is really about: {not_about}"
        )

    def expanded_query(self, claim_text: str) -> str:
        """Claim plus related concepts — for meaning-based corpus retrieval."""
        extras = " ".join([*self.search_terms, *self.about])
        return f"{claim_text} {self.subject} {extras}".strip()

    def effective_focus(self) -> set[str]:
        """Subject tokens including model-proposed related nouns (general)."""
        base = set(self.focus_tokens)
        for phrase in [self.subject, *self.search_terms, *self.about]:
            base |= expand_tokens(core_subject_tokens(phrase))
        trimmed = base - FOCUS_DROP
        return trimmed if trimmed else base


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
        search_terms=[],
        focus_tokens=focus,
    )


async def analyze_claim(claim_text: str) -> ClaimBrief:
    """Understand ANY claim before searching — the general entry point."""
    heuristic = _heuristic_brief(claim_text)
    data = await chat_json(
        (
            "You prepare research for fact-checking ONE claim about Sikhi. "
            "It may be about anything: scripture, Rehat, history, diet, alcohol, gender, "
            "politics, customs, or a topic nobody anticipated. If the input is a question, "
            "treat it as the factual claim being asked about. "
            "Return ONLY JSON: "
            '{"subject": "the real topic in 4-10 words", '
            '"about": ["what a genuinely relevant source (Gurbani verse, Rehat clause, history note) would discuss"], '
            '"not_about": ["false-friend themes the same words might wrongly match"], '
            '"search_terms": ["synonyms and related concepts, e.g. alcohol -> intoxicants, wine, liquor"], '
            '"gurbani_relevant": true, '
            '"queries": [{"q": "wine", "lang": "en"}]}. '
            "subject = the real issue, NOT rhetoric (completely, forbids, always, never). "
            "queries are 1-3 word strings likely to appear IN a Guru Granth Sahib verse about "
            "this subject (concrete nouns; Gurmukhi headwords welcome). "
            "Never use filler as a query: completely, totally, forbids, Lord, Guru, saved, "
            "fulfilled, Sikh, God. "
            "gurbani_relevant=false when scripture would not discuss it "
            "(modern dates, British politics, census figures, org procedures)."
        ),
        f"Claim:\n{claim_text[:1500]}",
        max_tokens=600,
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
    search_terms = [str(x).strip() for x in (data.get("search_terms") or []) if str(x).strip()][:12]
    return ClaimBrief(
        subject=(data.get("subject") or heuristic.subject)[:160],
        about=about or heuristic.about,
        not_about=not_about or heuristic.not_about,
        gurbani_relevant=bool(data.get("gurbani_relevant", True)),
        llm_queries=queries,
        search_terms=search_terms,
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


# ---------------------------------------------------------------------------
# Lexical fallback gate (no-LLM mode) — general rules, not topic rules
# ---------------------------------------------------------------------------


def passage_matches_claim(
    claim_text: str,
    passage: str,
    brief: ClaimBrief | None = None,
) -> bool:
    """Fallback gate: passage must share the claim's distinctive subject, same sense."""
    blob = (passage or "").strip()
    if not blob:
        return False
    if brief is not None:
        focus = brief.effective_focus()
    else:
        claim_raw = core_subject_tokens(claim_text) - FOCUS_DROP
        if not claim_raw:
            claim_raw = core_subject_tokens(claim_text)
        focus = expand_tokens(claim_raw)
    if not focus:
        return False
    passage_core = expand_tokens(core_subject_tokens(blob))
    meaningful = (focus & passage_core) - BOILERPLATE_TOKENS
    if not meaningful:
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


def verse_matches_claim(claim_text: str, translation: str = "", excerpt: str = "") -> bool:
    """Fallback verse gate: same subject, same sense — not a shared filler word."""
    return passage_matches_claim(claim_text, f"{translation or ''} {excerpt or ''}")


def _item_text(item: dict[str, Any]) -> str:
    blob = (
        f"{item.get('reference') or ''} {item.get('excerpt') or ''} "
        f"{item.get('translation') or ''} {item.get('category') or ''}"
    )
    if item.get("source") == "Known False Claims Index":
        meta = item.get("meta") or {}
        blob = f"{blob} {meta.get('claim_pattern') or ''} {meta.get('explanation') or ''}"
    return blob


def filter_passages_for_claim(
    claim_text: str,
    items: list[dict[str, Any]],
    brief: ClaimBrief | None = None,
) -> list[dict[str, Any]]:
    """Fallback filter over any evidence rows."""
    return [item for item in items if passage_matches_claim(claim_text, _item_text(item), brief=brief)]


def filter_verses_for_claim(claim_text: str, verses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fallback filter for verses only (kept for tests/back-compat)."""
    return filter_passages_for_claim(claim_text, verses)


# ---------------------------------------------------------------------------
# General judge — the primary gate for every evidence item, any topic
# ---------------------------------------------------------------------------


async def judge_evidence_for_claim(
    claim_text: str,
    items: list[dict[str, Any]],
    brief: ClaimBrief | None = None,
) -> list[dict[str, Any]]:
    """One general keep/drop over ALL candidate evidence (notes, patterns, verses).

    LLM decides relevance from meaning. Without a key, falls back to the
    lexical subject gate. Kept items are marked judged=True.
    """
    if not items:
        return []
    brief = brief or _heuristic_brief(claim_text)

    compact = [
        {
            "id": item.get("id"),
            "source": item.get("source"),
            "reference": item.get("reference"),
            "text": _item_text(item)[:320],
        }
        for item in items
    ]
    data = await chat_json(
        (
            "You are gating evidence for a fact-check about Sikhi. "
            "This applies to ANY claim on ANY topic. "
            "KEEP an item only if it directly supports, refutes, or contextualizes THIS claim's "
            "actual subject — a careful researcher would cite it for this claim. "
            "DROP items that merely share filler words (completely, totally, Lord, saved, "
            "fulfilled), share only generic Sikh vocabulary (Sikh, Guru, Rehat Maryada), use a "
            "word in a different sense, or address a different topic entirely "
            "(e.g. a meat/diet note is NOT evidence about alcohol; an education note is NOT "
            "evidence about meat). "
            'Return ONLY JSON {"keep_ids": ["id", ...]}. Keep nothing if nothing is on-topic.'
        ),
        f"{brief.prompt_block()}\nClaim: {claim_text[:1500]}\nCandidates: {compact}",
        max_tokens=500,
    )
    if data is None:
        kept = filter_passages_for_claim(claim_text, items, brief=brief)
    else:
        keep = {str(x) for x in (data.get("keep_ids") or [])}
        kept = [item for item in items if str(item.get("id")) in keep]
    return [{**item, "judged": True} for item in kept]


async def judge_verses_for_claim(
    claim_text: str,
    verses: list[dict[str, Any]],
    brief: ClaimBrief | None = None,
) -> list[dict[str, Any]]:
    """Back-compat wrapper: judge scripture rows with the general judge."""
    lexical_floor = filter_passages_for_claim(claim_text, verses, brief=brief)
    if not lexical_floor and brief is not None and brief.search_terms:
        # The model's related terms may legitimately match where claim words don't.
        lexical_floor = verses
    if not lexical_floor:
        return []
    return await judge_evidence_for_claim(claim_text, lexical_floor, brief)


# ---------------------------------------------------------------------------
# Semantic similarity utilities
# ---------------------------------------------------------------------------

SEMANTIC_DROP_BELOW = 0.14


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
    """Semantic sanity gate: drop items whose meaning is far from the claim subject."""
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
