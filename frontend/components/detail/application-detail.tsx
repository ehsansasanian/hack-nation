"use client";

import * as React from "react";
import Link from "next/link";
import {
  AtSign,
  Building2,
  ChevronDown,
  ChevronRight,
  Code2,
  FileText,
  Globe,
  History,
  Link2,
  User,
} from "lucide-react";

import { api } from "@/lib/api";
import type {
  AnalysisStatus,
  ApplicationDetail as ApplicationDetailData,
  DeclaredFounderLinks,
  EnrichmentSource,
  Founder,
  FounderDetail,
  Signal,
  Trace,
} from "@/lib/types";
import { orderedScores } from "@/lib/format";
import { ErrorState, Spinner } from "@/components/async";
import { PageHeader } from "@/components/page-header";
import { buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { OriginBadge } from "@/components/origin-badge";
import { TraceProvider } from "@/components/trace/trace-panel";
import { AxisCard } from "./axis-card";
import { ClaimsTable } from "./claims-table";
import { OutreachDraft } from "./outreach-draft";
import { EnrichmentOutcomes } from "./enrichment-outcomes";
import { AnalysisProgress, ReRunAnalysis, isInFlight } from "./analysis-progress";

const TERMINAL: AnalysisStatus[] = ["ready", "screened_out", "failed"];
const POLL_MS = 2000;
const MAX_POLLS = 90; // ~3 min safety cap so a stalled run never polls forever

/** A founder is "returning" when there's a track record beyond this application:
 *  a prior company, or a founder-score history entry from another application.
 *  Derived purely from GET /founders/{id} - no backend changes. */
export interface ReturningInfo {
  priorCompanies: string[];
  fromOtherApplications: boolean;
  founderScore: number | null;
}

function returningInfo(
  f: FounderDetail,
  currentCompanyId: number,
  currentAppId: number,
): ReturningInfo | null {
  const priorCompanies = f.companies
    .filter((c) => c.id !== currentCompanyId)
    .map((c) => c.name);
  const otherAppIds = new Set(
    f.score_history
      .map((e) => e.application_id)
      .filter((x): x is number => x != null && x !== currentAppId),
  );
  const returning = priorCompanies.length > 0 || otherAppIds.size > 0;
  if (!returning) return null;
  return {
    priorCompanies,
    fromOtherApplications: otherAppIds.size > 0,
    founderScore: f.founder_score,
  };
}

async function loadDetail(id: string) {
  const [app, trace] = await Promise.all([
    api.application(id),
    api.trace(id).catch((): Trace | null => null),
  ]);
  const founders = await Promise.allSettled(app.founders.map((f) => api.founder(f.id)));
  const signalsById = new Map<number, Signal>();
  const returningById = new Map<number, ReturningInfo>();
  for (const r of founders) {
    if (r.status !== "fulfilled") continue;
    const f = r.value;
    for (const s of f.signals) signalsById.set(s.id, s);
    const info = returningInfo(f, app.company.id, app.id);
    if (info) returningById.set(f.id, info);
  }
  return { app, signalsById, trace, returningById };
}

function DeckText({ text }: { text: string }) {
  const [open, setOpen] = React.useState(false);
  return (
    <section className="rounded-xl border border-border bg-card">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-4 py-3 text-sm font-medium"
      >
        {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        <FileText className="size-4 text-muted-foreground" />
        Source deck text
      </button>
      {open && (
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap border-t border-border px-4 py-3 font-sans text-sm leading-relaxed text-foreground/90">
          {text}
        </pre>
      )}
    </section>
  );
}

/** "Returning founder" badge - surfaces a persistent track record ("ship once,
 *  start stronger next time") and links straight to the founder's profile. */
function ReturningFounderBadge({
  founderId,
  info,
}: {
  founderId: number;
  info: ReturningInfo;
}) {
  const detail =
    info.priorCompanies.length > 0
      ? `prior: ${info.priorCompanies.join(", ")}`
      : "prior scoring history on file";
  return (
    <Link
      href={`/founders/${founderId}`}
      title={`Track record found - ${detail}`}
      className="inline-flex items-center gap-1 rounded-md border border-indigo-200 bg-indigo-50 px-1.5 py-0.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100"
    >
      <History className="size-3" />
      Returning founder
      {info.founderScore != null && (
        <span className="tabular-nums">· score {info.founderScore.toFixed(1)}</span>
      )}
      <span className="hidden text-indigo-500 sm:inline">· {detail}</span>
    </Link>
  );
}

// --- Founders section -------------------------------------------------------
// Lists every founder declared on apply. Enrichment only entity-resolves the
// PRIMARY founder onto the company (co-founder enrichment signals carry no
// company hint), so declared_links is the source of truth for "all founders";
// we augment each with the resolved Founder row (score / profile / returning
// badge) when we can match it by github handle or normalised name.

const LINK_ICON: Record<string, typeof Code2> = {
  github: Code2,
  linkedin: Building2,
  website: Globe,
  x: AtSign,
  other: Link2,
};

interface LinkPill {
  key: string;
  label: string;
  href: string;
  source: keyof typeof LINK_ICON;
}

interface FounderCardData {
  key: string;
  name: string;
  role: string | null;
  bio: string | null;
  founderId: number | null;
  founderScore: number | null;
  links: LinkPill[];
  sources: EnrichmentSource[]; // enrichment_report keys this founder declared
}

const normName = (n: string | null | undefined) =>
  (n ?? "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

/** Bare github handle from "octocat" or a full profile URL. */
function ghHandle(value: string | null | undefined): string | null {
  if (!value) return null;
  let v = value.trim();
  if (!v) return null;
  v = v.replace(/^https?:\/\/(www\.)?github\.com\//i, "");
  v = v.replace(/^@/, "").replace(/[/?#].*$/, "");
  return v || null;
}

function ensureUrl(v: string | null | undefined): string | null {
  if (!v) return null;
  const t = v.trim();
  if (!t) return null;
  return /^https?:\/\//i.test(t) ? t : `https://${t}`;
}

/** Split other_links into the role/bio context the apply form folds in (the API
 *  has no dedicated field) and any genuine extra URLs. */
function parseFounderMeta(other: string[] | undefined): {
  role: string | null;
  bio: string | null;
  links: string[];
} {
  let role: string | null = null;
  let bio: string | null = null;
  const links: string[] = [];
  for (const raw of other ?? []) {
    const s = (raw ?? "").trim();
    if (!s) continue;
    const lower = s.toLowerCase();
    if (lower.startsWith("role:")) role = s.slice(s.indexOf(":") + 1).trim() || role;
    else if (lower.startsWith("bio:")) bio = s.slice(s.indexOf(":") + 1).trim() || bio;
    else links.push(s);
  }
  return { role, bio, links };
}

function buildLinks(
  declared: DeclaredFounderLinks | null,
  resolved: Founder | null,
  otherLinks: string[],
): LinkPill[] {
  const pills: LinkPill[] = [];
  const seen = new Set<string>();
  const push = (source: keyof typeof LINK_ICON, label: string, href: string | null) => {
    if (!href) return;
    const k = href.toLowerCase();
    if (seen.has(k)) return;
    seen.add(k);
    pills.push({ key: `${source}:${href}`, label, href, source });
  };
  const rl = resolved?.links ?? {};
  const gh = ghHandle(declared?.github) ?? resolved?.github_handle ?? ghHandle(rl.github);
  if (gh) push("github", "GitHub", `https://github.com/${gh}`);
  push("linkedin", "LinkedIn", ensureUrl(declared?.linkedin ?? rl.linkedin));
  push("website", "Website", ensureUrl(declared?.website ?? rl.website ?? rl.blog));
  push("x", "X", ensureUrl(declared?.x ?? rl.x ?? rl.twitter));
  for (const l of otherLinks) push("other", "Link", ensureUrl(l));
  return pills;
}

function sourcesFromDeclared(d: DeclaredFounderLinks): EnrichmentSource[] {
  const s: EnrichmentSource[] = [];
  if (d.github) s.push("github");
  if (d.website) s.push("web");
  if (d.linkedin) s.push("linkedin");
  if (d.x) s.push("x");
  return s;
}

function sourcesFromResolved(f: Founder): EnrichmentSource[] {
  const rl = f.links ?? {};
  const s: EnrichmentSource[] = [];
  if (f.github_handle || rl.github) s.push("github");
  if (rl.website || rl.blog) s.push("web");
  if (rl.linkedin) s.push("linkedin");
  if (rl.x || rl.twitter) s.push("x");
  return s;
}

function matchResolved(
  declared: DeclaredFounderLinks,
  resolved: Founder[],
): Founder | undefined {
  const gh = ghHandle(declared.github);
  if (gh) {
    const byGh = resolved.find(
      (f) => f.github_handle && f.github_handle.toLowerCase() === gh.toLowerCase(),
    );
    if (byGh) return byGh;
  }
  const nn = normName(declared.name);
  return nn ? resolved.find((f) => normName(f.name) === nn) : undefined;
}

function resolvedOnlyCard(f: Founder): FounderCardData {
  return {
    key: `f${f.id}`,
    name: f.name,
    role: null,
    bio: f.bio ?? null,
    founderId: f.id,
    founderScore: f.founder_score,
    links: buildLinks(null, f, []),
    sources: sourcesFromResolved(f),
  };
}

function buildFounderCards(app: ApplicationDetailData): FounderCardData[] {
  const resolved = app.founders ?? [];
  const declared = app.declared_links ?? [];
  const cards: FounderCardData[] = [];
  const usedIds = new Set<number>();

  if (declared.length > 0) {
    declared.forEach((d, i) => {
      const match = matchResolved(d, resolved);
      if (match) usedIds.add(match.id);
      const meta = parseFounderMeta(d.other_links);
      cards.push({
        key: `d${i}`,
        name: d.name?.trim() || match?.name || `Founder ${i + 1}`,
        role: meta.role,
        bio: meta.bio ?? match?.bio ?? null,
        founderId: match?.id ?? null,
        founderScore: match?.founder_score ?? null,
        links: buildLinks(d, match ?? null, meta.links),
        sources: sourcesFromDeclared(d),
      });
    });
    // Resolved founders with no declared entry (e.g. legacy re-apply) still show.
    for (const f of resolved) if (!usedIds.has(f.id)) cards.push(resolvedOnlyCard(f));
  } else {
    for (const f of resolved) cards.push(resolvedOnlyCard(f));
  }
  return cards;
}

function FounderCard({
  card,
  report,
  returning,
}: {
  card: FounderCardData;
  report: ApplicationDetailData["enrichment_report"];
  returning: ReturningInfo | undefined;
}) {
  return (
    <div className="space-y-2.5 rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5">
          <User className="size-4 text-muted-foreground" />
          {card.founderId != null ? (
            <Link
              href={`/founders/${card.founderId}`}
              className="text-sm font-semibold hover:text-blue-700"
            >
              {card.name}
            </Link>
          ) : (
            <span className="text-sm font-semibold">{card.name}</span>
          )}
        </span>
        {card.role && <Badge variant="muted">{card.role}</Badge>}
        {card.founderScore != null && (
          <span
            title="Persistent founder score"
            className="inline-flex items-center rounded-md border border-border bg-background px-1.5 py-0.5 text-xs tabular-nums text-muted-foreground"
          >
            score {card.founderScore.toFixed(1)}
          </span>
        )}
        {returning && card.founderId != null && (
          <ReturningFounderBadge founderId={card.founderId} info={returning} />
        )}
      </div>

      {card.links.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {card.links.map((l) => {
            const Icon = LINK_ICON[l.source];
            return (
              <a
                key={l.key}
                href={l.href}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-1.5 py-0.5 text-xs font-medium text-muted-foreground hover:border-blue-300 hover:text-blue-700"
              >
                <Icon className="size-3" />
                {l.label}
              </a>
            );
          })}
        </div>
      )}

      {report && card.sources.length > 0 && (
        <EnrichmentOutcomes report={report} sources={card.sources} />
      )}

      {card.bio && (
        <p className="text-xs leading-relaxed text-muted-foreground">{card.bio}</p>
      )}

      {card.links.length === 0 && card.sources.length === 0 && (
        <p className="text-xs text-muted-foreground">
          No links provided - not penalised (cold-start protection).
        </p>
      )}
    </div>
  );
}

function FoundersSection({
  app,
  returningById,
}: {
  app: ApplicationDetailData;
  returningById: Map<number, ReturningInfo>;
}) {
  const cards = React.useMemo(() => buildFounderCards(app), [app]);
  if (cards.length === 0) return null;
  const multi = cards.length > 1;
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-muted-foreground">
        {multi ? `Founding team · ${cards.length} founders` : "Founder"}
        <span className="ml-2 font-normal">
          declared links fetched as evidence; blocked sources kept as references
        </span>
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {cards.map((c) => (
          <FounderCard
            key={c.key}
            card={c}
            report={app.enrichment_report}
            returning={c.founderId != null ? returningById.get(c.founderId) : undefined}
          />
        ))}
      </div>
    </section>
  );
}

export function ApplicationDetail({ id }: { id: string }) {
  const [data, setData] = React.useState<Awaited<
    ReturnType<typeof loadDetail>
  > | null>(null);
  const [error, setError] = React.useState<Error | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false); // an analyze request is in flight
  const [runToken, setRunToken] = React.useState(0); // bump to (re)start polling

  const load = React.useCallback(async (): Promise<AnalysisStatus | undefined> => {
    try {
      const d = await loadDetail(id);
      setData(d);
      setError(null);
      return d.app.analysis_status;
    } catch (e) {
      setError(e as Error);
      return undefined;
    } finally {
      setLoading(false);
    }
  }, [id]);

  React.useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    const tick = async () => {
      if (!alive) return;
      const status = await load();
      attempts += 1;
      const keepPolling =
        status !== undefined &&
        !TERMINAL.includes(status) &&
        attempts < MAX_POLLS;
      if (alive && keepPolling) timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [load, runToken]);

  const onAnalyze = React.useCallback(
    async (force: boolean) => {
      setBusy(true);
      try {
        await api.analyze(id, force);
        // Optimistically reflect the queued state, then (re)start polling.
        setData((prev) =>
          prev
            ? {
                ...prev,
                app: { ...prev.app, analysis_status: "received", analysis_error: null },
              }
            : prev,
        );
      } catch {
        /* a run is already in flight - polling will pick up its real state */
      } finally {
        setBusy(false);
        setRunToken((t) => t + 1);
      }
    },
    [id],
  );

  if (loading && !data)
    return (
      <div className="px-8 py-6">
        <Spinner />
      </div>
    );
  if (error && !data)
    return (
      <div className="px-8 py-6">
        <ErrorState error={error} onRetry={() => setRunToken((t) => t + 1)} />
      </div>
    );
  if (!data) return null;

  const { app, signalsById, trace, returningById } = data;
  const scores = orderedScores(app.scores);
  const coldStart = scores.some((s) => s.cold_start);
  const screened = app.status === "screened_out";
  const analysis = app.analysis_status;
  const showProgress = isInFlight(analysis) || analysis === "failed";
  const c = app.company;

  return (
    <TraceProvider trace={trace}>
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <Link href="/pipeline" className="text-muted-foreground hover:text-foreground">
              Pipeline
            </Link>
            <span className="text-muted-foreground">/</span>
            {c.name}
          </span>
        }
        subtitle={c.one_liner}
        actions={
          <span className="flex items-center gap-2">
            {analysis === "ready" && (
              <ReRunAnalysis busy={busy} onRerun={() => onAnalyze(true)} />
            )}
            {app.status === "memo_ready" && (
              <Link
                href={`/applications/${app.id}/memo`}
                className={buttonVariants({ size: "sm" })}
              >
                <FileText /> View memo
              </Link>
            )}
          </span>
        }
      />
      <div className="space-y-6 px-8 py-6">
        {/* live analysis progress (screening -> scoring -> diligence -> memo) */}
        {showProgress && (
          <AnalysisProgress
            status={analysis}
            error={app.analysis_error}
            busy={busy}
            onAnalyze={onAnalyze}
            enrichmentReport={app.enrichment_report}
          />
        )}

        {/* meta */}
        <div className="flex flex-wrap items-center gap-2">
          <OriginBadge origin={app.origin} />
          {c.sector && <Badge variant="outline">{c.sector}</Badge>}
          {c.stage && <Badge variant="outline">{c.stage}</Badge>}
          {c.geography && <Badge variant="outline">{c.geography}</Badge>}
          {coldStart && (
            <Badge className="border-amber-300 bg-amber-50 text-amber-800">
              cold-start founder
            </Badge>
          )}
        </div>

        {/* founders - all declared founders, links + per-source enrichment outcomes */}
        <FoundersSection app={app} returningById={returningById} />

        {/* screening */}
        {app.screening_rationale && (
          <div
            className={
              screened
                ? "rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900"
                : "rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground"
            }
          >
            <span className="font-medium capitalize">
              {screened ? "Screened out" : `Screening: ${app.screening_verdict}`}
            </span>{" "}
            - {app.screening_rationale}
          </div>
        )}

        {/* axis scores */}
        {scores.length > 0 && (
          <section>
            <h2 className="mb-3 text-sm font-semibold text-muted-foreground">
              Three-axis score
              <span className="ml-2 font-normal">
                independent axes, never averaged
              </span>
            </h2>
            <div className="grid gap-4 md:grid-cols-3">
              {scores.map((s) => (
                <AxisCard key={s.axis} score={s} signalsById={signalsById} />
              ))}
            </div>
          </section>
        )}

        {/* outbound outreach */}
        {app.origin === "outbound" && app.outreach_draft && (
          <OutreachDraft text={app.outreach_draft} />
        )}

        {/* claims - only once diligence has produced (or cleared) them */}
        {(app.claims.length > 0 || analysis === "ready") && (
          <section>
            <h2 className="mb-3 text-sm font-semibold text-muted-foreground">
              Diligence claims &amp; trust
            </h2>
            <ClaimsTable claims={app.claims} />
          </section>
        )}

        {app.deck_text && <DeckText text={app.deck_text} />}
      </div>
    </TraceProvider>
  );
}
