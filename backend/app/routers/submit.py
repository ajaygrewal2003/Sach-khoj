from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.models import Case, CaseStatus
from app.pipeline import run_pipeline
from app.schemas import CaseOut

router = APIRouter(prefix="/api", tags=["submit"])


@router.post("/submit", response_model=CaseOut)
async def submit_case(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    url: str | None = Form(default=None),
    text: str | None = Form(default=None),
    language_hint: str | None = Form(default="auto"),
    media: UploadFile | None = File(default=None),
) -> Case:
    settings = get_settings()
    url = (url or "").strip() or None
    text = (text or "").strip() or None

    if not url and not text and media is None:
        raise HTTPException(status_code=400, detail="Provide at least a URL, text, or media file.")

    media_path = None
    media_filename = None
    if media is not None and media.filename:
        data = await media.read()
        if len(data) > settings.max_upload_bytes:
            limit_mb = settings.max_upload_bytes // (1024 * 1024)
            raise HTTPException(status_code=400, detail=f"Upload exceeds {limit_mb}MB limit.")
        safe_name = _safe_filename(media.filename)
        settings.upload_path.mkdir(parents=True, exist_ok=True)
        dest = settings.upload_path / f"{uuid.uuid4().hex}_{safe_name}"
        dest.write_bytes(data)
        media_path = str(dest)
        media_filename = media.filename

    case = Case(
        status=CaseStatus.pending,
        source_url=url,
        submitted_text=text,
        language_hint=language_hint or "auto",
        media_path=media_path,
        media_filename=media_filename,
        pipeline_log=[{"stage": "submit", "event": "accepted"}],
    )
    db.add(case)
    await db.commit()
    await db.refresh(case, attribute_names=["claims"])

    background_tasks.add_task(run_pipeline, case.id)
    return case


def _safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^\w.\-]+", "_", name)
    return name[:120] or "upload.bin"
