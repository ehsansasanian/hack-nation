// TypeScript mirror of the backend Pydantic response models (backend/app/schemas.py).
// Kept intentionally close to the API contract so the client stays a thin, typed seam.

export type Axis = "founder" | "market" | "idea_vs_market";
export type Trend = "improving" | "declining" | "stable";
export type TrustLevel = "verified" | "consistent" | "unverified" | "contradicted";
export type Origin = "inbound" | "outbound";
export type Status = "screened_out" | "in_review" | "memo_ready";
export type AnalysisStatus =
  | "received"
  | "enriching"
  | "screening"
  | "scoring"
  | "scored" // scored at scan/batch time; at rest, diligence + memo pending
  | "diligence"
  | "memo"
  | "ready"
  | "screened_out"
  | "failed";

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
  analysis_status: AnalysisStatus;
  analysis_error: string | null;
  origin: Origin;
  screening_verdict: string | null;
  screening_rationale: string | null;
  outreach_draft: string | null;
  // Inbound enrichment: per-source fetch report set by the `enriching` stage.
  // null until enrichment runs. See EnrichmentReport below.
  enrichment_report: EnrichmentReport | null;
  created_at: string;
  company: Company;
  scores: Score[];
}

export interface AnalyzeResult {
  application_id: number;
  analysis_status: AnalysisStatus;
  scheduled: boolean;
  detail: string;
}

export interface ApplicationDetail extends Application {
  deck_text: string | null;
  claims: Claim[];
  founders: Founder[];
  // Self-declared per-founder links captured on apply (all founders, whether or
  // not entity resolution linked them to the company). null for legacy apps.
  declared_links: DeclaredFounderLinks[] | null;
  // Server-computed qualitative "why is this alpha" read. null for legacy apps.
  edge: Edge | null;
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

// Phase 8 customizable fund guidelines + investor-vocabulary mandate constraints.
// All optional; each gates or informs screening/scoring and shows in the memo.
export interface MandateExtras {
  investment_principles: string | null;
  axis_notes: Record<string, string> | null; // {founder/market/idea_vs_market: note}
  valuation_cap: string | null;
  instrument: string | null;
  business_model: string | null;
  min_arr_usd: number | null;
  min_growth_rate: string | null;
  require_technical_founder: boolean | null;
  exclusions: string[] | null;
}

export interface Thesis extends Partial<MandateExtras> {
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
  // Phase 8 (all optional on the form).
  investment_principles?: string | null;
  axis_notes?: Record<string, string>;
  valuation_cap?: string | null;
  instrument?: string | null;
  business_model?: string | null;
  min_arr_usd?: number | null;
  min_growth_rate?: string | null;
  require_technical_founder?: boolean;
  exclusions?: string[];
}

// --- Co-founder & idea recombination (Phase 8) ----------------------------

/** One complementary founder proposed from Memory. HYPOTHETICAL - proposing a
 *  recombination never changes the application's real axis scores. */
export interface RecombinationCandidate {
  founder_id: number;
  name: string;
  sector: string | null;
  founder_score: number | null;
  technical: boolean;
  commercial: boolean;
  fills: string[]; // gaps closed: "technical" | "commercial" | "domain"
  availability: string; // why they are recombinable (not tied to an active in-thesis deal)
  why: string; // complementarity rationale
  match_score: number;
}

export interface WeakAxis {
  axis: string;
  value: number;
  note: string;
}

/** A hypothetical recombination note for a low-scoring application: complementary
 *  co-founder proposals + idea pivots + a contingent IC note. */
export interface Recombination {
  application_id: number;
  company: string;
  standing: string; // the current, real standing (unchanged by this note)
  weak_axes: WeakAxis[];
  gaps: string[];
  candidates: RecombinationCandidate[];
  idea_pivots: string[];
  contingent_note: string;
  reeval_weeks: number;
  backend: string;
}

// --- Founders directory + team matching (Phase 8 Database tab) ------------

/** One row in the founders directory. Classification/availability come from the
 *  same complementarity engine the scoring backend and memo use. */
export interface DirectoryFounder {
  id: number;
  name: string;
  github_handle: string | null;
  founder_score: number | null;
  technical: boolean;
  commercial: boolean;
  classification: string; // technical | commercial | technical + commercial | unclassified
  domain: string | null; // sectors the founder has worked in
  available: boolean; // not tied to an active in-thesis application
  availability: string; // human-readable reason
  returning: boolean; // track record across more than one company
}

/** Compact per-founder view inside a match result. */
export interface MatchFounder {
  id: number;
  name: string;
  github_handle: string | null;
  founder_score: number | null;
  technical: boolean;
  commercial: boolean;
  classification: string;
  domain: string | null;
  available: boolean;
  availability: string;
}

/** A HYPOTHETICAL team read on a pairing - never changes a real score. */
export interface FounderMatch {
  founder_a: MatchFounder;
  founder_b: MatchFounder;
  sector: string | null;
  solo: boolean;
  technical: boolean;
  commercial: boolean;
  complementary: boolean;
  domain_gap: boolean;
  prior_collab: boolean;
  verdict: string;
  lift: number;
  gaps: string[];
  patterns: string;
  rationale: string;
  hypothetical_team: string;
}

/** Ranked complementary, available founders for one founder ("find matches"). */
export interface FounderMatches {
  founder: MatchFounder;
  needs: string[]; // coverage the founder is missing: technical / commercial
  candidates: RecombinationCandidate[];
}

// --- Edge panel (Phase 8) - qualitative "why is this alpha" ----------------

export interface EdgeLine {
  key: string; // cold_start | outbound | momentum | recency
  label: string;
  detail: string;
  evidence: string; // the flag / field / signal this line is derived from
}

/** Server-computed, strictly-qualitative edge read (no return numbers). */
export interface Edge {
  summary: string; // honest lead; "" when no edge is derivable
  has_edge: boolean;
  lines: EdgeLine[];
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

// --- Inbound enrichment & co-founder profiles (Phase 8) -------------------

/** Sources the `enriching` stage attempts, as keyed in the enrichment_report. */
export type EnrichmentSource = "github" | "web" | "linkedin" | "x";
export type FetchOutcome = "fetched" | "blocked" | "error";

export interface EnrichmentOutcome {
  outcome: FetchOutcome;
  signal_count: number;
  note?: string;
}

/** Per-source fetch report on Application.enrichment_report. Externally fetched
 *  sources (github/web) become evidence; auth-walled ones (linkedin/x) are
 *  recorded honestly as blocked self-declared references, never fabricated. */
export type EnrichmentReport = Partial<Record<EnrichmentSource, EnrichmentOutcome>>;

/** One founder's self-declared links from the apply form (as returned on the
 *  detail response). `github` is a bare handle or a full URL. `other_links` may
 *  carry `role: ...` / `bio: ...` context strings the form folds in (see the
 *  apply page - the API has no dedicated role/bio field). */
export interface DeclaredFounderLinks {
  name: string | null;
  github: string | null;
  linkedin: string | null;
  website: string | null;
  x: string | null;
  other_links: string[];
}

/** One founder entry submitted on POST /applications (`founders[]`). All links
 *  optional; a missing link never penalises a founder (cold-start protection). */
export interface FounderLinkInput {
  name?: string;
  github?: string;
  linkedin?: string;
  website?: string;
  x?: string;
  other_links?: string[];
}
