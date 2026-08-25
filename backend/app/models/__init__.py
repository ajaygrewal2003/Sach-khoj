from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


class CaseStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    needs_review = "needs_review"


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    overridden = "overridden"
    dismissed = "dismissed"


class VerdictLabel(str, enum.Enum):
    false = "false"
    misleading = "misleading"
    unverified = "unverified"
    true = "true"
    not_checkable = "not_checkable"


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus, native_enum=False), default=CaseStatus.pending, index=True
    )
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    submitted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    language_hint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    media_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    media_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    page_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    overall_verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pipeline_log: Mapped[list | None] = mapped_column(JSON, nullable=True)
    review_status: Mapped[ReviewStatus | None] = mapped_column(
        Enum(ReviewStatus, native_enum=False), nullable=True, index=True
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    claims: Mapped[list[Claim]] = relationship(back_populates="case", cascade="all, delete-orphan")


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), default="other")
    quoted_gurbani: Mapped[str | None] = mapped_column(Text, nullable=True)
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[list | None] = mapped_column(JSON, nullable=True)
    retrieved_passages: Mapped[list | None] = mapped_column(JSON, nullable=True)

    case: Mapped[Case] = relationship(back_populates="claims")


class KnownFalseClaim(Base):
    __tablename__ = "known_false_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_pattern: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), default="propaganda")
    explanation: Mapped[str] = mapped_column(Text)
    correction: Mapped[str] = mapped_column(Text)
    source_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
