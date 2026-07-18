# The VC Brain

An AI-first VC operating system that runs the top of the venture funnel end to end: **sourcing → screening → diligence → decision**. It ingests heterogeneous founder and company signals (pitch decks, GitHub, launches, social, analyst notes) into a deduplicated, source-tagged, timestamped memory layer with a persistent Founder Score; scores each company on three independent axes (Founder, Market, Idea-vs-Market) through a configurable investment thesis; runs per-claim trust checks that surface contradictions and explicitly flag missing data; and produces an investment memo with a recommendation. This repository implements the memory layer and API contract (Phases 0-1), the reasoning layer (Phase 2: thesis fit, fast screening, 3 independent axis scores with per-axis evidence, an explicit cold-start path, and persistent Founder Score updates), outbound sourcing (Phase 3: live GitHub, Hacker News, and arXiv scanners that feed the same funnel and draft outreach for above-threshold candidates), diligence + memo (Phase 4: claim extraction, a per-claim Trust Score that surfaces seeded contradictions, a validator self-correction pass, memo generation, and natural-language pipeline search); and the experience layer (Phase 5: a Next.js investor dashboard over the same API - ranked 3-axis pipeline with NL search, application detail with per-axis evidence, investment memo, thesis editor, founder profile with score-history chart, inbound apply, and live outbound sourcing).

Every reasoning layer (scoring and diligence) sits behind a **dual backend seam**: an OpenAI structured-output path and a deterministic, network-free offline path implementing the identical contract, with automatic fallback and provenance stamped on every output - so the whole system runs (and the demo rehearses) with the network off, and one re-run upgrades everything to live LLM output with no code change.

## Architecture

- **Backend** (`backend/`) - FastAPI + SQLAlchemy over SQLite. Every signal, regardless of source, enters through one ingestion pipeline that normalizes → deduplicates → resolves entities (founder/company) → persists with both event time and ingestion time.
- **Frontend** (`frontend/`) - Next.js 16 (App Router, TypeScript, Tailwind v4, shadcn/ui). A thin typed API client (`lib/api.ts`) calls the backend directly; every view has explicit loading / error states (including a clear "backend not running" hint).
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
| `GITHUB_TOKEN`   | Raises the GitHub API rate limit (60 -> 5000 req/h) for sourcing - Phase 3. If unset, the logged-in `gh` CLI token is used at runtime |
| `VC_BRAIN_LLM`   | Reasoning backend: `openai` (default when a key is present), `offline` (deterministic, no network), or `auto` |

Neither key is required for Phase 0-1 (memory layer + API). Scoring works with the network off via `VC_BRAIN_LLM=offline` (used for the offline demo rehearsal); the OpenAI path falls back to the offline backend if a live call fails.

## Run the backend

```bash
cd backend
uv sync                                   # install dependencies
uv run python -m app.ingestion.load_synthetic   # seed the SQLite DB (idempotent)
uv run python -m app.reasoning.score_all        # seed thesis + run 3-axis scoring (add --backend offline for no network)
uv run python -m app.reasoning.diligence_all    # run diligence + memo on every scored app (add --backend offline)
uv run uvicorn app.main:app --reload      # serve on http://127.0.0.1:8000
```

API docs are at `http://127.0.0.1:8000/docs`. Key endpoints:

- `GET /pipeline` - ranked list of applications with the 3 axis scores per row (filter by `status`, `origin`)
- `POST /applications` - inbound apply (company name + deck text)
- `POST /applications/{id}/score` - run thesis filter -> screening -> 3-axis scoring (`?force=true` to override a screen-out, `?backend=offline|openai` to pin a backend)
- `POST /applications/{id}/diligence` - claim extraction -> per-claim truth-gap -> validator (idempotent; `?backend=offline|openai`)
- `POST /applications/{id}/memo` - generate the investment memo (runs diligence first if needed); `GET` fetches it
- `POST /query` - natural-language pipeline search (see below)
- `GET /applications/{id}` - application detail (scores, claims, deck, founders)
- `GET /founders/{id}` - founder profile with persistent score history
- `GET /thesis`, `PUT /thesis` - investment thesis configuration
- `POST /sourcing/scan` - run the live outbound scanners (see below)

