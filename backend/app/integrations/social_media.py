"""Download public social media posts (reels, videos, image posts) for analysis.

Strategy, in order:
1. yt-dlp — handles YouTube/Shorts, TikTok, X/Twitter, many public Facebook and
   Instagram reels. Optional cookies file makes Meta far more reliable.
2. Open Graph fallback — many pages expose og:video / og:image even when the
   page itself is behind a login wall; download that media directly.
3. Give the user a clear path: screen-record/save the post and upload the file.

Nothing here bypasses authentication; it only fetches what is publicly served.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

MEDIA_HOSTS = {
    "instagram.com",
    "www.instagram.com",
    "instagr.am",
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "fb.com",
    "fb.watch",
    "tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "x.com",
    "twitter.com",
    "www.x.com",
    "www.twitter.com",
}

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}


def is_media_url(url: str) -> bool:
    """True for social/video hosts where the post IS the media."""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return False
    return any(host == h or host.endswith("." + h) for h in MEDIA_HOSTS)


def media_kind(path: str | Path) -> str | None:
    ext = Path(path).suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "image"
    return None


async def download_social_media(url: str) -> dict[str, Any]:
    """Fetch a public post's media + caption. Returns a result dict, never raises.

    Keys: ok, media_path, media_kind ('video'|'image'|None), title, description,
    uploader, duration, message.
    """
    result: dict[str, Any] = {
        "ok": False,
        "media_path": None,
        "media_kind": None,
        "title": None,
        "description": "",
        "uploader": None,
        "duration": None,
        "message": None,
    }

    ytdlp = await asyncio.to_thread(_ytdlp_download, url)
    if ytdlp.get("ok") and _validate_media(ytdlp.get("media_path"), ytdlp.get("media_kind")):
        return {**result, **ytdlp}

    og = await _og_media_download(url)
    if og.get("ok") and _validate_media(og.get("media_path"), og.get("media_kind")):
        og["message"] = ytdlp.get("message")
        return {**result, **og}

    result["message"] = (
        (ytdlp.get("message") or "The platform refused automated access to this post.")
        + " Workaround: save/screen-record the post and upload the file here, "
        "or paste the caption text — the analysis pipeline is identical."
    )
    # Still surface any caption text OG gave us.
    result["title"] = og.get("title")
    result["description"] = og.get("description") or ""
    return result


def _validate_media(path: str | None, kind: str | None) -> bool:
    """Reject junk downloads (HTML embed pages saved as .mp4, truncated files)."""
    if not path:
        return False
    p = Path(path)
    if not p.exists() or p.stat().st_size < 1024:
        return False
    if kind == "video" or media_kind(p) == "video":
        try:
            proc = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(p)],
                check=True,
                capture_output=True,
                timeout=30,
            )
            duration = float((json.loads(proc.stdout).get("format") or {}).get("duration") or 0.0)
            if duration <= 0:
                raise ValueError("no duration")
            return True
        except Exception:  # noqa: BLE001
            logger.warning("Downloaded file is not a valid video: %s", p)
            p.unlink(missing_ok=True)
            return False
    try:
        from PIL import Image

        with Image.open(p) as img:
            img.verify()
        return True
    except Exception:  # noqa: BLE001
        logger.warning("Downloaded file is not a valid image: %s", p)
        p.unlink(missing_ok=True)
        return False


def _ytdlp_download(url: str) -> dict[str, Any]:
    """Blocking yt-dlp download; run in a thread."""
    settings = get_settings()
    dest_dir = settings.upload_path / "social"
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex
    outtmpl = str(dest_dir / f"{stem}.%(ext)s")

    opts: dict[str, Any] = {
        "outtmpl": outtmpl,
        "format": "mp4[height<=720]/best[height<=720]/best",
        "max_filesize": settings.max_media_download_bytes,
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 2,
        "playlist_items": "1",
        "match_filter": _duration_filter(settings.max_video_seconds),
    }
    if settings.social_cookies_file and Path(settings.social_cookies_file).exists():
        opts["cookiefile"] = settings.social_cookies_file

    try:
        import yt_dlp

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("yt-dlp failed for %s: %s", url, exc)
        return {"ok": False, "message": f"Automated download failed: {str(exc)[:200]}"}

    if info is None:
        return {"ok": False, "message": "Automated download returned nothing."}
    if "entries" in info:
        entries = [e for e in (info.get("entries") or []) if e]
        info = entries[0] if entries else info

    downloaded = sorted(dest_dir.glob(f"{stem}.*"))
    if not downloaded:
        return {"ok": False, "message": "No media file was produced."}
    media_path = downloaded[0]
    kind = media_kind(media_path) or ("video" if info.get("duration") else None)
    return {
        "ok": True,
        "media_path": str(media_path),
        "media_kind": kind,
        "title": info.get("title"),
        "description": (info.get("description") or "")[:4000],
        "uploader": info.get("uploader") or info.get("channel"),
        "duration": info.get("duration"),
    }


def _duration_filter(max_seconds: int):
    def _filter(info_dict, *, incomplete=False):  # yt-dlp callback signature
        duration = info_dict.get("duration")
        if duration and duration > max_seconds:
            return f"video too long ({duration}s > {max_seconds}s limit)"
        return None

    return _filter


async def _og_media_download(url: str) -> dict[str, Any]:
    """Fallback: pull og:video / og:image directly from the public page HTML."""
    settings = get_settings()
    headers = {
        # Meta serves richer OG tags to link-preview agents than to browsers.
        "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                return {"ok": False}
            html = resp.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("OG fetch failed for %s: %s", url, exc)
        return {"ok": False}

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    meta: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        key = tag.get("property") or tag.get("name")
        content = tag.get("content")
        if key and content:
            meta[key] = content

    title = meta.get("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else None)
    description = meta.get("og:description") or meta.get("description") or ""

    media_url = meta.get("og:video") or meta.get("og:video:url") or meta.get("og:video:secure_url")
    kind = "video" if media_url else None
    if not media_url:
        media_url = meta.get("og:image") or meta.get("og:image:url")
        kind = "image" if media_url else None
    if not media_url:
        return {"ok": False, "title": title, "description": description}

    dest_dir = get_settings().upload_path / "social"
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(urlparse(media_url).path).suffix.lower() or (".mp4" if kind == "video" else ".jpg")
    dest = dest_dir / f"{uuid.uuid4().hex}{ext}"
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, headers=headers) as client:
            async with client.stream("GET", media_url) as resp:
                if resp.status_code >= 400:
                    return {"ok": False, "title": title, "description": description}
                size = 0
                with dest.open("wb") as fh:
                    async for chunk in resp.aiter_bytes():
                        size += len(chunk)
                        if size > settings.max_media_download_bytes:
                            fh.close()
                            dest.unlink(missing_ok=True)
                            return {"ok": False, "title": title, "description": description}
                        fh.write(chunk)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OG media download failed for %s: %s", media_url, exc)
        dest.unlink(missing_ok=True)
        return {"ok": False, "title": title, "description": description}

    return {
        "ok": True,
        "media_path": str(dest),
        "media_kind": kind or media_kind(dest),
        "title": title,
        "description": description[:4000],
        "uploader": meta.get("og:site_name"),
        "duration": None,
    }
