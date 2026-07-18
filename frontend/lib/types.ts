// TypeScript mirror of the backend Pydantic response models (backend/app/schemas.py).
// Kept intentionally close to the API contract so the client stays a thin, typed seam.

export type Axis = "founder" | "market" | "idea_vs_market";
export type Trend = "improving" | "declining" | "stable";
export type TrustLevel = "verified" | "consistent" | "unverified" | "contradicted";
export type Origin = "inbound" | "outbound";
export type Status = "screened_out" | "in_review" | "memo_ready";

export interface Company {
  id: number;
  name: string;
  sector: string | null;
  stage: string | null;
  geography: string | null;
  one_liner: string | null;
}

export interface Score {
  axis: Axis;
  value: number;
  trend: Trend | null;
  rationale: string | null;
  evidence_signal_ids: number[];
  confidence: number | null;
  cold_start: boolean;
  score_low: number | null;
  score_high: number | null;
  model: string | null;
  validator_note: string | null;
}

export interface Claim {
  id: number;
  text: string;
  category: string | null;
  source: string | null;
  trust_level: TrustLevel | null;
  evidence_signal_ids: number[];
  contradiction_note: string | null;
  validator_note: string | null;
}

export interface Founder {
  id: number;
  name: string;
  github_handle: string | null;
  links: Record<string, string>;
  bio: string | null;
  founder_score: number | null;
  score_history: ScoreHistoryEntry[];
}

export interface ScoreHistoryEntry {
  timestamp: string;
  score: number;
  note?: string;
  evidence_score?: number;
  confidence?: number;
  cold_start?: boolean;
  application_id?: number;
}

export interface Signal {
  id: number;
  source: string;
  content: Record<string, unknown>;
  timestamp: string;
  ingested_at: string;
  last_seen: string;
}

export interface Application {
  id: number;
  status: Status;
  origin: Origin;
  screening_verdict: string | null;
  screening_rationale: string | null;
  outreach_draft: string | null;
  created_at: string;
  company: Company;
  scores: Score[];
}

export interface ApplicationDetail extends Application {
  deck_text: string | null;
  claims: Claim[];
  founders: Founder[];
}

export interface FounderDetail extends Founder {
  companies: Company[];
  signals: Signal[];
}

export interface Memo {
  application_id: number;
  sections: Record<string, string>;
  recommendation: string | null;
  generated_at: string;
}

export interface Thesis {
  id: number;
  name: string;
  sectors: string[];
  stages: string[];
  geographies: string[];
  check_size: string | null;
  ownership_target: string | null;
  risk_appetite: string | null;
  active: boolean;
}

export interface ThesisUpdate {
  name: string;
  sectors: string[];
  stages: string[];
  geographies: string[];
  check_size: string | null;
  ownership_target: string | null;
  risk_appetite: string | null;
  active: boolean;
}

// --- Trace (Phase 6 agentic traceability) ---------------------------------

export interface TraceSignal {
  id: number;
  source: string;
  timestamp: string;
  ingested_at: string;
  excerpt: string;
  content: Record<string, unknown>;
}

export interface TraceStepDetail {
  // score steps
  axis?: string;
  value?: number;
  score_low?: number | null;
  score_high?: number | null;
  cold_start?: boolean;
  confidence?: number | null;
  trend?: Trend | null;
  model?: string | null;
  validator_note?: string | null;
  // claim steps
  claim_id?: number;
  category?: string | null;
  claim_source?: string | null;
  trust_level?: TrustLevel | null;
  contradiction_note?: string | null;
  influenced_recommendation?: boolean;
  // shared
  memo_section?: string | null;
  // memo step
  sections?: string[];
  core_contradiction?: boolean;
  // signals step
  by_source?: Record<string, number>;
}

export type TraceStepKind = "signals" | "screening" | "score" | "claim" | "memo";

export interface TraceStep {
  index: number;
  kind: TraceStepKind;
  title: string;
  ref: string | null;
  status: string | null;
  summary: string;
  signal_ids: number[];
  source_signal_id: number | null;
  detail: TraceStepDetail;
}

export interface Trace {
  application_id: number;
  company: Company;
  backend: string | null;
  memo_recommendation: string | null;
  signals: TraceSignal[];
  steps: TraceStep[];
}

// --- NL query -------------------------------------------------------------

export interface QueryMatch {
  application_id: number;
  company: string;
  sector: string | null;
  geography: string | null;
  stage: string | null;
  scores: Record<string, number>;
  match_score: number;
  partial: boolean;
  rationale: string;
}

export interface QueryResponse {
  query: string;
  backend: string;
  parsed: {
    sector: string;
    geography: string;
    stage: string;
    attributes: string[];
  };
  results: QueryMatch[];
}

// --- Sourcing scan --------------------------------------------------------

export interface ScanCandidate {
  source: string;
  handle: string;
  company: string;
  why_flagged: string;
  status: string;
  application_id: number | null;
  best_axis: string | null;
  best_score: number | null;
  scores: Record<string, number>;
  outreach_drafted: boolean;
}

export interface ScanSummary {
  sources_requested: string[];
  source_errors: Record<string, string>;
  signals_fetched: number;
  signals_created: number;
  signals_duplicate: number;
  founders_created: number;
  companies_created: number;
  applications_created: number;
  outbound_in_review: number;
  outbound_screened_out: number;
  outreach_drafts: number;
  candidates: ScanCandidate[];
}

export interface ScanRequest {
  sources: string[];
  limit: number;
}