## Outbound sourcing (Phase 3)

`POST /sourcing/scan` runs live scanners and feeds finds into the **same** ingestion pipeline (dedup + entity resolution) and the **same** Phase 2 scoring as inbound applications:

- **GitHub** - recently-created AI/infra repos ranked by star velocity; enriched with owner profile, commit cadence, and README quality.
- **Hacker News** - Show HN launches ranked by points velocity; author + linked domain extracted (Algolia API, no key).
- **arXiv** - recent cs.AI papers attached to the lead author (opt-in; enriches the founder graph, creates no applications).

In-thesis candidates above the score threshold become `Application(origin="outbound")` with a personalized **draft** outreach message (nothing is ever sent). The scan is safe to re-run: unchanged content dedups to zero new signals.

```bash
# defaults: sources=["github","hn"], limit=10
curl -X POST http://127.0.0.1:8000/sourcing/scan \
  -H 'Content-Type: application/json' \
  -d '{"sources":["github","hn","arxiv"],"limit":8}'

# outbound candidates then appear in the pipeline alongside inbound
curl 'http://127.0.0.1:8000/pipeline?origin=outbound'
```

## Diligence, Trust Score & memo (Phase 4)

Diligence extracts discrete **claims** (traction / revenue / team / market) from the deck and from self-asserted public posts, then runs a **per-claim truth-gap** against stored signals - labelling each `verified` (external evidence supports), `consistent` (nothing contradicts), `unverified` (no evidence either way), or `contradicted` (a signal conflicts, with a note naming both sources). A **validator** self-correction pass then refutes each axis rationale and downgrades over-optimistic claims. The **memo** renders every claim at its trust level, flags missing data explicitly (`Cap table: not disclosed`), and ends with a recommendation (`invest $100K` / `pass` / `need-more-info`) tied to the three axis scores (never averaged) and thesis fit.

```bash
# diligence a single application (e.g. the seeded-contradiction demo)
curl -X POST 'http://127.0.0.1:8000/applications/2/diligence?backend=offline'   # Ledgerly: $50k MRR vs pre-revenue

# generate + fetch its memo
curl -X POST 'http://127.0.0.1:8000/applications/2/memo?backend=offline'
curl 'http://127.0.0.1:8000/applications/2/memo'

# natural-language pipeline search: parse -> filter -> rerank with per-result rationale
curl -X POST http://127.0.0.1:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"q":"technical founder, Berlin, AI infra, no prior VC backing","backend":"offline"}'
```

## Run the frontend

Start the backend first (above), then:

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

The client reads the backend base URL from `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). To point at a different host, set it before starting:

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
```

The backend already enables CORS for `http://localhost:3000` (see `backend/app/main.py`); if you serve the frontend from another origin, add it there.

`npm run build` produces the production build (type-checked). Pages:

| Route                       | View                                                                 |
| --------------------------- | -------------------------------------------------------------------- |
| `/`                         | Pipeline dashboard - ranked table, 3 axis chips per row, trust summary, origin, thesis-fit; NL query bar on top |
| `/applications/[id]`        | Application detail - 3 axis cards (score, trend, confidence, rationale, evidence), claims with trust badges, cold-start flag, outbound outreach draft |
| `/applications/[id]/memo`   | Investment memo - recommendation banner, sections, inline trust badges, explicit "not disclosed" gap callouts |
| `/thesis`                   | Thesis editor (GET/PUT `/thesis`); saving returns to the pipeline (re-run scoring to re-rank) |
| `/founders/[id]`            | Founder profile - persistent score-history chart, signal timeline grouped by source |
| `/apply`                    | Inbound apply (company + deck text or `.txt`/`.md` upload) → lands on the new application |
| `/sourcing`                 | Live outbound scan (github / hn / arxiv + limit) → summary + candidate outbound apps |
