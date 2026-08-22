from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.models import Case, CaseStatus, KnownFalseClaim, ReviewStatus
from app.schemas import CaseListOut, CaseOut, KnownFalseIn, ReviewAction
from app.services.knowledge_base import get_knowledge_base

router = APIRouter(prefix="/api/review", tags=["review"])


def require_admin(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    expected = f"Bearer {settings.admin_token}"
    if not authorization or authorization.strip() != expected:
        raise HTTPException(status_code=401, detail="Admin authorization required")


@router.get("/queue", response_model=CaseListOut, dependencies=[Depends(require_admin)])
async def review_queue(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> CaseListOut:
    filt = or_(Case.status == CaseStatus.needs_review, Case.review_status == ReviewStatus.pending)
    total = await db.scalar(select(func.count()).select_from(Case).where(filt)) or 0
    result = await db.scalars(
        select(Case)
        .where(filt)
        .options(selectinload(Case.claims))
        .order_by(Case.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    return CaseListOut(items=list(result), total=total)


@router.post("/{case_id}", response_model=CaseOut, dependencies=[Depends(require_admin)])
async def review_case(
    case_id: str,
    body: ReviewAction,
    db: AsyncSession = Depends(get_db),
) -> Case:
    case = await db.get(Case, case_id, options=[selectinload(Case.claims)])
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    case.reviewer_notes = body.notes
    if body.action == "approve":
        case.review_status = ReviewStatus.approved
        case.status = CaseStatus.completed
    elif body.action == "dismiss":
        case.review_status = ReviewStatus.dismissed
        case.status = CaseStatus.completed
    elif body.action == "override":
        case.review_status = ReviewStatus.overridden
        case.status = CaseStatus.completed
        if body.overall_verdict:
            case.overall_verdict = body.overall_verdict
        if body.claim_overrides:
            by_id = {c.id: c for c in case.claims}
            for item in body.claim_overrides:
                claim = by_id.get(item.get("id"))
                if not claim:
                    continue
                if item.get("verdict"):
                    claim.verdict = item["verdict"]
                if item.get("summary"):
                    claim.summary = item["summary"]
                if item.get("correction") is not None:
                    claim.correction = item["correction"]
                if item.get("confidence") is not None:
                    claim.confidence = float(item["confidence"])
    else:
        raise HTTPException(status_code=400, detail="Unknown action")

    await db.commit()
    await db.refresh(case)
    return case


@router.get("/known-false", dependencies=[Depends(require_admin)])
async def list_known_false(db: AsyncSession = Depends(get_db)) -> dict:
    rows = list(await db.scalars(select(KnownFalseClaim).order_by(KnownFalseClaim.created_at.desc())))
    return {
        "items": [
            {
                "id": r.id,
                "claim_pattern": r.claim_pattern,
                "category": r.category,
                "explanation": r.explanation,
                "correction": r.correction,
                "source_refs": r.source_refs,
            }
            for r in rows
        ]
    }


@router.post("/known-false", dependencies=[Depends(require_admin)])
async def add_known_false(body: KnownFalseIn, db: AsyncSession = Depends(get_db)) -> dict:
    row = KnownFalseClaim(
        claim_pattern=body.claim_pattern,
        category=body.category,
        explanation=body.explanation,
        correction=body.correction,
        source_refs=body.source_refs,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # Also append to in-memory KB for immediate retrieval
    kb = get_knowledge_base()
    kb.known_false.append(
        {
            "id": row.id,
            "claim_pattern": row.claim_pattern,
            "category": row.category,
            "explanation": row.explanation,
            "correction": row.correction,
            "source_refs": row.source_refs,
        }
    )
    return {"id": row.id, "status": "created"}
