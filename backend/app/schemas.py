from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


VerdictType = Literal["false", "misleading", "unverified", "true", "not_checkable"]
ClaimCategory = Literal[
    "gurbani_misquote",
    "out_of_context",
    "historical",
    "rehat",
    "doctrine",
    "propaganda",
    "other",
]


class SubmitRequest(BaseModel):
    url: str | None = None
    text: str | None = None
    language_hint: str | None = Field(default="auto", description="gurmukhi | english | auto")


class EvidenceItem(BaseModel):
    id: str
    source: str
    reference: str
    excerpt: str
    url: str | None = None
    score: float | None = None


class ExtractedClaim(BaseModel):
    text: str
    category: ClaimCategory = "other"
    quoted_gurbani: str | None = None


class ClaimVerdict(BaseModel):
    claim_text: str
    category: str
    quoted_gurbani: str | None = None
    verdict: VerdictType
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    correction: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class ClaimOut(BaseModel):
    id: str
    ordinal: int
    text: str
    category: str
    quoted_gurbani: str | None = None
    verdict: str | None = None
    confidence: float | None = None
    summary: str | None = None
    correction: str | None = None
    evidence: list[dict[str, Any]] | None = None

    model_config = {"from_attributes": True}


class CaseOut(BaseModel):
    id: str
    status: str
    source_url: str | None = None
    submitted_text: str | None = None
    language_hint: str | None = None
    media_filename: str | None = None
    extracted_text: str | None = None
    page_title: str | None = None
    overall_verdict: str | None = None
    overall_confidence: float | None = None
    overall_summary: str | None = None
    error_message: str | None = None
    pipeline_log: list[Any] | None = None
    review_status: str | None = None
    reviewer_notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    claims: list[ClaimOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class CaseListOut(BaseModel):
    items: list[CaseOut]
    total: int


class ReviewAction(BaseModel):
    action: Literal["approve", "override", "dismiss"]
    notes: str | None = None
    overall_verdict: VerdictType | None = None
    claim_overrides: list[dict[str, Any]] | None = None


class HealthOut(BaseModel):
    status: str
    llm_enabled: bool
    app: str


class KnownFalseIn(BaseModel):
    claim_pattern: str
    category: str = "propaganda"
    explanation: str
    correction: str
    source_refs: list[str] | None = None
