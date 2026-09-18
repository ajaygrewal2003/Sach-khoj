from __future__ import annotations

from pathlib import Path
from typing import Any

from app.integrations.ocr import ocr_image
from app.integrations.social_media import download_social_media, is_media_url, media_kind
from app.integrations.web_fetch import fetch_url_content, normalize_whitespace
from app.services.media_understanding import understand_image, understand_video


async def ingest_submission(
    *,
    url: str | None = None,
    text: str | None = None,
    media_path: str | Path | None = None,
) -> dict[str, Any]:
    """Stage 1 — turn whatever the user gave us (URL, text, video, image) into text.

    Social links (reels, TikToks, Shorts, posts) are downloaded, the speech is
    transcribed, and the frames are read, so the claim pipeline sees everything
    that was said and shown — same as pasted text.
    """
    log: list[dict[str, Any]] = []
    parts: list[str] = []
    title: str | None = None
    metadata: dict[str, Any] = {}
    blocked = False
    message: str | None = None

    if text and text.strip():
        parts.append(normalize_whitespace(text))
        log.append({"stage": "ingest", "event": "text_provided", "chars": len(text.strip())})

    if url and url.strip():
        url = url.strip()
        if is_media_url(url):
            social = await download_social_media(url)
            title = social.get("title") or title
            metadata = {
                "source_url": url,
                "uploader": social.get("uploader"),
                "duration": social.get("duration"),
                "media_kind": social.get("media_kind"),
            }
            message = social.get("message")
            caption = (social.get("description") or "").strip()
            if title:
                parts.append(f"[Post title] {normalize_whitespace(title)}")
            if caption:
                parts.append(f"[Post caption] {normalize_whitespace(caption)}")
            if social.get("ok") and social.get("media_path"):
                media_parts = await _understand_media_file(social["media_path"], log)
                parts.extend(media_parts)
                log.append(
                    {
                        "stage": "ingest",
                        "event": "social_media_downloaded",
                        "url": url,
                        "kind": social.get("media_kind"),
                        "duration": social.get("duration"),
                    }
                )
            else:
                blocked = True
                log.append(
                    {
                        "stage": "ingest",
                        "event": "social_media_blocked",
                        "url": url,
                        "message": message,
                    }
                )
        else:
            fetched = await fetch_url_content(url)
            blocked = bool(fetched.get("blocked"))
            message = fetched.get("message")
            title = fetched.get("title")
            metadata = fetched.get("metadata") or {}
            if fetched.get("text"):
                parts.append(normalize_whitespace(fetched["text"]))
            log.append(
                {
                    "stage": "ingest",
                    "event": "url_fetch",
                    "url": url,
                    "blocked": blocked,
                    "chars": len(fetched.get("text") or ""),
                    "message": message,
                }
            )

    if media_path:
        media_parts = await _understand_media_file(media_path, log)
        parts.extend(media_parts)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_parts: list[str] = []
    for part in parts:
        key = part[:200]
        if key in seen:
            continue
        seen.add(key)
        unique_parts.append(part)

    combined = normalize_whitespace("\n\n".join(unique_parts))
    if combined and blocked:
        # We got usable text some other way; don't fail the case.
        blocked = False
    return {
        "extracted_text": combined,
        "page_title": title,
        "page_metadata": metadata,
        "blocked": blocked,
        "message": message,
        "log": log,
    }


async def _understand_media_file(media_path: str | Path, log: list[dict[str, Any]]) -> list[str]:
    """Video → transcript + visuals; image → vision + OCR. Returns labeled sections."""
    media_path = Path(media_path)
    parts: list[str] = []
    kind = media_kind(media_path) or "image"

    if kind == "video":
        understood = await understand_video(media_path)
        transcript = (understood.get("transcript") or "").strip()
        visuals = (understood.get("visuals") or "").strip()
        if transcript:
            parts.append(f"[Spoken transcript] {normalize_whitespace(transcript)}")
        if visuals:
            parts.append(f"[On-screen visuals and text] {normalize_whitespace(visuals)}")
        log.append(
            {
                "stage": "ingest",
                "event": "video_understanding",
                "path": str(media_path),
                "transcript_chars": len(transcript),
                "visuals_chars": len(visuals),
            }
        )
        return parts

    vision_text = (await understand_image(media_path) or "").strip()
    if vision_text:
        parts.append(f"[Image content] {normalize_whitespace(vision_text)}")
    ocr_text = (await ocr_image(media_path) or "").strip()
    # OCR still helps when vision is unavailable (no key) or misses dense text.
    if ocr_text and not vision_text:
        parts.append(normalize_whitespace(ocr_text))
    log.append(
        {
            "stage": "ingest",
            "event": "image_understanding",
            "path": str(media_path),
            "vision_chars": len(vision_text),
            "ocr_chars": len(ocr_text),
        }
    )
    return parts
