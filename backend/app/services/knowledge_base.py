from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from rapidfuzz import fuzz

from app.config import get_settings

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\w\u0A00-\u0A7F]+", re.UNICODE)

STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "that", "this", "with",
    "from", "is", "are", "was", "were", "be", "been", "by", "as", "it", "its", "at",
    "can", "could", "would", "should", "must", "may", "might", "will",     "just", "only",
    "also", "than", "then", "there", "their", "they", "them", "these", "those", "but",
    "not", "no", "yes", "if", "into", "about", "over", "after", "before", "between",
    "said", "says", "say", "claim", "claims", "according", "teach", "teaches", "teaching",
    "taught", "ji", "sri", "the", "any", "all", "does", "do", "doing", "done", "has",
    "have", "had", "been", "being", "who", "whom", "which", "what", "when", "where",
    "how", "why", "very", "more", "most", "such", "via", "per", "vs", "etc",
    "completely", "totally", "entirely", "fully", "always", "never", "everyone", "anyone",
}

# If any token in a group appears, add the whole group to the token set.
SYNONYM_GROUPS: list[set[str]] = [
    {"ritual", "rituals", "rite", "rites", "ceremony", "ceremonies", "ceremonial",
     "karam", "karmakand", "karamkand", "formalism", "formal"},
    {"liberation", "mukti", "moksha", "salvation", "heaven", "mukhti"},
    {"naam", "nam", "simran", "meditation", "japna", "remembrance"},
    {"pilgrimage", "tirath", "teerath", "yatra", "bathing"},
    {"sikh", "sikhi", "sikhism", "sikhs"},
    {"guru", "gurus"},
    {"rehat", "maryada", "discipline"},
    {"khalsa", "amritdhari"},
    {"caste", "varna", "janeu"},
    {"gurbani", "shabad", "verse", "bani"},
    {"ang", "page", "pageno"},
    {"kirpan", "5k", "kakaar", "kakaars"},
    {"langar", "seva"},
    {"british", "colonial", "colonisers", "colonizers"},
    {"hindu", "sect"},
    {"form", "forms", "formless", "physical", "nirankar", "shapeless", "image",
     "idol", "idols", "murti", "statue", "salagram", "saalagraam"},
    {"women", "woman", "gender"},
    {"nitnem", "paath", "path"},
    {"meat", "flesh", "kutha", "jhatka", "vegetarian", "diet", "dietary"},
]


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1]


def content_tokens(text: str) -> set[str]:
    return {t for t in _tokenize(text) if t not in STOPWORDS and not t.isdigit()}


def expand_tokens(tokens: set[str]) -> set[str]:
    out = set(tokens)
    for group in SYNONYM_GROUPS:
        if out & group:
            out |= group
    return out


WEAK_SUBJECT_TOKENS = {
    "sikh", "sikhi", "sikhism", "sikhs", "guru", "gurus", "gurbani", "bani",
    "forbid", "forbids", "forbidden", "ban", "bans", "banned", "prohibits", "prohibit",
    "completely", "totally", "entirely", "fully", "always", "never", "only", "just",
    "lord", "god", "master", "divine", "waheguru", "him", "his", "himself",
    "saved", "fulfilled", "comforted", "meditating", "teaches", "teaching", "taught",
    "claim", "claims", "according", "emphasize", "emphasizes", "people", "religion",
}


def core_subject_tokens(text: str) -> set[str]:
    """Noun-ish tokens that should match for two texts to be about the same subject."""
    return content_tokens(text) - WEAK_SUBJECT_TOKENS


def subject_overlap(a: str, b: str) -> int:
    """Count overlapping *subject* tokens after dropping weak filler and expanding synonyms."""
    qa = expand_tokens(core_subject_tokens(a))
    qb = expand_tokens(core_subject_tokens(b))
    return len(qa & qb)


