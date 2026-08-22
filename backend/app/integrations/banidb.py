from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

import httpx
from rapidfuzz import fuzz

from app.config import get_settings

logger = logging.getLogger(__name__)


def _cache_key(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


class _ResponseCache:
    """Simple in-memory cache for API responses within a process lifetime."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value


_cache = _ResponseCache()


class BaniDBClient:
    def __init__(self, base_url: str | None = None, timeout: float = 20.0) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.banidb_base_url).rstrip("/")
        self.timeout = timeout

    async def search(
        self,
        query: str,
        *,
        searchtype: int = 1,
        source: str = "G",
        results: int = 8,
    ) -> list[dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []

        key = _cache_key("banidb-search", f"{query}|{searchtype}|{source}|{results}")
        cached = _cache.get(key)
        if cached is not None:
            return cached

        params = {
            "searchtype": searchtype,
            "source": source,
            "writer": "all",
            "raag": "all",
            "ang": 0,
            "results": results,
        }
        url = f"{self.base_url}/search/{query}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("BaniDB search failed for %r: %s", query, exc)
            return []

        verses = data.get("verses") or []
        passages = [self._normalize_verse(v) for v in verses]
        _cache.set(key, passages)
        return passages

    async def get_ang(self, ang: int) -> list[dict[str, Any]]:
        key = _cache_key("banidb-ang", str(ang))
        cached = _cache.get(key)
        if cached is not None:
            return cached

        url = f"{self.base_url}/angs/{ang}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("BaniDB ang lookup failed for %s: %s", ang, exc)
            return []

        page = data.get("page") or []
        passages = [self._normalize_verse(v) for v in page]
        _cache.set(key, passages)
        return passages

    async def search_fuzzy(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search unicode Gurmukhi, then rank by fuzzy similarity."""
        if any("\u0A00" <= ch <= "\u0A7F" for ch in query):
            results = await self.search(query, searchtype=2, results=max(limit * 2, 10))
        else:
            results = await self.search(query, searchtype=3, results=max(limit * 2, 10))
        if not results:
            ascii_q = "".join(ch for ch in query.lower() if ch.isalpha())
            if len(ascii_q) >= 3:
                results = await self.search(ascii_q[:12], searchtype=2, results=max(limit * 2, 10))

        ranked: list[tuple[float, dict[str, Any]]] = []
        for item in results:
            excerpt = item.get("excerpt") or ""
            score = max(
                fuzz.partial_ratio(query, excerpt),
                fuzz.token_set_ratio(query, excerpt),
            )
            item = {**item, "score": round(score / 100.0, 3)}
            ranked.append((score, item))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in ranked[:limit]]

    def _has_gurmukhi(self, text: str) -> bool:
        return any("\u0A00" <= ch <= "\u0A7F" for ch in text)

    async def search_for_claim(self, query: str, *, searchtype: int, limit: int = 5) -> list[dict[str, Any]]:
        """Search Gurmukhi (type 2) or English translation (type 3) and attach a match score."""
        results = await self.search(query, searchtype=searchtype, results=max(limit * 2, 8))
        ranked: list[tuple[float, dict[str, Any]]] = []
        query_l = (query or "").strip()
        for item in results:
            haystack = f"{item.get('excerpt') or ''} {item.get('translation') or ''}"
            if searchtype == 3 and query_l:
                if not self._english_query_hits(query_l, haystack):
                    continue
            elif searchtype == 2 and query_l and query_l not in (item.get("excerpt") or ""):
                # Gurmukhi headword should appear in the verse unicode.
                continue
            score = max(
                fuzz.partial_ratio(query_l, haystack),
                fuzz.token_set_ratio(query_l, haystack),
            )
            ranked.append((score, {**item, "score": round(max(score / 100.0, 0.35), 3)}))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in ranked[:limit]]

    def _english_query_hits(self, query: str, haystack: str) -> bool:
        """Require the search phrase (or each content word) as whole words, not substrings."""
        if not query or not haystack:
            return False
        if re.search(rf"\b{re.escape(query)}\b", haystack, re.IGNORECASE):
            return True
        words = [w for w in re.findall(r"[A-Za-z]+", query) if len(w) > 2]
        if len(words) >= 2 and all(re.search(rf"\b{re.escape(w)}\b", haystack, re.IGNORECASE) for w in words):
            return True
        return False

    def _normalize_verse(self, verse: dict[str, Any]) -> dict[str, Any]:
        verse_body = verse.get("verse") or {}
        unicode_text = verse_body.get("unicode") or verse_body.get("gurmukhi") or ""
        translation = ((verse.get("translation") or {}).get("en") or {}).get("bdb") or ""
        writer = (verse.get("writer") or {}).get("english") or "Unknown"
        source = (verse.get("source") or {}).get("english") or "Sri Guru Granth Sahib Ji"
        ang = verse.get("pageNo") or verse.get("pageno")
        shabad_id = verse.get("shabadId")
        verse_id = verse.get("verseId")
        ref = f"Ang {ang}" if ang else f"Shabad {shabad_id}"
        return {
            "id": f"banidb:{verse_id or shabad_id}:{ang}",
            "source": "BaniDB",
            "reference": ref,
            "excerpt": unicode_text,
            "translation": translation,
            "writer": writer,
            "source_name": source,
            "ang": ang,
            "shabad_id": shabad_id,
            "url": f"https://www.sikhitothemax.org/shabad?id={shabad_id}" if shabad_id else None,
            "score": None,
        }
