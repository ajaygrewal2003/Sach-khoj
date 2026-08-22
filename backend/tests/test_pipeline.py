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
from app.pipeline.claims import extract_claims
from app.pipeline.verify import _heuristic_verify
from app.schemas import ExtractedClaim
from app.services.knowledge_base import KnowledgeBase


@pytest.fixture(autouse=True)
def _test_env(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    curated = ROOT / "data" / "curated"
    upload = tmp_path / "uploads"
    upload.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("CURATED_DATA_DIR", str(curated))
    monkeypatch.setenv("UPLOAD_DIR", str(upload))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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


def test_golden_set_shapes():
    path = ROOT / "data" / "golden" / "golden_set.json"
    data = json.loads(path.read_text())
    assert len(data["examples"]) >= 8
    for ex in data["examples"]:
        claim = ExtractedClaim(text=ex["text"], category="other")
        # Smoke the heuristic verifier with KB evidence
        kb = KnowledgeBase()
        kb.load(force=True)
        evidence = kb.match_known_false(ex["text"]) + kb.search(ex["text"], limit=3)
        verdict = _heuristic_verify(claim, evidence)
        if ex["type"] != "true_control":
            # For known misinfo patterns we expect false/misleading when matched
            if evidence and evidence[0].get("source") == "Known False Claims Index":
                assert verdict.verdict in ex["expected_verdict"]
