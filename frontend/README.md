# The VC Brain - frontend

Next.js 16 (App Router, TypeScript, Tailwind v4, shadcn/ui) investor dashboard over the FastAPI backend. See the [root README](../README.md) for architecture, how-to-run, and the demo walkthrough.

```bash
npm install
npm run dev        # http://localhost:3000 (expects the backend on http://localhost:8000)
npm run build      # type-checked production build
```

The backend base URL is configurable via `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

Routes: `/` pipeline · `/applications/[id]` detail · `/applications/[id]/memo` memo · `/thesis` · `/founders/[id]` · `/apply` · `/sourcing`. A "Why?" trace panel (`components/trace/`) is available on every axis score and claim.

> Note: this repo pins a pre-release Next.js. See `AGENTS.md` before editing.
