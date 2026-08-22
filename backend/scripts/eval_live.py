#!/usr/bin/env python3
"""Live eval: run retrieve+verify against BaniDB/OpenAI and score quote discipline.

Usage (from backend/):
  unset OPENAI_API_KEY
  set -a && source .env && set +a
  python scripts/eval_live.py

  python scripts/eval_live.py --ids d-meat-ban,h-british-khalsa
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

# Placeholder process env (CI/tests) must not hide backend/.env
_placeholder = {"", "test-disabled", "none", "disabled"}
if (os.environ.get("OPENAI_API_KEY") or "").strip().lower() in _placeholder:
    os.environ.pop("OPENAI_API_KEY", None)

from dotenv import load_dotenv

load_dotenv(BACKEND / ".env", override=True)

from app.config import get_settings
from app.pipeline.claims import extract_claims, _infer_category
from app.pipeline.relevance import analyze_claim
from app.pipeline.retrieve import retrieve_evidence
from app.pipeline.verify import verify_claim
from app.schemas import ExtractedClaim
from app.services.knowledge_base import reset_knowledge_base

get_settings.cache_clear()
reset_knowledge_base()

EVAL_PATH = ROOT / "data" / "golden" / "live_eval.json"
OUT_DIR = BACKEND / ".eval"
FILLER_DEFAULT = [
    "saved me completely",
    "completely fulfilled",
    "totally, completely fulfilled",
    "comforted by meditating",
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower())


def _gurbani_items(verdicts: list[Any]) -> list[Any]:
    items = []
    for v in verdicts:
        for e in v.evidence:
            if (e.source or "") in {"BaniDB", "GurbaniNow"}:
                items.append(e)
    return items


def _blob(verdicts: list[Any]) -> str:
    parts: list[str] = []
    for v in verdicts:
        parts.extend([v.summary or "", v.correction or "", v.claim_text or ""])
        for e in v.evidence:
            parts.extend(
                [
                    e.reference or "",
                    e.excerpt or "",
                    e.translation or "",
                    e.source or "",
                ]
            )
    return _norm(" ".join(parts))


def score_fixture(fx: dict[str, Any], verdicts: list[Any], filler_patterns: list[str]) -> dict[str, Any]:
    reasons: list[str] = []
    blob = _blob(verdicts)
    expected = set(fx.get("expected_verdict") or [])
    labels = [v.verdict for v in verdicts]

    if fx.get("min_claims") and len(verdicts) < int(fx["min_claims"]):
        reasons.append(f"expected>={fx['min_claims']} claims, got {len(verdicts)}")

    if expected and not any(lab in expected for lab in labels):
        reasons.append(f"verdict {labels} not in {sorted(expected)}")

    if fx.get("bucket") == "true_control" and any(lab == "false" for lab in labels):
        reasons.append("true_control marked false")

    gurbani = _gurbani_items(verdicts)
    gexp = fx.get("gurbani_expected") or "optional"
    if gexp == "forbidden" and gurbani:
        refs = [e.reference for e in gurbani]
        reasons.append(f"gurbani forbidden but cited {refs}")
    if gexp == "required" and not gurbani:
        reasons.append("gurbani required but none cited")

    must_match = [m.lower() for m in (fx.get("must_match") or [])]
    if gurbani and must_match:
        gblob = _norm(
            " ".join(
                f"{e.reference} {e.excerpt} {e.translation or ''}" for e in gurbani
            )
        )
        haystack = blob if fx.get("mode") == "extract" else gblob
        if not any(tok in haystack for tok in must_match):
            reasons.append(f"gurbani citations miss must_match {must_match}")

    patterns = list(filler_patterns) + list(fx.get("must_not_quote") or [])
    for pat in patterns:
        if pat and pat.lower() in blob:
            reasons.append(f"filler/forbidden quote: {pat!r}")

    for bad in fx.get("forbidden_evidence") or []:
        if bad.lower() in blob:
            reasons.append(f"known-false collision: {bad!r}")

    angs = sorted({e.reference for e in gurbani if e.reference})
    return {
        "id": fx["id"],
        "pass": not reasons,
        "reasons": reasons,
        "verdicts": labels,
        "confidence": [round(float(v.confidence), 3) for v in verdicts],
        "gurbani_refs": angs,
        "summaries": [(v.summary or "")[:280] for v in verdicts],
        "evidence_sources": sorted(
            {e.source for v in verdicts for e in v.evidence if e.source}
        ),
    }


async def run_one(fx: dict[str, Any]) -> dict[str, Any]:
    text = fx["text"]
    if fx.get("mode") == "extract":
        claims = await extract_claims(text)
        if not claims:
            claims = [ExtractedClaim(text=text, category=_infer_category(text))]
    else:
        claims = [
            ExtractedClaim(
                text=text,
                category=_infer_category(text),
                quoted_gurbani=fx.get("quoted_gurbani"),
            )
        ]

    verdicts = []
    retrieve_notes = []
    for claim in claims:
        brief = await analyze_claim(claim.text)
        evidence = await retrieve_evidence(claim, brief=brief)
        retrieve_notes.append(
            {
                "subject": brief.subject,
                "gurbani_relevant": brief.gurbani_relevant,
                "evidence_ids": [e.get("id") for e in evidence[:8]],
                "sources": sorted({e.get("source") for e in evidence if e.get("source")}),
            }
        )
        verdicts.append(await verify_claim(claim, evidence, brief=brief))
    return {"claims": claims, "verdicts": verdicts, "retrieve": retrieve_notes}


def print_table(rows: list[dict[str, Any]]) -> None:
    print(f"{'id':<24} {'ok':<5} {'verdict':<22} {'angs':<28} reasons")
    print("-" * 110)
    for row in rows:
        flag = "PASS" if row["pass"] else "FAIL"
        verdict = ",".join(row["verdicts"])[:20]
        angs = ",".join(row["gurbani_refs"])[:26] or "-"
        why = "; ".join(row["reasons"])[:60]
        print(f"{row['id']:<24} {flag:<5} {verdict:<22} {angs:<28} {why}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", default="", help="comma-separated fixture ids")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--http-smoke", action="store_true", help="also POST /api/submit once")
    args = parser.parse_args()

    data = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    fixtures = data["fixtures"]
    filler = data.get("rubric", {}).get("filler_patterns") or FILLER_DEFAULT
    if args.ids:
        wanted = {x.strip() for x in args.ids.split(",") if x.strip()}
        fixtures = [f for f in fixtures if f["id"] in wanted]
    if args.limit:
        fixtures = fixtures[: args.limit]

    settings = get_settings()
    print(
        f"llm_enabled={settings.llm_enabled} model={settings.openai_model} "
        f"fixtures={len(fixtures)}",
        flush=True,
    )

    rows = []
    details = []
    for fx in fixtures:
        print(f"… {fx['id']}", flush=True)
        try:
            ran = await run_one(fx)
            row = score_fixture(fx, ran["verdicts"], filler)
            row["retrieve"] = ran["retrieve"]
        except Exception as exc:  # noqa: BLE001
            row = {
                "id": fx["id"],
                "pass": False,
                "reasons": [f"exception: {exc}"],
                "verdicts": [],
                "confidence": [],
                "gurbani_refs": [],
                "summaries": [],
                "evidence_sources": [],
            }
        rows.append(row)
        details.append(row)

    passed = sum(1 for r in rows if r["pass"])
    filler_fails = sum(
        1 for r in rows if any("filler" in x for x in r["reasons"])
    )
    report = {
        "passed": passed,
        "total": len(rows),
        "pass_rate": round(passed / max(len(rows), 1), 3),
        "filler_quote_failures": filler_fails,
        "llm_enabled": settings.llm_enabled,
        "rows": details,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "last_run.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print_table(rows)
    print(
        f"\n{passed}/{len(rows)} passed ({report['pass_rate']*100:.0f}%) "
        f"filler_quote_failures={filler_fails}",
        flush=True,
    )
    print(f"wrote {OUT_DIR / 'last_run.json'}", flush=True)
    if args.http_smoke:
        await _http_smoke()
    solid = report["pass_rate"] >= 0.9 and filler_fails == 0
    return 0 if solid else 1


async def _http_smoke() -> None:
    """One real submit-path check (same FastAPI handlers as the UI)."""
    from httpx import ASGITransport, AsyncClient

    from app.database import init_db
    from app.main import app
    from app.pipeline import run_pipeline

    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/submit",
            data={
                "text": "Sikhi completely forbids eating meat.",
                "language_hint": "english",
            },
        )
        resp.raise_for_status()
        case_id = resp.json()["id"]
        await run_pipeline(case_id)
        got = await client.get(f"/api/cases/{case_id}")
        got.raise_for_status()
        body = got.json()
        blob = json.dumps(body).lower()
        assert "saved me completely" not in blob
        claims = body.get("claims") or []
        assert claims, "submit smoke produced no claims"
        print(
            f"http_smoke case={case_id} status={body.get('status')} "
            f"verdict={claims[0].get('verdict')}",
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
