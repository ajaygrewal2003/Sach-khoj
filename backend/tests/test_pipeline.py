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
from app.services.semantic_index import reset_semantic_index


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
    reset_semantic_index()
    yield
    get_settings.cache_clear()
    reset_knowledge_base()
    reset_semantic_index()


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


def test_scripture_queries_for_many_claim_types():
    from app.pipeline.gurbani_topics import scripture_queries_for

    form = {
        q.query.lower()
        for q in scripture_queries_for(
            "Sikhi teaches that God can only be worshipped in one specific physical form."
        )
    }
    assert "formless" in form or "form" in form

    ritual = scripture_queries_for("Sikhi teaches that rituals alone can guarantee spiritual liberation.")
    assert ritual

    langar = scripture_queries_for("Langar is only for baptized Sikhs; foreigners are not allowed.")
    assert langar

    women = scripture_queries_for("Women cannot take Amrit according to the Gurus.")
    assert women

    meat_qs = scripture_queries_for("Sikhi completely forbids eating meat.")
    meat_labels = {q.query.lower() for q in meat_qs}
    assert "completely" not in meat_labels
    assert "forbids" not in meat_labels
    assert "lord" not in meat_labels
    assert any("meat" in q.query.lower() or "flesh" in q.query.lower() or q.query == "ਮਾਸ" for q in meat_qs)

    caste_qs = {q.query.lower() for q in scripture_queries_for("Sikhi completely rejects the caste system.")}
    assert "completely" not in caste_qs
    assert any("caste" in q for q in caste_qs)

    novel = scripture_queries_for("Sikhism forbids dancing at weddings.")
    novel_labels = {q.query.lower() for q in novel}
    assert "forbids" not in novel_labels
    assert novel, "novel claims should still search their distinctive nouns"
    assert any("danc" in q or "wedding" in q for q in novel_labels)


def test_off_topic_gurbani_is_dropped():
    from app.pipeline.retrieve import _score_scripture_against_claim
    from app.services.knowledge_base import KnowledgeBase

    junk = _score_scripture_against_claim(
        "Sikhi completely forbids eating meat.",
        {
            "id": "banidb:x:133",
            "source": "BaniDB",
            "reference": "Ang 133",
            "excerpt": "ਸਭ ਛਡਾਈ",
            "translation": "My Lord and Master Himself has saved me completely; I am comforted by meditating on the Lord.",
        },
    )
    assert junk is None

    ok = _score_scripture_against_claim(
        "Sikhi completely forbids eating meat.",
        {
            "id": "banidb:x:144",
            "source": "BaniDB",
            "reference": "Ang 144",
            "excerpt": "ਇਕਿ ਮਾਸਹਾਰੀ",
            "translation": "Some eat meat, while others eat grass.",
        },
    )
    assert ok is not None

    kb = KnowledgeBase()
    kb.load(force=True)
    hits = kb.match_known_false("Sikhi completely forbids eating meat.")
    assert hits
    assert "meat" in hits[0]["meta"]["claim_pattern"].lower()
    assert "education" not in hits[0]["meta"]["claim_pattern"].lower()


def test_known_false_does_not_match_on_rehat_boilerplate():
    kb = KnowledgeBase()
    kb.load(force=True)
    hits = kb.match_known_false(
        "A Sikh believes in the ten Gurus and the Guru Granth Sahib according to Rehat Maryada summaries."
    )
    patterns = " ".join((h.get("meta") or {}).get("claim_pattern", "") for h in hits).lower()
    assert "meat" not in patterns
    assert "vegetarian" not in patterns


def test_filler_search_terms_rejected():
    from app.pipeline.relevance import (
        claim_focus_tokens,
        is_filler_query,
        is_usable_search_query,
        verse_matches_claim,
    )

    focus = claim_focus_tokens("Sikhi completely forbids eating meat.")
    assert "meat" in focus
    assert "completely" not in focus
    assert is_filler_query("completely")
    assert is_filler_query("forbids")
    assert is_filler_query("Lord")
    assert not is_usable_search_query("completely", claim_focus=focus)
    assert is_usable_search_query("eat meat", claim_focus=focus)
    assert is_usable_search_query("flesh", claim_focus=focus)
    assert verse_matches_claim(
        "Sikhi completely forbids eating meat.",
        translation="Some eat meat, while others eat grass.",
    )
    assert not verse_matches_claim(
        "Sikhi completely forbids eating meat.",
        translation="says Nanak, I was totally, completely fulfilled.",
    )
    assert not verse_matches_claim(
        "Sikhi completely forbids eating meat.",
        translation="The framework is made up of bones, flesh and veins; the poor soul-bird dwells within it.",
    )
    assert verse_matches_claim(
        "Sikhi completely rejects the caste system.",
        translation="There is no caste in the world hereafter.",
    )
    assert not verse_matches_claim(
        "Sikhi completely rejects the caste system.",
        translation="My Lord and Master Himself has saved me completely.",
    )
    assert verse_matches_claim(
        "Sikhi teaches that God can only be worshipped in one specific physical form.",
        translation="The Lord is formless; He has no form or feature.",
    )


