from __future__ import annotations

from pathlib import Path
from typing import Any

from app.integrations.ocr import ocr_image
from app.integrations.web_fetch import fetch_url_content, normalize_whitespace


async def ingest_submission(
    *,
    url: str | None = None,
    text: str | None = None,
    media_path: str | Path | None = None,
) -> dict[str, Any]:
    """Stage 1 — gather raw text from URL / paste / OCR."""
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
        fetched = await fetch_url_content(url.strip())
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
        ocr_text = await ocr_image(media_path)
        if ocr_text:
            parts.append(normalize_whitespace(ocr_text))
        log.append(
            {
                "stage": "ingest",
                "event": "ocr",
                "path": str(media_path),
                "chars": len(ocr_text or ""),
            }
        )

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
    return {
        "extracted_text": combined,
        "page_title": title,
        "page_metadata": metadata,
        "blocked": blocked,
        "message": message,
        "log": log,
    }
