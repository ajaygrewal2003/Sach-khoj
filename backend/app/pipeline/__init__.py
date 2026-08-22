from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import SessionLocal
from app.models import Case, CaseStatus, Claim, ReviewStatus, VerdictLabel
from app.pipeline.claims import extract_claims
from app.pipeline.ingest import ingest_submission
from app.pipeline.retrieve import retrieve_evidence
from app.pipeline.verify import verify_claim

logger = logging.getLogger(__name__)

VERDICT_PRIORITY = {
    "false": 5,
    "misleading": 4,
    "unverified": 3,
    "not_checkable": 2,
    "true": 1,
}


async def run_pipeline(case_id: str) -> None:
    async with SessionLocal() as session:
        case = await session.get(Case, case_id, options=[selectinload(Case.claims)])
        if not case:
            logger.error("Case %s not found", case_id)
            return

        case.status = CaseStatus.processing
        case.pipeline_log = list(case.pipeline_log or [])
        await session.commit()

        try:
            await _process(session, case)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Pipeline failed for %s", case_id)
            case.status = CaseStatus.failed
            case.error_message = str(exc)
            case.pipeline_log = (case.pipeline_log or []) + [{"stage": "error", "message": str(exc)}]
            await session.commit()


async def _process(session: AsyncSession, case: Case) -> None:
    settings = get_settings()
    log: list[dict[str, Any]] = list(case.pipeline_log or [])

    ingest = await ingest_submission(
        url=case.source_url,
        text=case.submitted_text,
        media_path=case.media_path,
    )
    log.extend(ingest["log"])
    case.extracted_text = ingest["extracted_text"]
    case.page_title = ingest.get("page_title")
    case.page_metadata = ingest.get("page_metadata")

    if ingest.get("message"):
        log.append({"stage": "ingest", "event": "notice", "message": ingest["message"]})

    text = (case.extracted_text or "").strip()
    if not text:
        case.status = CaseStatus.failed
        case.error_message = ingest.get("message") or (
            "No text could be extracted. Paste caption text or upload a clearer screenshot."
        )
        case.pipeline_log = log
        await session.commit()
        return

    claims = await extract_claims(text, language_hint=case.language_hint)
    log.append({"stage": "claims", "event": "extracted", "count": len(claims)})

    # Clear prior claims on re-run
    case.claims.clear()
    await session.flush()

    verdicts = []
    for i, claim in enumerate(claims):
        evidence = await retrieve_evidence(claim)
        log.append(
            {
                "stage": "retrieve",
                "claim_index": i,
                "evidence_count": len(evidence),
                "sources": sorted({e.get("source") for e in evidence if e.get("source")}),
            }
        )
        verdict = await verify_claim(claim, evidence)
        verdicts.append(verdict)
        case.claims.append(
            Claim(
                ordinal=i,
                text=verdict.claim_text,
                category=verdict.category,
                quoted_gurbani=verdict.quoted_gurbani,
                verdict=verdict.verdict,
                confidence=verdict.confidence,
                summary=verdict.summary,
                correction=verdict.correction,
                evidence=[e.model_dump() for e in verdict.evidence],
                retrieved_passages=evidence,
            )
        )
        log.append(
            {
                "stage": "verify",
                "claim_index": i,
                "verdict": verdict.verdict,
                "confidence": verdict.confidence,
            }
        )

    overall_verdict, overall_confidence, overall_summary = _aggregate(verdicts, ingest)
    case.overall_verdict = overall_verdict
    case.overall_confidence = overall_confidence
    case.overall_summary = overall_summary
    case.pipeline_log = log

    needs_review = (
        not verdicts
        or overall_confidence < settings.confidence_review_threshold
        or overall_verdict in {"unverified", "not_checkable"}
        or any(v.verdict == "unverified" or v.confidence < settings.confidence_review_threshold for v in verdicts)
    )
    if needs_review:
        case.status = CaseStatus.needs_review
        case.review_status = ReviewStatus.pending
    else:
        case.status = CaseStatus.completed
        case.review_status = None

    await session.commit()


def _aggregate(verdicts, ingest: dict[str, Any]) -> tuple[str, float, str]:
    if not verdicts:
        msg = "No checkable claims were extracted from the submitted content."
        if ingest.get("message"):
            msg += f" Note: {ingest['message']}"
        return VerdictLabel.not_checkable.value, 0.4, msg

    top = max(verdicts, key=lambda v: (VERDICT_PRIORITY.get(v.verdict, 0), v.confidence))
    avg_conf = sum(v.confidence for v in verdicts) / len(verdicts)
    false_count = sum(1 for v in verdicts if v.verdict in {"false", "misleading"})
    true_count = sum(1 for v in verdicts if v.verdict == "true")

    if len(verdicts) == 1:
        return top.verdict, round(avg_conf, 3), verdicts[0].summary

    if false_count:
        summary = (
            f"Found {false_count} claim(s) assessed as false or misleading out of {len(verdicts)}. "
            "Review cited Ang/shabad/Rehat evidence before sharing. "
            "This is an AI-assisted research tool, not Panthic authority."
        )
    elif true_count == len(verdicts):
        summary = (
            f"All {len(verdicts)} extracted claim(s) appear consistent with retrieved sources. "
            "Still verify citations independently for religious guidance."
        )
    else:
        summary = (
            f"Assessed {len(verdicts)} claim(s); strongest signal is '{top.verdict}'. "
            "Low-confidence or unverified items should go to human review."
        )

    return top.verdict, round(avg_conf, 3), summary
