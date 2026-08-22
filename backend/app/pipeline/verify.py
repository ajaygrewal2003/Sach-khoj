from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from app.schemas import ClaimVerdict, EvidenceItem, ExtractedClaim, VerdictType
from app.services.llm import VERDICT_SCHEMA_HINT, chat_json


async def verify_claim(claim: ExtractedClaim, evidence: list[dict[str, Any]]) -> ClaimVerdict:
    """Stage 4 — produce structured verdict grounded only in retrieved evidence."""
    llm_verdict = await _llm_verify(claim, evidence)
    if llm_verdict:
        return llm_verdict
    return _heuristic_verify(claim, evidence)


async def _llm_verify(claim: ExtractedClaim, evidence: list[dict[str, Any]]) -> ClaimVerdict | None:
    if not evidence:
        return ClaimVerdict(
            claim_text=claim.text,
            category=claim.category,
            quoted_gurbani=claim.quoted_gurbani,
            verdict="unverified",
            confidence=0.35,
            summary="No authoritative passages were retrieved for this claim, so it cannot be verified yet.",
            correction=None,
            evidence=[],
        )

    compact = [
        {
            "id": e.get("id"),
            "source": e.get("source"),
            "reference": e.get("reference"),
            "excerpt": (e.get("excerpt") or "")[:500],
            "translation": (e.get("translation") or "")[:300] if e.get("translation") else None,
        }
        for e in evidence
    ]
    system = (
        "You are an evidence-grounded assistant helping researchers check claims about Sikhism and Gurbani. "
        "Never invent Ang numbers, shabad IDs, or quotations. "
        + VERDICT_SCHEMA_HINT
    )
    user = (
        f"Claim category: {claim.category}\n"
        f"Claim: {claim.text}\n"
        f"Quoted gurbani (if any): {claim.quoted_gurbani}\n\n"
        f"Retrieved evidence (cite only by id):\n{compact}"
    )
    data = await chat_json(system, user)
    if not data:
        return None

    allowed_ids = {e.get("id") for e in evidence if e.get("id")}
    cited_ids = [eid for eid in (data.get("evidence_ids") or []) if eid in allowed_ids]
    verdict = _coerce_verdict(data.get("verdict"))
    confidence = _coerce_confidence(data.get("confidence"), default=0.5)

    # Enforce citation rules
    if verdict in {"false", "misleading", "true"} and not cited_ids:
        verdict = "unverified"
        confidence = min(confidence, 0.45)

    cited_evidence = [_to_evidence_item(e) for e in evidence if e.get("id") in set(cited_ids)]
    if not cited_evidence and evidence and verdict == "unverified":
        # Still surface top retrieved passages for human reviewers
        cited_evidence = [_to_evidence_item(e) for e in evidence[:3]]

    return ClaimVerdict(
        claim_text=claim.text,
        category=claim.category,
        quoted_gurbani=claim.quoted_gurbani,
        verdict=verdict,
        confidence=confidence,
        summary=(data.get("summary") or "Assessment complete.").strip(),
        correction=(data.get("correction") or None),
        evidence=cited_evidence,
    )


def _heuristic_verify(claim: ExtractedClaim, evidence: list[dict[str, Any]]) -> ClaimVerdict:
    """Deterministic fallback used when LLM is unavailable."""
    if not evidence:
        return ClaimVerdict(
            claim_text=claim.text,
            category=claim.category,
            quoted_gurbani=claim.quoted_gurbani,
            verdict="unverified",
            confidence=0.3,
            summary="No matching evidence found in BaniDB/GurbaniNow or the curated corpus.",
            correction=None,
            evidence=[],
        )

    known = [e for e in evidence if e.get("source") == "Known False Claims Index"]
    if known:
        meta = (known[0].get("meta") or {})
        return ClaimVerdict(
            claim_text=claim.text,
            category=claim.category,
            quoted_gurbani=claim.quoted_gurbani,
            verdict="false",
            confidence=min(0.92, 0.7 + float(known[0].get("score") or 0.2) * 0.2),
            summary=meta.get("explanation")
            or "This claim matches a known misinformation pattern in the curated index.",
            correction=meta.get("correction"),
            evidence=[_to_evidence_item(e) for e in known[:2]],
        )

    gurbani_hits = [e for e in evidence if e.get("source") in {"BaniDB", "GurbaniNow"}]
    quote = (claim.quoted_gurbani or "").strip()
    if quote and gurbani_hits:
        best = max(gurbani_hits, key=lambda e: fuzz.partial_ratio(quote, e.get("excerpt") or ""))
        score = fuzz.partial_ratio(quote, best.get("excerpt") or "")
        if score >= 88:
            return ClaimVerdict(
                claim_text=claim.text,
                category=claim.category,
                quoted_gurbani=claim.quoted_gurbani,
                verdict="true" if claim.category != "out_of_context" else "misleading",
                confidence=round(score / 100.0, 2),
                summary=(
                    f"A close match was found in {best.get('source')} ({best.get('reference')}). "
                    + (
                        "The verse appears authentic; review surrounding framing for out-of-context misuse."
                        if claim.category == "out_of_context"
                        else "The quoted wording aligns with the retrieved shabad."
                    )
                ),
                correction=None
                if claim.category != "out_of_context"
                else "Verify that the commentary around the shabad matches its traditional meaning and context.",
                evidence=[_to_evidence_item(best)],
            )
        if score < 55:
            return ClaimVerdict(
                claim_text=claim.text,
                category=claim.category,
                quoted_gurbani=claim.quoted_gurbani,
                verdict="false",
                confidence=0.72,
                summary=(
                    f"The quoted text does not closely match retrieved Gurbani. "
                    f"Nearest retrieved reference is {best.get('reference')} from {best.get('source')}."
                ),
                correction=f"Compare against {best.get('reference')}: {(best.get('excerpt') or '')[:180]}",
                evidence=[_to_evidence_item(best)],
            )

    curated = [e for e in evidence if e.get("source") not in {"BaniDB", "GurbaniNow", "Known False Claims Index"}]
    top = (known or gurbani_hits or curated or evidence)[:3]
    return ClaimVerdict(
        claim_text=claim.text,
        category=claim.category,
        quoted_gurbani=claim.quoted_gurbani,
        verdict="unverified",
        confidence=0.48,
        summary=(
            "Related reference material was retrieved, but without an LLM key the tool will not force a hard verdict. "
            "A human reviewer should compare the claim to the cited passages."
        ),
        correction=None,
        evidence=[_to_evidence_item(e) for e in top],
    )


def _to_evidence_item(raw: dict[str, Any]) -> EvidenceItem:
    return EvidenceItem(
        id=str(raw.get("id") or "unknown"),
        source=str(raw.get("source") or "unknown"),
        reference=str(raw.get("reference") or ""),
        excerpt=str(raw.get("excerpt") or "")[:800],
        url=raw.get("url"),
        score=raw.get("score"),
    )


def _coerce_verdict(value: Any) -> VerdictType:
    allowed = {"false", "misleading", "unverified", "true", "not_checkable"}
    if isinstance(value, str) and value in allowed:
        return value  # type: ignore[return-value]
    return "unverified"


def _coerce_confidence(value: Any, default: float = 0.5) -> float:
    try:
        conf = float(value)
    except (TypeError, ValueError):
        conf = default
    return max(0.0, min(1.0, conf))
