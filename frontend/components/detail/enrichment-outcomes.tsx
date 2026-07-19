import * as React from "react";
import { AtSign, Ban, Building2, Code2, Globe, TriangleAlert } from "lucide-react";

import type {
  EnrichmentOutcome,
  EnrichmentReport,
  EnrichmentSource,
  FetchOutcome,
} from "@/lib/types";
import { cn } from "@/lib/utils";

// Presentation for each fetch source. Brand icons are intentionally avoided
// (lucide dropped them) - neutral marks + explicit labels read clearer anyway.
const SOURCE_META: Record<EnrichmentSource, { label: string; Icon: typeof Code2 }> = {
  github: { label: "GitHub", Icon: Code2 },
  web: { label: "Website", Icon: Globe },
  linkedin: { label: "LinkedIn", Icon: Building2 },
  x: { label: "X", Icon: AtSign },
};

const SOURCE_ORDER: EnrichmentSource[] = ["github", "web", "linkedin", "x"];

const OUTCOME_TONE: Record<FetchOutcome, string> = {
  fetched: "border-emerald-200 bg-emerald-50 text-emerald-800",
  blocked: "border-amber-200 bg-amber-50 text-amber-800",
  error: "border-red-200 bg-red-50 text-red-800",
};

/** Short, honest one-liner for a source outcome. Blocked/error are shown as
 *  what they are - not as a failure of the whole enriching stage. */
function outcomeText(o: EnrichmentOutcome, showCount: boolean): string {
  if (o.outcome === "fetched") {
    return showCount && o.signal_count > 0
      ? `${o.signal_count} signal${o.signal_count === 1 ? "" : "s"}`
      : "fetched";
  }
  if (o.outcome === "blocked") return "blocked · reference";
  return "error";
}

export function SourceOutcomeChip({
  source,
  outcome,
  showCount = true,
}: {
  source: EnrichmentSource;
  outcome: EnrichmentOutcome;
  showCount?: boolean;
}) {
  const meta = SOURCE_META[source];
  const Icon = outcome.outcome === "blocked" ? Ban : outcome.outcome === "error" ? TriangleAlert : meta.Icon;
  const title =
    outcome.note ??
    (outcome.outcome === "fetched"
      ? `${meta.label}: fetched and ingested as evidence`
      : `${meta.label}: ${outcome.outcome}`);
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium",
        OUTCOME_TONE[outcome.outcome],
      )}
    >
      <Icon className="size-3" />
      {meta.label}
      <span className="font-normal opacity-80">· {outcomeText(outcome, showCount)}</span>
    </span>
  );
}

/** A compact row of per-source outcomes for a whole (or filtered) report. */
export function EnrichmentOutcomes({
  report,
  showCounts = true,
  sources,
  className,
}: {
  report: EnrichmentReport;
  showCounts?: boolean;
  /** Restrict to these sources (e.g. only the ones a given founder declared). */
  sources?: EnrichmentSource[];
  className?: string;
}) {
  const keys = (sources ?? SOURCE_ORDER).filter((s) => report[s]);
  if (keys.length === 0) return null;
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {keys.map((s) => (
        <SourceOutcomeChip key={s} source={s} outcome={report[s]!} showCount={showCounts} />
      ))}
    </div>
  );
}

export function hasEnrichment(report: EnrichmentReport | null | undefined): boolean {
  return !!report && Object.keys(report).length > 0;
}
