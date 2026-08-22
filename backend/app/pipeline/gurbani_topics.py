from __future__ import annotations

from dataclasses import dataclass

from app.pipeline.relevance import (
    claim_focus_tokens,
    has_gurmukhi,
    is_usable_search_query,
    understand_claim_subject,
)
from app.services.knowledge_base import expand_tokens

# BaniDB: searchtype 2 ≈ Gurmukhi word, searchtype 3 ≈ English translation.
# Queries must be short; never send a full English sentence or filler word to the API.


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


# High-precision boosts when a claim clearly hits a known theme.
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
                "image",
            }
        ),
        distinctive=frozenset(
            {"form", "forms", "formless", "physical", "idol", "idols", "murti", "statue", "nirankar", "image"}
        ),
        english=("formless", "idol"),
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
        english=("pilgrimage", "fasting"),
        gurmukhi=("ਤੀਰਥ",),
    ),
    TopicSpec(
        id="naam",
        tokens=frozenset({"naam", "simran", "japna", "remembrance"}),
        distinctive=frozenset({"naam", "simran", "japna"}),
        english=("Naam",),
        gurmukhi=("ਨਾਮੁ",),
    ),
    TopicSpec(
        id="caste",
        tokens=frozenset({"caste", "janeu", "varna"}),
        distinctive=frozenset({"caste", "janeu"}),
        english=("caste",),
        gurmukhi=("ਜਾਤਿ",),
    ),
    TopicSpec(
        id="equality_women",
        tokens=frozenset({"woman", "women", "female", "gender"}),
        distinctive=frozenset({"woman", "women", "female", "gender"}),
        english=("woman",),
        gurmukhi=("ਇਸਤ੍ਰੀ",),
    ),
    TopicSpec(
        id="langar",
        tokens=frozenset({"langar", "kitchen", "foreigner", "foreigners"}),
        distinctive=frozenset({"langar", "kitchen"}),
        english=("hungry",),
        gurmukhi=(),
    ),
    TopicSpec(
        id="hukam",
        tokens=frozenset({"hukam", "nadar"}),
        distinctive=frozenset({"hukam", "nadar"}),
        english=("Hukam",),
        gurmukhi=("ਹੁਕਮੁ",),
    ),
    TopicSpec(
        id="kakaars",
        tokens=frozenset({"kirpan", "kesh", "kes", "hair", "kara", "kangha"}),
        distinctive=frozenset({"kirpan", "kesh", "kes", "hair"}),
        english=("hair",),
        gurmukhi=(),
    ),
    TopicSpec(
        id="diet",
        tokens=frozenset(
            {
                "meat",
                "flesh",
                "kutha",
                "jhatka",
                "vegetarian",
                "diet",
                "dietary",
                "halal",
                "maas",
            }
        ),
        distinctive=frozenset({"meat", "flesh", "kutha", "jhatka", "vegetarian", "diet", "halal", "maas"}),
        english=("eat meat", "flesh"),
        gurmukhi=("ਮਾਸ",),
    ),
    TopicSpec(
        id="ego",
        tokens=frozenset({"ego", "haumai", "pride"}),
        distinctive=frozenset({"ego", "haumai", "pride"}),
        english=("ego",),
        gurmukhi=("ਹਉਮੈ",),
    ),
    TopicSpec(
        id="honest_living",
        tokens=frozenset({"honest", "honesty", "kirat", "earning"}),
        distinctive=frozenset({"honest", "honesty", "kirat"}),
        english=("honest living",),
        gurmukhi=(),
    ),
)