def test_verifier_ignores_filler_gurbani():
    from app.pipeline.verify import _heuristic_verify

    claim_text = "Sikhi completely forbids eating meat."
    claim = ExtractedClaim(text=claim_text, category="doctrine")
    kb = KnowledgeBase()
    kb.load(force=True)
    known = kb.match_known_false(claim_text)
    assert known
    junk = {
        "id": "banidb:x:133",
        "source": "BaniDB",
        "match_reason": "scripture_topic",
        "reference": "Ang 133",
        "excerpt": "ਸਭ ਛਡਾਈ ਖਸਮਿ ਆਪਿ ਹਰਿ ਜਪਿ ਭਈ ਠਰੂਰੇ ॥੬॥",
        "translation": (
            "My Lord and Master Himself has saved me completely; "
            "I am comforted by meditating on the Lord."
        ),
        "score": 0.9,
    }
    good = {
        "id": "banidb:x:144",
        "source": "BaniDB",
        "match_reason": "scripture_topic",
        "reference": "Ang 144",
        "excerpt": "ਇਕਿ ਮਾਸਹਾਰੀ",
        "translation": "Some eat meat, while others eat grass.",
        "score": 0.8,
    }
    verdict = _heuristic_verify(claim, known + [junk, good])
    blob = f"{verdict.summary} {verdict.correction or ''} " + " ".join(
        f"{e.reference} {e.translation or ''} {e.excerpt}" for e in verdict.evidence
    )
    assert "Ang 133" not in blob
    assert "saved me completely" not in blob.lower()
    assert "completely fulfilled" not in blob.lower()
    assert "Ang 144" in blob
    assert "meat" in blob.lower()


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


def test_explanation_weaves_in_gurbani():
    from app.pipeline.verify import _ensure_gurbani_in_explanation

    evidence = [
        {
            "source": "BaniDB",
            "reference": "Ang 141",
            "excerpt": "ਪਹਿਲਾ ਸਚੁ ਹਲਾਲ ਦੁਇ ਤੀਜਾ ਖੈਰ ਖੁਦਾਇ ॥",
            "translation": "Let the first be truthfulness, the second honest living, and the third charity in the Name of God.",
        }
    ]
    text = _ensure_gurbani_in_explanation(
        "Sikhi encourages honest work and earning a living through honest means.",
        "Sikh teachings emphasize honest work.",
        evidence,
        "true",
    )
    assert "Ang 141" in text
    assert "honest living" in text.lower()
    assert "ਪਹਿਲਾ ਸਚੁ" in text


def test_banidb_english_hits_require_whole_words():
    from app.integrations.banidb import BaniDBClient

    client = BaniDBClient()
    meat_line = "Some eat meat, while others eat grass."
    filler = "My Lord and Master Himself has saved me completely; I am comforted by meditating on the Lord."
    assert client._english_query_hits("eat meat", meat_line)
    assert client._english_query_hits("flesh", "Do not desire the flesh.")
    assert not client._english_query_hits("eat meat", filler)
    assert not client._english_query_hits("flesh", filler)
    assert not client._english_query_hits("completely", meat_line)


@pytest.mark.asyncio
async def test_scripture_queries_skip_when_gurbani_not_relevant():
    from app.pipeline.gurbani_topics import scripture_queries_for_claim
    from app.pipeline.relevance import ClaimBrief

    brief = ClaimBrief(
        subject="historical origin of the Khalsa",
        gurbani_relevant=False,
        llm_queries=[{"q": "warrior", "lang": "en"}],
        focus_tokens={"khalsa", "british"},
    )
    qs = await scripture_queries_for_claim(
        "The British created the Khalsa in the 19th century.", brief=brief
    )
    assert qs == []


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


def test_live_eval_fixtures_well_formed():
    path = ROOT / "data" / "golden" / "live_eval.json"
    data = json.loads(path.read_text())
    fixtures = data["fixtures"]
    assert 22 <= len(fixtures) <= 40
    ids = [f["id"] for f in fixtures]
    assert len(ids) == len(set(ids))
    for fx in fixtures:
        assert fx["text"]
        assert fx["expected_verdict"]
        assert fx["gurbani_expected"] in {"required", "optional", "forbidden"}
        from app.pipeline.gurbani_topics import scripture_queries_for

        labels = {q.query.lower() for q in scripture_queries_for(fx["text"])}
        assert "completely" not in labels
        assert "forbids" not in labels