def topical_overlap(query: str, document: str) -> tuple[int, float]:
    """Distinctive concept count + expanded overlap ratio.

    Synonym groups count as one concept so 'sikh/sikhi/sikhism' cannot
    masquerade as a strong match by itself.
    """
    q_raw = content_tokens(query)
    d_raw = content_tokens(document)
    q = expand_tokens(q_raw)
    d = expand_tokens(d_raw)
    if not q or not d:
        return 0, 0.0
    grouped: set[str] = set()
    for g in SYNONYM_GROUPS:
        grouped |= g
    concepts = 0
    for g in SYNONYM_GROUPS:
        if (q & g) and (d & g):
            concepts += 1
    extra = len((q_raw & d_raw) - grouped)
    distinctive = concepts + extra
    ratio = len(q & d) / max(len(q), 1)
    return distinctive, ratio


@dataclass
class Passage:
    id: str
    source: str
    reference: str
    excerpt: str
    url: str | None = None
    tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    category: str | None = None

    def index_text(self) -> str:
        return " ".join(
            [
                self.reference,
                self.excerpt,
                " ".join(self.tags or []),
                " ".join(self.keywords or []),
                self.category or "",
            ]
        )

    def to_evidence(self, score: float | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "reference": self.reference,
            "excerpt": self.excerpt,
            "url": self.url,
            "score": score,
            "category": self.category,
        }


