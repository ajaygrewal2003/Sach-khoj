# Sach Khoj (ਸੱਚ ਖੋਜ)

Evidence-grounded validation tool for claims about **Sikhism and Gurbani**. Paste a link to a reel/video/post, caption text, or upload a video/screenshot — the pipeline transcribes and reads the media, extracts claims, retrieves passages from BaniDB / GurbaniNow and a curated corpus, then returns verdicts with citations.

> **Disclaimer:** AI-assisted research tool, not Panthic authority. Consult a Giani / Sangat for religious guidance.

## Features (MVP)

- Submit a **link to a reel/video/post** (Instagram, Facebook, TikTok, YouTube, X) — the pipeline downloads the media, transcribes the speech (Whisper), and reads on-screen text/visuals (vision model), then fact-checks everything said and shown
- Upload a **video or screenshot** directly (guaranteed path when a platform blocks link access)
- Website article extraction (trafilatura)
- Claim extraction (LLM when `OPENAI_API_KEY` is set; heuristic fallback otherwise)
- Gurbani retrieval via [BaniDB](https://www.banidb.com/) and [GurbaniNow](https://api.gurbaninow.com/)
- Curated Rehat Maryada / history / known-false index (semantic + hybrid search)
- Per-claim verdicts: `false | misleading | unverified | true | not_checkable`
- Shareable case report pages
- Admin human-review queue for low-confidence results

### Social media links: what to expect

Downloads use yt-dlp with an Open Graph fallback, and every file is validated before analysis. Platforms rate-limit datacenter IPs aggressively; two levers make links reliable:

1. **`SOCIAL_COOKIES_FILE`** — path to a Netscape-format cookies file exported from a logged-in browser session (see yt-dlp's FAQ). This makes Instagram/Facebook/YouTube links work consistently.
2. **Upload fallback** — if a link is refused, the report tells the user to save/screen-record the post and upload the file; the analysis (transcript + visuals + verdicts) is identical.

Requires `ffmpeg` on the host (`apt install ffmpeg`; included in the Docker image).

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

Live evaluation (BaniDB + OpenAI; scores quote relevance, not just verdicts):

```bash
cd backend
unset OPENAI_API_KEY && set -a && source .env && set +a
python scripts/eval_live.py --http-smoke
```

Fixtures live in `data/golden/live_eval.json`. A run writes `backend/.eval/last_run.json`.


## Ethical notes

- Prefer user-submitted content over social scraping
- Frame outputs as claim assessments, not personal accusations
- Expand the golden set with scholars / gurdwara media teams before treating results as production-grade
