"use client";

import * as React from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight, FileText, User } from "lucide-react";

import { api } from "@/lib/api";
import type { AnalysisStatus, Signal, Trace } from "@/lib/types";
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
import { AnalysisProgress, ReRunAnalysis, isInFlight } from "./analysis-progress";

const TERMINAL: AnalysisStatus[] = ["ready", "screened_out", "failed"];
const POLL_MS = 2000;
const MAX_POLLS = 90; // ~3 min safety cap so a stalled run never polls forever

async function loadDetail(id: string) {
  const [app, trace] = await Promise.all([
    api.application(id),
    api.trace(id).catch((): Trace | null => null),
  ]);
  const founders = await Promise.allSettled(app.founders.map((f) => api.founder(f.id)));
  const signalsById = new Map<number, Signal>();
  for (const r of founders) {
    if (r.status === "fulfilled")
      for (const s of r.value.signals) signalsById.set(s.id, s);
  }
  return { app, signalsById, trace };
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

  const { app, signalsById, trace } = data;
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
            <Link href="/" className="text-muted-foreground hover:text-foreground">
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
          {app.founders.map((f) => (
            <Link
              key={f.id}
              href={`/founders/${f.id}`}
              className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-1.5 py-0.5 text-xs font-medium hover:border-blue-300 hover:text-blue-700"
            >
              <User className="size-3" />
              {f.name}
              {f.founder_score != null && (
                <span className="tabular-nums text-muted-foreground">
                  {f.founder_score.toFixed(1)}
                </span>
              )}
            </Link>
          ))}
        </div>

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
