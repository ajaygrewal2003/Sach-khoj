"""Turn videos and images into text the claim pipeline can verify.

Video → spoken transcript (Whisper) + sampled-frame descriptions (vision model,
including exact on-screen text). Image → vision description + OCR. Everything
degrades gracefully: missing key or ffmpeg failure returns empty strings and
the pipeline continues with whatever text it has.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


async def understand_video(path: str | Path) -> dict[str, str]:
    """Full understanding of a video: what was said and what was shown."""
    path = Path(path)
    if not path.exists():
        return {"transcript": "", "visuals": ""}
    transcript_task = asyncio.create_task(transcribe_media(path))
    visuals_task = asyncio.create_task(describe_video_frames(path))
    transcript = await transcript_task
    visuals = await visuals_task
    return {"transcript": transcript, "visuals": visuals}


async def understand_image(path: str | Path) -> str:
    """Vision read of an image post: description + exact visible text."""
    path = Path(path)
    if not path.exists():
        return ""
    settings = get_settings()
    if not settings.llm_enabled:
        return ""
    data = await asyncio.to_thread(path.read_bytes)
    if len(data) > 20 * 1024 * 1024:
        return ""
    b64 = base64.b64encode(data).decode("ascii")
    mime = _image_mime(path)
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        resp = await client.chat.completions.create(
            model=settings.openai_vision_model or settings.openai_model,
            max_tokens=700,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "This is a social media post image being fact-checked. "
                                "1) Transcribe ALL visible text exactly (any language, including "
                                "Gurmukhi). 2) Then briefly describe what the image shows and any "
                                "claims it makes. Do not add your own opinion of the claims."
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                }
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Image understanding failed for %s: %s", path, exc)
        return ""


async def transcribe_media(path: str | Path) -> str:
    """Transcribe speech from a video/audio file via Whisper. '' on failure."""
    settings = get_settings()
    if not settings.llm_enabled:
        return ""
    path = Path(path)

    audio_path = await asyncio.to_thread(_extract_audio, path)
    if audio_path is None:
        return ""
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        with audio_path.open("rb") as fh:
            resp = await client.audio.transcriptions.create(
                model=settings.openai_transcribe_model,
                file=fh,
            )
        return (getattr(resp, "text", None) or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Transcription failed for %s: %s", path, exc)
        return ""
    finally:
        audio_path.unlink(missing_ok=True)


def _extract_audio(path: Path) -> Path | None:
    """Compress audio to a small mp3 Whisper accepts. None when there is no audio."""
    out = Path(tempfile.mkstemp(suffix=".mp3")[1])
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "48k",
        "-t",
        str(get_settings().max_video_seconds),
        str(out),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Audio extraction failed for %s: %s", path, exc)
        out.unlink(missing_ok=True)
        return None
    if not out.exists() or out.stat().st_size < 1024:
        out.unlink(missing_ok=True)
        return None
    return out


async def describe_video_frames(path: str | Path, frames: int | None = None) -> str:
    """Sample frames across the video and have the vision model read them."""
    settings = get_settings()
    if not settings.llm_enabled:
        return ""
    path = Path(path)
    frames = frames or settings.video_frames_to_sample

    jpegs = await asyncio.to_thread(_sample_frames, path, frames)
    if not jpegs:
        return ""
    try:
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "These are frames sampled in order from a social media video being "
                    "fact-checked. 1) Transcribe ALL on-screen text exactly (captions, "
                    "overlays, signs — any language including Gurmukhi). 2) Describe what "
                    "is shown and what the video appears to claim visually. "
                    "Do not evaluate the claims."
                ),
            }
        ]
        for jpeg in jpegs:
            b64 = base64.b64encode(jpeg).decode("ascii")
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}}
            )
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        resp = await client.chat.completions.create(
            model=settings.openai_vision_model or settings.openai_model,
            max_tokens=800,
            messages=[{"role": "user", "content": content}],
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Frame understanding failed for %s: %s", path, exc)
        return ""


def _sample_frames(path: Path, frames: int) -> list[bytes]:
    duration = _probe_duration(path)
    if duration <= 0:
        return []
    timestamps = [duration * (i + 0.5) / frames for i in range(frames)]
    jpegs: list[bytes] = []
    for ts in timestamps:
        out = Path(tempfile.mkstemp(suffix=".jpg")[1])
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{ts:.2f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            "scale='min(768,iw)':-2",
            "-q:v",
            "5",
            str(out),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            if out.exists() and out.stat().st_size > 500:
                jpegs.append(out.read_bytes())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Frame extraction at %.1fs failed: %s", ts, exc)
        finally:
            out.unlink(missing_ok=True)
    return jpegs


def _probe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
        return float((data.get("format") or {}).get("duration") or 0.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ffprobe failed for %s: %s", path, exc)
        return 0.0


def _image_mime(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/jpeg")
