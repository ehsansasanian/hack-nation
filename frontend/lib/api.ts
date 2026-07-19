// Central typed API client for The VC Brain backend.
// Base URL is configurable via NEXT_PUBLIC_API_URL (default http://localhost:8000).

import type {
  AnalyzeResult,
  Application,
  ApplicationDetail,
  DirectoryFounder,
  FounderDetail,
  FounderLinkInput,
  FounderMatch,
  FounderMatches,
  Memo,
  QueryResponse,
  Recombination,
  ScanRequest,
  ScanSummary,
  Thesis,
  ThesisUpdate,
  Trace,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  /** True when the request never reached the server (backend likely down). */
  offline: boolean;

  constructor(message: string, status: number, offline = false) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.offline = offline;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      `Cannot reach the backend at ${API_BASE}. Is it running? (cd backend && uv run uvicorn app.main:app --port 8000)`,
      0,
      true,
    );
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail || `Request failed (${res.status})`, res.status);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  // Pipeline & applications
  pipeline: (params?: { status?: string; origin?: string }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.origin) qs.set("origin", params.origin);
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<Application[]>(`/pipeline${suffix}`);
  },
  application: (id: number | string) =>
    request<ApplicationDetail>(`/applications/${id}`),
  memo: (id: number | string) => request<Memo>(`/applications/${id}/memo`),
  trace: (id: number | string) => request<Trace>(`/applications/${id}/trace`),
  createApplication: (payload: {
    company_name: string;
    deck_text?: string;
    founder_name?: string;
    sector?: string;
    stage?: string;
    geography?: string;
    one_liner?: string;
    // Optional per-founder self-declared links; the `enriching` stage fetches
    // each before screening. First entry is treated as the primary founder.
    founders?: FounderLinkInput[];
  }) =>
    request<Application>("/applications", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  analyze: (id: number | string, force = false) =>
    request<AnalyzeResult>(
      `/applications/${id}/analyze${force ? "?force=true" : ""}`,
      { method: "POST" },
    ),

  // Co-founder & idea recombination (hypothetical; never changes real scores).
  // `recombination` fetches a stored note (404 if none); `recombine` generates it.
  // The chips use the deterministic offline backend; omit `backend` for the
  // default (live narrative with offline fallback).
  recombination: (id: number | string) =>
    request<Recombination>(`/applications/${id}/recombination`),
  recombine: (id: number | string, backend?: "openai" | "offline") =>
    request<Recombination>(
      `/applications/${id}/recombine${backend ? `?backend=${backend}` : ""}`,
      { method: "POST" },
    ),

  // Founders
  founder: (id: number | string) => request<FounderDetail>(`/founders/${id}`),
  // Database tab: directory + team matching (deterministic, $0 LLM).
  founders: () => request<DirectoryFounder[]>("/founders"),
  matchFounders: (founderA: number, founderB: number) =>
    request<FounderMatch>("/founders/match", {
      method: "POST",
      body: JSON.stringify({ founder_a: founderA, founder_b: founderB }),
    }),
  founderMatches: (id: number | string) =>
    request<FounderMatches>(`/founders/${id}/matches`),

  // Thesis
  thesis: () => request<Thesis>("/thesis"),
  updateThesis: (payload: ThesisUpdate) =>
    request<Thesis>("/thesis", { method: "PUT", body: JSON.stringify(payload) }),

  // NL query. `backend` pins the parser: omit for the default (live LLM with
  // offline fallback); pass "offline" for the deterministic parser - used by the
  // ready-to-use chips, whose queries are already structured so they need no LLM.
  query: (q: string, backend?: "openai" | "offline") =>
    request<QueryResponse>("/query", {
      method: "POST",
      body: JSON.stringify(backend ? { q, backend } : { q }),
    }),

  // Sourcing
  scan: (payload: ScanRequest) =>
    request<ScanSummary>("/sourcing/scan", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
