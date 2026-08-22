from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from app.config import get_settings

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\w\u0A00-\u0A7F]+", re.UNICODE)


@dataclass
class Passage:
    id: str
    source: str
    reference: str
    excerpt: str
    url: str | None = None
    tags: list[str] | None = None
    category: str | None = None

    def to_evidence(self, score: float | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "reference": self.reference,
            "excerpt": self.excerpt,
            "url": self.url,
            "score": score,
        }


class KnowledgeBase:
    """Curated corpus with hybrid keyword + fuzzy retrieval (no external vector DB required for MVP)."""

    def __init__(self) -> None:
        self.passages: list[Passage] = []
        self.known_false: list[dict[str, Any]] = []
        self._loaded = False

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
                        tags=chunk.get("tags") or [],
                        category=chunk.get("category"),
                    )
                )

        logger.info("Loaded %s curated passages and %s known-false patterns", len(self.passages), len(self.known_false))
        self._loaded = True

    def search(self, query: str, *, limit: int = 5, category: str | None = None) -> list[dict[str, Any]]:
        self.load()
        query = (query or "").strip()
        if not query or not self.passages:
            return []

        q_tokens = set(_tokenize(query.lower()))
        scored: list[tuple[float, Passage]] = []
        for p in self.passages:
            if category and p.category and p.category != category and category not in (p.tags or []):
                # Soft filter — still allow but downrank later
                pass
            text = f"{p.reference} {p.excerpt} {' '.join(p.tags or [])}".lower()
            p_tokens = set(_tokenize(text))
            overlap = len(q_tokens & p_tokens) / max(len(q_tokens), 1)
            fuzzy = fuzz.token_set_ratio(query, p.excerpt) / 100.0
            tag_bonus = 0.15 if category and (p.category == category or category in (p.tags or [])) else 0.0
            score = 0.45 * overlap + 0.45 * fuzzy + tag_bonus
            if score >= 0.18:
                scored.append((score, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p.to_evidence(score=round(s, 3)) for s, p in scored[:limit]]

    def match_known_false(self, claim_text: str, limit: int = 3) -> list[dict[str, Any]]:
        self.load()
        claim_text = (claim_text or "").strip()
        if not claim_text:
            return []

        hits: list[tuple[float, dict[str, Any]]] = []
        for item in self.known_false:
            pattern = item.get("claim_pattern") or ""
            score = max(
                fuzz.token_set_ratio(claim_text, pattern),
                fuzz.partial_ratio(claim_text, pattern),
            )
            if score >= 70:
                hits.append((score / 100.0, item))
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
                }
            )
        return evidence


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text) if len(t) > 1]


_kb: KnowledgeBase | None = None


def get_knowledge_base() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
        _kb.load()
    return _kb
