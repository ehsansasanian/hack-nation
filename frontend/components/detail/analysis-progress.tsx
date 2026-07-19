"use client";

import * as React from "react";
import { Check, Loader2, Play, RefreshCw, TriangleAlert } from "lucide-react";

import type { AnalysisStatus, EnrichmentReport } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { EnrichmentOutcomes, hasEnrichment } from "./enrichment-outcomes";

const STAGES: { key: AnalysisStatus; label: string }[] = [
  { key: "enriching", label: "Enriching" },
  { key: "screening", label: "Screening" },
  { key: "scoring", label: "Scoring" },
  { key: "diligence", label: "Diligence" },
  { key: "memo", label: "Memo" },
];

// Which stage index is currently active for a given status (-1 = queued, nothing
// active yet). Enrichment fetches self-declared links BEFORE screening; screening
// + scoring are one backend call surfaced as two beats.
const ACTIVE_INDEX: Record<string, number> = {
  received: -1,
  enriching: 0,
  screening: 1,
  scoring: 2,
  diligence: 3,
  memo: 4,
};

/** True while analysis is running (a stepper should be shown and polling active). */
export function isInFlight(status: AnalysisStatus): boolean {
  return status in ACTIVE_INDEX; // received | screening | scoring | diligence | memo
}

function Step({
  label,
  state,
  isLast,
}: {
  label: string;
  state: "done" | "active" | "pending";
  isLast: boolean;
}) {
  return (
    <div className="flex flex-1 items-center gap-2">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-medium",
            state === "done" && "border-emerald-300 bg-emerald-50 text-emerald-700",
            state === "active" && "border-blue-300 bg-blue-50 text-blue-700",
            state === "pending" && "border-border bg-muted text-muted-foreground",
          )}
        >
          {state === "done" ? (
            <Check className="size-3.5" />
          ) : state === "active" ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : null}
        </span>
        <span
          className={cn(
            "text-sm font-medium",
            state === "active" && "text-foreground",
            state === "done" && "text-foreground/80",
            state === "pending" && "text-muted-foreground",
          )}
        >
          {label}
        </span>
      </div>
      {!isLast && (
        <span
          className={cn(
            "h-px flex-1",
            state === "done" ? "bg-emerald-300" : "bg-border",
          )}
        />
      )}
    </div>
  );
}

export function AnalysisProgress({
  status,
  error,
  busy,
  onAnalyze,
  enrichmentReport,
}: {
  status: AnalysisStatus;
  error: string | null;
  busy: boolean;
  onAnalyze: (force: boolean) => void;
  enrichmentReport?: EnrichmentReport | null;
}) {
  const failed = status === "failed";
  const activeIndex = ACTIVE_INDEX[status] ?? -1;

  const heading = failed
    ? "Analysis failed"
    : status === "received"
      ? "Queued for analysis"
      : "Analyzing application";
  const subtitle = failed
    ? "The pipeline stopped before completing. You can retry it."
    : status === "received"
      ? "Enrichment, screening, scoring, diligence and memo will run automatically."
      : status === "enriching"
        ? "Fetching self-declared founder links as evidence - runs before screening."
        : "Live - scores, claims and the memo appear below as each stage lands.";

  return (
    <section
      className={cn(
        "rounded-xl border px-4 py-4",
        failed ? "border-red-200 bg-red-50/60" : "border-border bg-card",
      )}
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {failed ? (
            <TriangleAlert className="size-4 text-red-600" />
          ) : status !== "received" ? (
            <Loader2 className="size-4 animate-spin text-blue-600" />
          ) : null}
          <div>
            <div className="text-sm font-semibold">{heading}</div>
            <div className="text-xs text-muted-foreground">{subtitle}</div>
          </div>
        </div>
        {(status === "received" || failed) && (
          <Button size="sm" onClick={() => onAnalyze(false)} disabled={busy}>
            {busy ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : failed ? (
              <RefreshCw className="size-3.5" />
            ) : (
              <Play className="size-3.5" />
            )}
            {failed ? "Retry analysis" : "Run analysis"}
          </Button>
        )}
      </div>

      <div className="flex items-center">
        {STAGES.map((stage, i) => {
          const state: "done" | "active" | "pending" = failed
            ? "pending"
            : i < activeIndex
              ? "done"
              : i === activeIndex
                ? "active"
                : "pending";
          return (
            <Step
              key={stage.key}
              label={stage.label}
              state={state}
              isLast={i === STAGES.length - 1}
            />
          );
        })}
      </div>

      {/* Enrichment outcomes: honest per-source result (fetched / blocked / error).
          The report is committed once the enriching stage finishes, so we show a
          "fetching" note while it runs and the compact chips from then on. */}
      {!failed && status === "enriching" && !hasEnrichment(enrichmentReport) && (
        <p className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" />
          Fetching self-declared founder links...
        </p>
      )}
      {!failed && hasEnrichment(enrichmentReport) && (
        <div className="mt-4 border-t border-border pt-3">
          <div className="mb-1.5 text-xs font-medium text-muted-foreground">
            Enrichment - declared links fetched as evidence
          </div>
          <EnrichmentOutcomes report={enrichmentReport!} />
        </div>
      )}

      {failed && error && (
        <p className="mt-4 rounded-lg border border-red-200 bg-white/60 px-3 py-2 font-mono text-xs text-red-800">
          {error}
        </p>
      )}
    </section>
  );
}

/** Subtle re-run control shown once analysis is complete (uses force=true). */
export function ReRunAnalysis({
  busy,
  onRerun,
}: {
  busy: boolean;
  onRerun: () => void;
}) {
  return (
    <Button variant="ghost" size="sm" onClick={onRerun} disabled={busy}>
      {busy ? (
        <Loader2 className="size-3.5 animate-spin" />
      ) : (
        <RefreshCw className="size-3.5" />
      )}
      Re-run analysis
    </Button>
  );
}
