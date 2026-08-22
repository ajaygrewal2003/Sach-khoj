from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SOCIAL_HOSTS = {
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "fb.com",
    "instagram.com",
    "www.instagram.com",
    "instagr.am",
}


def is_social_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return False
    return any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS)


async def fetch_url_content(url: str, timeout: float = 25.0) -> dict[str, Any]:
    """Fetch page metadata and main text. Social URLs often fail — return guidance."""
    result: dict[str, Any] = {
        "url": url,
        "title": None,
        "text": "",
        "metadata": {},
        "blocked": False,
        "message": None,
    }

    if is_social_url(url):
        result["blocked"] = True
        result["message"] = (
            "Facebook/Instagram pages usually cannot be fetched automatically. "
            "Paste the caption text or upload a screenshot, then resubmit."
        )
        # Still try oEmbed / public HTML lightly
        og = await _try_open_graph(url, timeout=timeout)
        result.update({k: v for k, v in og.items() if v})
        return result

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "SachKhojBot/1.0 (+https://github.com/ajaygrewal2003/sach-khoj)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("URL fetch failed for %s: %s", url, exc)
        result["message"] = f"Could not fetch URL: {exc}"
        return result

    extracted = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    meta = _parse_html_meta(html)
    result["title"] = meta.get("title")
    result["text"] = extracted.strip()
    result["metadata"] = meta
    if not result["text"]:
        result["message"] = "Fetched page but could not extract readable article text."
    return result


async def _try_open_graph(url: str, timeout: float = 15.0) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SachKhojBot/1.0)"},
        ) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                return {}
            meta = _parse_html_meta(resp.text)
            return {
                "title": meta.get("og:title") or meta.get("title"),
                "text": meta.get("og:description") or meta.get("description") or "",
                "metadata": meta,
            }
    except Exception:  # noqa: BLE001
        return {}


def _parse_html_meta(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    meta: dict[str, Any] = {}
    if soup.title and soup.title.string:
        meta["title"] = soup.title.string.strip()
    for tag in soup.find_all("meta"):
        key = tag.get("property") or tag.get("name")
        content = tag.get("content")
        if key and content:
            meta[key] = content.strip()
    return meta


def normalize_whitespace(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