class KnowledgeBase:
    """Curated corpus with TF-IDF + synonym expansion (no external vector DB required)."""

    def __init__(self) -> None:
        self.passages: list[Passage] = []
        self.known_false: list[dict[str, Any]] = []
        self._loaded = False
        self._vocab: dict[str, int] = {}
        self._idf: np.ndarray | None = None
        self._matrix: np.ndarray | None = None

    def load(self, force: bool = False) -> None:
        if self._loaded and not force:
            return
        settings = get_settings()
        root = settings.curated_path
        self.passages = []
        self.known_false = []

        if not root.exists():
            logger.warning("Curated data dir missing: %s", root)
            self._loaded = True
            return

        for path in sorted(root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load %s: %s", path, exc)
                continue

            if path.name == "known_false_claims.json":
                self.known_false = list(data if isinstance(data, list) else data.get("claims", []))
                continue

            source_name = data.get("source") or path.stem.replace("_", " ").title()
            for i, chunk in enumerate(data.get("chunks") or data.get("passages") or []):
                pid = chunk.get("id") or f"{path.stem}:{i}"
                self.passages.append(
                    Passage(
                        id=pid,
                        source=chunk.get("source") or source_name,
                        reference=chunk.get("reference") or chunk.get("title") or pid,
                        excerpt=chunk.get("excerpt") or chunk.get("text") or "",
                        url=chunk.get("url"),
                        tags=list(chunk.get("tags") or []),
                        keywords=list(chunk.get("keywords") or []),
                        category=chunk.get("category"),
                    )
                )

        self._build_tfidf()
        logger.info(
            "Loaded %s curated passages and %s known-false patterns",
            len(self.passages),
            len(self.known_false),
        )
        self._loaded = True

    def search(self, query: str, *, limit: int = 5, category: str | None = None) -> list[dict[str, Any]]:
        self.load()
        query = (query or "").strip()
        if not query or not self.passages or self._matrix is None:
            return []

        q_vec = self._vectorize(query)
        q_tokens = expand_tokens(content_tokens(query))
        scores: list[tuple[float, Passage]] = []

        for i, p in enumerate(self.passages):
            dense = float(np.dot(self._matrix[i], q_vec))
            distinctive, lexical = topical_overlap(query, p.index_text())
            p_tokens = expand_tokens(content_tokens(p.index_text()))
            fuzzy = 0.0
            if q_tokens and p_tokens:
                fuzzy = fuzz.token_set_ratio(" ".join(sorted(q_tokens)), " ".join(sorted(p_tokens))) / 100.0

            tag_bonus = 0.0
            if category and (p.category == category or category in (p.tags or [])):
                tag_bonus = 0.12

            if distinctive < 2 and dense < 0.22:
                continue

            score = 0.50 * dense + 0.30 * lexical + 0.10 * fuzzy + 0.10 * min(distinctive / 5.0, 1.0) + tag_bonus
            if score >= 0.28:
                scores.append((score, p))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [p.to_evidence(score=round(s, 3)) for s, p in scores[:limit]]

    def match_known_false(self, claim_text: str, limit: int = 3) -> list[dict[str, Any]]:
        self.load()
        claim_text = (claim_text or "").strip()
        if not claim_text:
            return []

        q_tokens = expand_tokens(content_tokens(claim_text))
        hits: list[tuple[float, dict[str, Any]]] = []

        for item in self.known_false:
            patterns = [item.get("claim_pattern") or ""]
            patterns.extend(item.get("aliases") or [])
            best = 0.0
            for pattern in patterns:
                if not pattern:
                    continue
                distinctive, lexical = topical_overlap(claim_text, pattern)
                core_hit = subject_overlap(claim_text, pattern)
                p_tokens = expand_tokens(content_tokens(pattern))
                if not q_tokens or not p_tokens:
                    continue
                jaccard = len(q_tokens & p_tokens) / max(len(q_tokens | p_tokens), 1)
                fuzzy = fuzz.ratio(claim_text.lower(), pattern.lower()) / 100.0
                # "Sikhi forbids X" must not match "Sikhism forbids Y".
                if core_hit < 1:
                    continue
                if core_hit < 2 and fuzzy < 0.78:
                    continue
                score = 0.35 * min(core_hit / 3.0, 1.0) + 0.25 * lexical + 0.20 * jaccard + 0.20 * fuzzy
                best = max(best, score)
            if best >= 0.48:
                hits.append((best, item))

        hits.sort(key=lambda x: x[0], reverse=True)
        evidence = []
        for score, item in hits[:limit]:
            evidence.append(
                {
                    "id": f"known-false:{item.get('id') or abs(hash(item.get('claim_pattern', '')))}",
                    "source": "Known False Claims Index",
                    "reference": item.get("category") or "known_false",
                    "excerpt": f"{item.get('explanation', '')} Correction: {item.get('correction', '')}",
                    "url": None,
                    "score": round(score, 3),
                    "meta": item,
                    "category": item.get("category"),
                }
            )
        return evidence

    def _build_tfidf(self) -> None:
        docs = [expand_tokens(content_tokens(p.index_text())) for p in self.passages]
        df: dict[str, int] = {}
        for tokens in docs:
            for t in tokens:
                df[t] = df.get(t, 0) + 1
        vocab = {term: i for i, term in enumerate(sorted(df))}
        n_docs = max(len(docs), 1)
        idf = np.zeros(len(vocab), dtype=np.float64)
        for term, idx in vocab.items():
            idf[idx] = math.log((n_docs + 1) / (df[term] + 1)) + 1.0
        matrix = np.zeros((len(docs), len(vocab)), dtype=np.float64)
        for row, tokens in enumerate(docs):
            if not vocab:
                break
            counts: dict[str, int] = {}
            for t in tokens:
                counts[t] = counts.get(t, 0) + 1
            for t, c in counts.items():
                col = vocab.get(t)
                if col is None:
                    continue
                matrix[row, col] = c * idf[col]
            norm = np.linalg.norm(matrix[row])
            if norm:
                matrix[row] /= norm
        self._vocab = vocab
        self._idf = idf
        self._matrix = matrix

    def _vectorize(self, query: str) -> np.ndarray:
        dim = len(self._vocab)
        vec = np.zeros(dim, dtype=np.float64)
        if dim == 0 or self._idf is None:
            return vec
        tokens = expand_tokens(content_tokens(query))
        counts: dict[str, int] = {}
        for t in tokens:
            if t in self._vocab:
                counts[t] = counts.get(t, 0) + 1
        for t, c in counts.items():
            vec[self._vocab[t]] = c * self._idf[self._vocab[t]]
        norm = np.linalg.norm(vec)
        if norm:
            vec /= norm
        return vec


_kb: KnowledgeBase | None = None


def get_knowledge_base() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
        _kb.load()
    return _kb


def reset_knowledge_base() -> None:
    global _kb
    _kb = None
