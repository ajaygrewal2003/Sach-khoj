import asyncio
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure backend package imports resolve
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.database import init_db
from app.main import app
from app.pipeline.claims import extract_claims, _infer_category
from app.pipeline.retrieve import retrieve_evidence
from app.pipeline.verify import _heuristic_verify
from app.schemas import ExtractedClaim
from app.services.knowledge_base import KnowledgeBase, reset_knowledge_base


@pytest.fixture(autouse=True)
def _test_env(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    curated = ROOT / "data" / "curated"
    upload = tmp_path / "uploads"
    upload.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("CURATED_DATA_DIR", str(curated))
    monkeypatch.setenv("UPLOAD_DIR", str(upload))
    monkeypatch.setenv("OPENAI_API_KEY", "test-disabled")
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin")
    get_settings.cache_clear()
    reset_knowledge_base()
    yield
    get_settings.cache_clear()
    reset_knowledge_base()


@pytest.mark.asyncio
async def test_health():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Trigger lifespan manually is hard with ASGITransport; init_db already called
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["llm_enabled"] is False


@pytest.mark.asyncio
async def test_submit_and_process_known_false():
    await init_db()
    from app.database import SessionLocal
    from app.services.seed import seed_known_false_claims
    from app.services.knowledge_base import get_knowledge_base

    get_knowledge_base().load(force=True)
    async with SessionLocal() as session:
        await seed_known_false_claims(session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/submit",
            data={
                "text": "The British created the Khalsa in the 19th century to divide Indians.",
                "language_hint": "english",
            },
        )
        assert resp.status_code == 200
        case = resp.json()
        case_id = case["id"]

        # Run pipeline inline (BackgroundTasks may not execute under ASGITransport the same way)
        from app.pipeline import run_pipeline

        await run_pipeline(case_id)

        got = await client.get(f"/api/cases/{case_id}")
        assert got.status_code == 200
        body = got.json()
        assert body["status"] in {"completed", "needs_review"}
        assert body["claims"]
        assert body["claims"][0]["verdict"] == "false"
        assert body["claims"][0]["evidence"]


@pytest.mark.asyncio
async def test_review_requires_admin():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/review/queue")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_heuristic_claim_extraction():
    claims = await extract_claims(
        "Guru Nanak said on Ang 2000 that Sikhs must abandon Gurmukhi. Also the British created the Khalsa."
    )
    assert len(claims) >= 1


def test_knowledge_base_known_false():
    kb = KnowledgeBase()
    kb.load(force=True)
    hits = kb.match_known_false("The British created the Khalsa identity")
    assert hits
    assert hits[0]["source"] == "Known False Claims Index"


def test_ritual_claim_retrieval_is_on_topic():
    kb = KnowledgeBase()
    kb.load(force=True)
    claim = "Sikhi teaches that rituals alone can guarantee spiritual liberation."
    known = kb.match_known_false(claim)
    assert known, "ritual liberation claim should hit the known-false index"
    assert "ritual" in (known[0]["excerpt"] + known[0]["meta"]["claim_pattern"]).lower()

    hits = kb.search(claim, limit=5)
    refs = " ".join(h["reference"].lower() for h in hits)
    texts = " ".join(h["excerpt"].lower() for h in hits)
    blob = refs + " " + texts
    assert "mukti" in blob or "ritual" in blob or "naam" in blob
    assert "women in sikh" not in blob
    assert "ang numbering" not in blob
    assert "caste hierarchy" not in blob or "ritual" in blob


@pytest.mark.asyncio
async def test_ritual_claim_pipeline_false_without_llm():
    claim = ExtractedClaim(
        text="Sikhi teaches that rituals alone can guarantee spiritual liberation.",
        category=_infer_category("Sikhi teaches that rituals alone can guarantee spiritual liberation."),
    )
    assert claim.category == "doctrine"
    evidence = await retrieve_evidence(claim)
    assert evidence
    assert any(e.get("source") == "Known False Claims Index" for e in evidence)
    verdict = _heuristic_verify(claim, evidence)
    assert verdict.verdict == "false"
    assert verdict.evidence
    joined = " ".join(e.excerpt.lower() for e in verdict.evidence)
    assert "women in sikh" not in joined
    assert "1430" not in joined


def test_scripture_queries_for_form_claim():
    from app.pipeline.gurbani_topics import scripture_queries_for

    qs = scripture_queries_for(
        "Sikhi teaches that God can only be worshipped in one specific physical form."
    )
    labels = {q.query for q in qs}
    assert "formless" in labels or "form" in labels
    assert any(q.searchtype == 3 for q in qs)


@pytest.mark.asyncio
async def test_form_claim_false_without_llm():
    text = "Sikhi teaches that God can only be worshipped in one specific physical form."
    claim = ExtractedClaim(text=text, category=_infer_category(text))
    assert claim.category == "doctrine"
    evidence = await retrieve_evidence(claim)
    assert evidence
    assert any(e.get("source") == "Known False Claims Index" for e in evidence)
    verdict = _heuristic_verify(claim, evidence)
    assert verdict.verdict == "false"


def test_golden_set_shapes():
    path = ROOT / "data" / "golden" / "golden_set.json"
    data = json.loads(path.read_text())
    assert len(data["examples"]) >= 8
    for ex in data["examples"]:
        claim = ExtractedClaim(text=ex["text"], category="other")
        kb = KnowledgeBase()
        kb.load(force=True)
        evidence = kb.match_known_false(ex["text"]) + kb.search(ex["text"], limit=3)
        verdict = _heuristic_verify(claim, evidence)
        if ex["type"] != "true_control":
            if evidence and evidence[0].get("source") == "Known False Claims Index":
                assert verdict.verdict in ex["expected_verdict"]
