from __future__ import annotations

from dataclasses import dataclass

from app.services.knowledge_base import content_tokens, expand_tokens

# BaniDB: searchtype 2 ≈ Gurmukhi word, searchtype 3 ≈ English translation.
# Queries must be short; never send a full English sentence to the API.


@dataclass(frozen=True)
class ScriptureQuery:
    query: str
    searchtype: int  # 2 gurmukhi, 3 english
    topic: str


@dataclass(frozen=True)
class TopicSpec:
    id: str
    tokens: frozenset[str]
    distinctive: frozenset[str]
    english: tuple[str, ...]
    gurmukhi: tuple[str, ...]


TOPICS: tuple[TopicSpec, ...] = (
    TopicSpec(
        id="nirankar",
        tokens=frozenset(
            {
                "form",
                "forms",
                "formless",
                "physical",
                "idol",
                "idols",
                "murti",
                "statue",
                "nirankar",
                "worship",
                "worshipped",
                "worships",
                "god",
                "onkar",
                "image",
            }
        ),
        distinctive=frozenset(
            {"form", "forms", "formless", "physical", "idol", "idols", "murti", "statue", "nirankar", "image"}
        ),
        english=("formless", "idol", "form"),
        gurmukhi=("ਨਿਰੰਕਾਰ",),
    ),
    TopicSpec(
        id="ritual_mukti",
        tokens=frozenset(
            {
                "ritual",
                "rituals",
                "mukti",
                "liberation",
                "ceremony",
                "ceremonies",
                "pilgrimage",
                "fasting",
                "tirath",
            }
        ),
        distinctive=frozenset(
            {"ritual", "rituals", "mukti", "liberation", "ceremony", "pilgrimage", "fasting", "tirath"}
        ),
        english=("pilgrimage", "fasting", "Naam"),
        gurmukhi=("ਨਾਮੁ",),
    ),
    TopicSpec(
        id="naam",
        tokens=frozenset({"naam", "simran", "japna", "meditation", "remembrance"}),
        distinctive=frozenset({"naam", "simran", "japna"}),
        english=("Naam",),
        gurmukhi=("ਨਾਮੁ",),
    ),
    TopicSpec(
        id="caste",
        tokens=frozenset({"caste", "janeu", "varna"}),
        distinctive=frozenset({"caste", "janeu"}),
        english=("caste",),
        gurmukhi=(),
    ),
)


def scripture_queries_for(claim_text: str) -> list[ScriptureQuery]:
    """Map an English/Gurmukhi claim onto short BaniDB search queries."""
    tokens = expand_tokens(content_tokens(claim_text))
    queries: list[ScriptureQuery] = []
    seen: set[tuple[str, int]] = set()
    for topic in TOPICS:
        hit = tokens & topic.tokens
        if not hit:
            continue
        if not (hit & topic.distinctive) and len(hit) < 2:
            continue
        for q in topic.english:
            key = (q, 3)
            if key not in seen:
                seen.add(key)
                queries.append(ScriptureQuery(query=q, searchtype=3, topic=topic.id))
        for q in topic.gurmukhi:
            key = (q, 2)
            if key not in seen:
                seen.add(key)
                queries.append(ScriptureQuery(query=q, searchtype=2, topic=topic.id))
    return queries[:6]
