from __future__ import annotations

from dataclasses import dataclass

from app.services.knowledge_base import content_tokens, expand_tokens
from app.services.llm import chat_json

# BaniDB: searchtype 2 ≈ Gurmukhi word, searchtype 3 ≈ English translation.
# Queries must be short; never send a full English sentence to the API.

GENERIC_TOKENS = {
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
}


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
    TopicSpec(
        id="equality_women",
        tokens=frozenset({"woman", "women", "female", "gender", "amrit"}),
        distinctive=frozenset({"woman", "women", "female", "gender"}),
        english=("woman",),
        gurmukhi=(),
    ),
    TopicSpec(
        id="langar",
        tokens=frozenset({"langar", "kitchen", "food", "foreigner", "foreigners"}),
        distinctive=frozenset({"langar", "kitchen"}),
        english=("food", "hungry"),
        gurmukhi=(),
    ),
    TopicSpec(
        id="hukam",
        tokens=frozenset({"hukam", "grace", "nadar", "will"}),
        distinctive=frozenset({"hukam", "nadar", "grace"}),
        english=("Hukam", "grace"),
        gurmukhi=("ਹੁਕਮੁ",),
    ),
    TopicSpec(
        id="kakaars",
        tokens=frozenset({"kirpan", "kesh", "kes", "hair", "sword", "kara", "kangha"}),
        distinctive=frozenset({"kirpan", "kesh", "kes", "hair", "sword"}),
        english=("sword", "hair"),
        gurmukhi=(),
    ),
    TopicSpec(
        id="ego",
        tokens=frozenset({"ego", "haumai", "pride", "humble"}),
        distinctive=frozenset({"ego", "haumai", "pride"}),
        english=("ego",),
        gurmukhi=("ਹਉਮੈ",),
    ),
)

# Claim token -> short BaniDB English queries that tend to hit real verses.
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
    "form": ("formless", "form"),
    "formless": ("formless",),
    "physical": ("formless", "idol"),
    "idol": ("idol",),
    "murti": ("idol",),
    "worship": ("worship", "formless"),
    "worshipped": ("worship", "formless"),
    "caste": ("caste",),
    "janeu": ("caste",),
    "woman": ("woman",),
    "women": ("woman",),
    "langar": ("food", "hungry"),
    "kirpan": ("sword",),
    "sword": ("sword",),
    "kesh": ("hair",),
    "kes": ("hair",),
    "hair": ("hair",),
    "hukam": ("Hukam",),
    "grace": ("grace",),
    "ego": ("ego",),
    "haumai": ("ego",),
    "truth": ("Truth",),
    "guru": ("Guru",),
    "granth": ("Word",),
    "shabad": ("Shabad",),
    "bani": ("Bani",),
    "hindu": ("Hindu",),
    "muslim": ("Muslim",),
    "khalsa": ("warrior",),
    "amrit": ("Ambrosial", "Naam"),
    "god": ("Lord", "formless"),
    "waheguru": ("Lord",),
    "onkar": ("One", "formless"),
    "nirankar": ("formless",),
}


def scripture_queries_for(claim_text: str) -> list[ScriptureQuery]:
    """Heuristic mapping of any claim onto short BaniDB searches."""
    tokens = expand_tokens(content_tokens(claim_text))
    queries: list[ScriptureQuery] = []
    seen: set[tuple[str, int]] = set()

    def add(query: str, searchtype: int, topic: str) -> None:
        query = (query or "").strip()
        if not query or len(query) > 40:
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
        if tok in GENERIC_TOKENS:
            continue
        for q in TOKEN_QUERIES.get(tok, ()):
            add(q, 3, f"token:{tok}")

    # Last resort: distinctive claim words as English translation searches.
    for tok in tokens:
        if tok in GENERIC_TOKENS or len(tok) < 5:
            continue
        if tok in TOKEN_QUERIES:
            continue
        if any(tok in t.tokens for t in TOPICS):
            continue
        add(tok, 3, "claim-token")
        if len(queries) >= 8:
            break

    return queries[:8]


async def scripture_queries_for_claim(claim_text: str) -> list[ScriptureQuery]:
    """Heuristic queries plus optional LLM-proposed Gurbani search terms."""
    queries = list(scripture_queries_for(claim_text))
    seen = {(q.query.lower(), q.searchtype) for q in queries}
    llm = await chat_json(
        (
            "You pick short search strings to look up Sri Guru Granth Sahib Ji. "
            "Return ONLY JSON: {\"queries\": [{\"q\": \"formless\", \"lang\": \"en\"}]}. "
            "Each q must be 1-3 words. lang is en or pa (Gurmukhi unicode). "
            "Do not send full sentences. Prefer words that appear in standard English translations "
            "(Naam, formless, caste, woman, pilgrimage, Hukam, Guru, Lord, Truth, ego, sword, hair)."
        ),
        f"Claim:\n{claim_text[:1500]}",
    )
    if not llm:
        return queries[:8]
    for item in llm.get("queries") or []:
        q = (item.get("q") or "").strip()
        lang = (item.get("lang") or "en").lower()
        if not q or len(q.split()) > 3:
            continue
        searchtype = 2 if lang in {"pa", "gurmukhi", "pa-guru"} or any("\u0A00" <= ch <= "\u0A7F" for ch in q) else 3
        key = (q.lower(), searchtype)
        if key in seen:
            continue
        seen.add(key)
        queries.append(ScriptureQuery(query=q, searchtype=searchtype, topic="llm"))
        if len(queries) >= 8:
            break
    return queries[:8]
