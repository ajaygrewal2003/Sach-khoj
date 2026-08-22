# Sach Khoj (ਸੱਚ ਖੋਜ)

Evidence-grounded validation tool for claims about **Sikhism and Gurbani**. Paste a URL, caption text, or screenshot — the pipeline extracts claims, retrieves passages from BaniDB / GurbaniNow and a curated corpus, then returns verdicts with citations.

> **Disclaimer:** AI-assisted research tool, not Panthic authority. Consult a Giani / Sangat for religious guidance.

## Features (MVP)

- Submit URL + text + screenshot/video frame
- Website article extraction (trafilatura)
- Facebook/Instagram-aware fallback (paste text / OCR when Meta blocks fetch)
- Claim extraction (LLM when `OPENAI_API_KEY` is set; heuristic fallback otherwise)
- Gurbani retrieval via [BaniDB](https://www.banidb.com/) and [GurbaniNow](https://api.gurbaninow.com/)
- Curated Rehat Maryada / history / known-false index (RAG-style hybrid search)
- Per-claim verdicts: `false | misleading | unverified | true | not_checkable`
- Shareable case report pages
- Admin human-review queue for low-confidence results

## Quick start (local)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite+aiosqlite:///./sachkhoj.db
export CURATED_DATA_DIR=../data/curated
export UPLOAD_DIR=./uploads
export ADMIN_TOKEN=dev-admin-token
# optional:
# export OPENAI_API_KEY=sk-...
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
export NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000

### Docker Compose

```bash
cp .env.example .env   # add OPENAI_API_KEY if desired
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000/docs

## API sketch

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Health + whether LLM is enabled |
| POST | `/api/submit` | multipart form: `url`, `text`, `language_hint`, `media` |
| GET | `/api/cases/{id}` | Case report + claims |
| GET | `/api/review/queue` | Admin review queue (`Authorization: Bearer <ADMIN_TOKEN>`) |
| POST | `/api/review/{id}` | approve / override / dismiss |
| POST | `/api/review/known-false` | add known-false pattern |

## Pipeline

1. **Ingest** — URL fetch / text / OCR  
2. **Claims** — atomic checkable claims  
3. **Retrieve** — BaniDB, GurbaniNow, curated JSON corpus, known-false index  
4. **Verify** — structured verdict; citations must match retrieved evidence IDs  

Low confidence (`< 0.7`) or `unverified` → human review queue.

## Project layout

```
backend/app/          FastAPI app, pipeline, integrations
frontend/             Next.js UI
data/curated/         Rehat, history, Gurbani notes, known-false seed
data/golden/          Golden evaluation examples
docker-compose.yml
```

## Tests

```bash
cd backend
pip install -r requirements.txt
pytest -q
```

## Ethical notes

- Prefer user-submitted content over social scraping
- Frame outputs as claim assessments, not personal accusations
- Expand the golden set with scholars / gurdwara media teams before treating results as production-grade
