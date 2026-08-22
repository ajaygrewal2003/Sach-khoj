from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def ocr_image(path: str | Path) -> str:
    """OCR an image. Prefers Gurmukhi (pan) + English when Tesseract is available."""
    path = Path(path)
    if not path.exists():
        return ""

    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        logger.warning("OCR dependencies missing")
        return ""

    try:
        image = Image.open(path)
        # Prefer Punjabi/Gurmukhi + English; fall back to English-only
        try:
            text = pytesseract.image_to_string(image, lang="pan+eng")
        except pytesseract.TesseractError:
            text = pytesseract.image_to_string(image, lang="eng")
        return (text or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR failed for %s: %s", path, exc)
        return ""
