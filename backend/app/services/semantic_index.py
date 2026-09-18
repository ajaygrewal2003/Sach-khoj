"""Meaning-based retrieval over the entire curated corpus + known-false index.

Embeds every curated passage and known-false pattern once (cached on disk),
then retrieves by cosine similarity to the claim. This is the general
mechanism: "alcohol" finds the intoxicants clause, "surname Kaur" finds
identity notes — no keyword or tag lists per topic.

Returns None when embeddings are unavailable (no API key) so callers can
fall back to the lexical TF-IDF path.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Any

from app.services.knowledge_base import get_knowledge_base
from app.services.llm import embed_texts

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"
_CACHE_FILE = _CACHE_DIR / "semantic_index.json"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class SemanticIndex:
    """Embedded view of the curated corpus + known-false patterns."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._vectors: dict[str, list[float]] = {}
        self._built = False

    def _collect_entries(self) -> list[dict[str, Any]]:
        kb = get_knowledge_base()
        kb.load()
        entries: list[dict[str, Any]] = []
        for passage in kb.passages:
            entries.append(
                {
                    "kind": "curated",
                    "text": passage.index_text(),
                    "evidence": passage.to_evidence(score=None),
                }
            )
        for item in kb.known_false:
            pattern = item.get("claim_pattern") or ""
            aliases = " | ".join(item.get("aliases") or [])
            text = f"{pattern} {aliases} {item.get('explanation') or ''}"
            entries.append(
                {
                    "kind": "known_false",
                    "text": text,
                    "evidence": {
                        "id": f"known-false:{item.get('id') or _sha(pattern)}",
                        "source": "Known False Claims Index",
                        "reference": item.get("category") or "known_false",
                        "excerpt": (
                            f"{item.get('explanation', '')} "
                            f"Correction: {item.get('correction', '')}"
                        ),
                        "url": None,
                        "score": None,
                        "meta": item,
                        "category": item.get("category"),
                    },
                }
            )
        return entries

    def _load_cache(self) -> dict[str, list[float]]:
        try:
            if _CACHE_FILE.exists():
                return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("semantic index cache unreadable: %s", exc)
        return {}

    def _save_cache(self) -> None:
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _CACHE_FILE.write_text(json.dumps(self._vectors), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("semantic index cache not saved: %s", exc)

    async def ensure_ready(self) -> bool:
        """Embed any corpus entries missing from the cache. False if unavailable."""
        if self._built:
            return bool(self._vectors)
        self._entries = self._collect_entries()
        self._vectors = self._load_cache()
        missing = [e for e in self._entries if _sha(e["text"]) not in self._vectors]
        if missing:
            vectors = await embed_texts([e["text"] for e in missing])
            if vectors is None:
                self._built = True
                self._vectors = {}
                return False
            for entry, vec in zip(missing, vectors, strict=True):
                self._vectors[_sha(entry["text"])] = vec
            self._save_cache()
        self._built = True
        return bool(self._vectors)

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        min_sim: float = 0.25,
    ) -> list[dict[str, Any]] | None:
        """Rank corpus entries by meaning. None when embeddings are unavailable."""
        if not (query or "").strip():
            return []
        if not await self.ensure_ready():
            return None
        qvecs = await embed_texts([query[:2000]])
        if not qvecs:
            return None
        qvec = qvecs[0]
        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in self._entries:
            vec = self._vectors.get(_sha(entry["text"]))
            if not vec:
                continue
            sim = _cosine(qvec, vec)
            if sim < min_sim:
                continue
            evidence = {**entry["evidence"], "score": round(sim, 3), "kind": entry["kind"]}
            scored.append((sim, evidence))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [evidence for _, evidence in scored[:top_k]]


_index: SemanticIndex | None = None


def get_semantic_index() -> SemanticIndex:
    global _index
    if _index is None:
        _index = SemanticIndex()
    return _index


def reset_semantic_index() -> None:
    global _index
    _index = None