# Claim token -> short BaniDB English queries that tend to hit real verses.
# Do not map generic words (guru, truth, god, sikh) — those retrieve random shabads.
TOKEN_QUERIES: dict[str, tuple[str, ...]] = {
    "ritual": ("pilgrimage", "fasting"),
    "rituals": ("pilgrimage", "fasting"),
    "mukti": ("Naam",),
    "liberation": ("Naam",),
    "naam": ("Naam",),
    "simran": ("Naam",),
    "pilgrimage": ("pilgrimage",),
    "tirath": ("pilgrimage",),
    "fasting": ("fasting",),
    "form": ("formless",),
    "formless": ("formless",),
    "physical": ("formless", "idol"),
    "idol": ("idol",),
    "murti": ("idol",),
    "worship": ("formless",),
    "worshipped": ("formless",),
    "caste": ("caste",),
    "janeu": ("caste",),
    "woman": ("woman",),
    "women": ("woman",),
    "langar": ("hungry",),
    "kirpan": ("sword",),
    "kesh": ("hair",),
    "kes": ("hair",),
    "hair": ("hair",),
    "hukam": ("Hukam",),
    "ego": ("ego",),
    "haumai": ("ego",),
    "hindu": ("Hindu",),
    "muslim": ("Muslim",),
    "amrit": ("Ambrosial",),
    "nirankar": ("formless",),
    "meat": ("eat meat", "flesh"),
    "flesh": ("flesh", "eat meat"),
    "vegetarian": ("eat meat", "flesh"),
    "kutha": ("flesh",),
    "jhatka": ("flesh",),
    "diet": ("eat meat", "flesh"),
    "maas": ("flesh", "eat meat"),
    "honest": ("honest living",),
    "honesty": ("honest living",),
    "kirat": ("honest living",),
    "earning": ("honest living",),
}


def scripture_queries_for(claim_text: str) -> list[ScriptureQuery]:
    """Heuristic mapping of a claim onto short, on-subject BaniDB searches."""
    focus = claim_focus_tokens(claim_text)
    tokens = expand_tokens(focus) if focus else claim_focus_tokens(claim_text)
    queries: list[ScriptureQuery] = []
    seen: set[tuple[str, int]] = set()

    def add(query: str, searchtype: int, topic: str) -> None:
        query = (query or "").strip()
        if not is_usable_search_query(query, claim_focus=focus, require_focus=False):
            return
        key = (query.lower(), searchtype)
        if key in seen:
            return
        seen.add(key)
        queries.append(ScriptureQuery(query=query, searchtype=searchtype, topic=topic))

    for topic in TOPICS:
        hit = tokens & topic.tokens
        if not hit:
            continue
        if not (hit & topic.distinctive) and len(hit) < 2:
            continue
        for q in topic.english:
            add(q, 3, topic.id)
        for q in topic.gurmukhi:
            add(q, 2, topic.id)

    for tok in tokens:
        for q in TOKEN_QUERIES.get(tok, ()):
            add(q, 3, f"token:{tok}")

    return queries[:6]


async def scripture_queries_for_claim(claim_text: str) -> list[ScriptureQuery]:
    """Understand the claim, then merge heuristic + LLM Gurbani search terms."""
    focus = claim_focus_tokens(claim_text)
    queries = list(scripture_queries_for(claim_text))
    seen = {(q.query.lower(), q.searchtype) for q in queries}

    understood = await understand_claim_subject(claim_text)
    if understood.get("gurbani_relevant") is False and not queries:
        return []

    def add(query: str, searchtype: int, topic: str) -> None:
        query = (query or "").strip()
        if not is_usable_search_query(query, claim_focus=focus, require_focus=True):
            return
        key = (query.lower(), searchtype)
        if key in seen:
            return
        seen.add(key)
        queries.append(ScriptureQuery(query=query, searchtype=searchtype, topic=topic))

    for item in understood.get("queries") or []:
        q = (item.get("q") or "").strip()
        lang = (item.get("lang") or "en").lower()
        if not q or len(q.split()) > 3:
            continue
        searchtype = 2 if lang in {"pa", "gurmukhi", "pa-guru"} or has_gurmukhi(q) else 3
        add(q, searchtype, "llm")
        if len(queries) >= 6:
            break
    return queries[:6]
