# The VC Brain

An AI-first VC operating system that runs the top of the venture funnel end to end: **sourcing → screening → diligence → decision**. It ingests heterogeneous founder and company signals (pitch decks, GitHub, launches, social, analyst notes) into a deduplicated, source-tagged, timestamped memory layer with a persistent Founder Score; scores each company on three independent axes (Founder, Market, Idea-vs-Market) through a configurable investment thesis; runs per-claim trust checks that surface contradictions and explicitly flag missing data; and produces an investment memo with a recommendation. This repository implements the memory layer and API contract (Phases 0-1) and the reasoning layer (Phase 2: thesis fit, fast screening, 3 independent axis scores with per-axis evidence, an explicit cold-start path, and persistent Founder Score updates); sourcing, diligence, and UI layers are stubbed against the same schema.

## Architecture

- **Backend** (`backend/`) - FastAPI + SQLAlchemy over SQLite. Every signal, regardless of source, enters through one ingestion pipeline that normalizes → deduplicates → resolves entities (founder/company) → persists with both event time and ingestion time.
- **Frontend** (`frontend/`) - Next.js (App Router, TypeScript, Tailwind, shadcn/ui).
- **Data** (`backend/data/`) - committed, deterministic synthetic profiles (`synthetic/`) and pitch decks (`decks/`). Nothing is generated at runtime.

## Prerequisites

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 18+ and npm

## Environment variables

Copy the example and fill in as needed (the runtime environment may already export these):

```bash
cp backend/.env.example backend/.env
```

| Variable         | Used for                                             |
| ---------------- | ---------------------------------------------------- |
| `OPENAI_API_KEY` | LLM reasoning (screening, scoring, memo) - Phase 2+  |
| `GITHUB_TOKEN`   | Raises the GitHub API rate limit for sourcing - Phase 3 |
| `VC_BRAIN_LLM`   | Reasoning backend: `openai` (default when a key is present), `offline` (deterministic, no network), or `auto` |

Neither key is required for Phase 0-1 (memory layer + API). Scoring works with the network off via `VC_BRAIN_LLM=offline` (used for the offline demo rehearsal); the OpenAI path falls back to the offline backend if a live call fails.

## Run the backend

```bash
cd backend
uv sync                                   # install dependencies
uv run python -m app.ingestion.load_synthetic   # seed the SQLite DB (idempotent)
uv run python -m app.reasoning.score_all        # seed thesis + run 3-axis scoring (add --backend offline for no network)
uv run uvicorn app.main:app --reload      # serve on http://127.0.0.1:8000
```

API docs are at `http://127.0.0.1:8000/docs`. Key endpoints:

- `GET /pipeline` - ranked list of applications with the 3 axis scores per row (filter by `status`, `origin`)
- `POST /applications` - inbound apply (company name + deck text)
- `POST /applications/{id}/score` - run thesis filter -> screening -> 3-axis scoring (`?force=true` to override a screen-out, `?backend=offline|openai` to pin a backend)
- `GET /applications/{id}` - application detail (scores, claims, deck, founders)
- `GET /founders/{id}` - founder profile with persistent score history
- `GET /thesis`, `PUT /thesis` - investment thesis configuration
- `POST /query`, `GET /applications/{id}/memo`, `POST /sourcing/scan` - stubbed (later phases, return 501)

## Run the frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```
