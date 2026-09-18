from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.integrations.banidb import _cache, _cache_key

logger = logging.getLogger(__name__)


class GurbaniNowClient:
    def __init__(self, base_url: str | None = None, timeout: float = 20.0) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.gurbaninow_base_url).rstrip("/")
        self.timeout = timeout

    async def get_ang(self, ang: int) -> list[dict[str, Any]]:
        key = _cache_key("gn-ang", str(ang))
        cached = _cache.get(key)
        if cached is not None:
            return cached

        url = f"{self.base_url}/ang/{ang}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("GurbaniNow ang lookup failed for %s: %s", ang, exc)
            return []

        page = data.get("page") or []
        passages = []
        for line in page:
            line_data = line.get("line") or line
            gurmukhi = (line_data.get("gurmukhi") or {})
            unicode_text = gurmukhi.get("unicode") or ""
            translation = ((line_data.get("translation") or {}).get("english") or {}).get("default") or ""
            shabad_id = line_data.get("shabadid")
            line_id = line_data.get("id")
            passages.append(
                {
                    "id": f"gurbaninow:{line_id or shabad_id}:{ang}",
                    "source": "GurbaniNow",
                    "reference": f"Ang {ang}",
                    "excerpt": unicode_text,
                    "translation": translation,
                    "ang": ang,
                    "shabad_id": shabad_id,
                    "url": None,
                    "score": None,
                }
            )
        _cache.set(key, passages)
        return passages

    async def search(self, query: str, searchtype: int = 0, results: int = 10) -> list[dict[str, Any]]:
        query = (query or "").strip()
        if not query:
            return []

        key = _cache_key("gn-search", f"{query}|{searchtype}|{results}")
        cached = _cache.get(key)
        if cached is not None:
            return cached

        url = f"{self.base_url}/search/{query}"
        params = {"searchtype": searchtype, "results": results}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("GurbaniNow search failed for %r: %s", query, exc)
            return []

        shabads = data.get("shabads") or []
        passages: list[dict[str, Any]] = []
        for item in shabads:
            shabad = item.get("shabad") or item
            verse = shabad.get("verse") or shabad.get("gurmukhi") or {}
            unicode_text = verse.get("unicode") if isinstance(verse, dict) else str(verse)
            ang = shabad.get("pageno") or shabad.get("pageNo")
            shabad_id = shabad.get("shabadid") or shabad.get("id")
            passages.append(
                {
                    "id": f"gurbaninow-search:{shabad_id}:{ang}",
                    "source": "GurbaniNow",
                    "reference": f"Ang {ang}" if ang else f"Shabad {shabad_id}",
                    "excerpt": unicode_text or "",
                    "translation": "",
                    "ang": ang,
                    "shabad_id": shabad_id,
                    "url": None,
                    "score": None,
                }
            )
        _cache.set(key, passages)
        return passages
