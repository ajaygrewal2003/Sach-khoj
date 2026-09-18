from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Case, CaseStatus
from app.schemas import CaseListOut, CaseOut

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("", response_model=CaseListOut)
async def list_cases(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: CaseStatus | None = None,
) -> CaseListOut:
    filters = []
    if status is not None:
        filters.append(Case.status == status)

    total = await db.scalar(select(func.count()).select_from(Case).where(*filters)) or 0
    result = await db.scalars(
        select(Case)
        .where(*filters)
        .options(selectinload(Case.claims))
        .order_by(Case.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = list(result)
    return CaseListOut(items=items, total=total)


@router.get("/{case_id}", response_model=CaseOut)
async def get_case(case_id: str, db: AsyncSession = Depends(get_db)) -> Case:
    case = await db.get(Case, case_id, options=[selectinload(Case.claims)])
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case
