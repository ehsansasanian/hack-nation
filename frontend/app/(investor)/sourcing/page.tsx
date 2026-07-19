"use client";

import * as React from "react";
import Link from "next/link";
import { Loader2, Radar, Send, TriangleAlert } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import type { ScanCandidate, ScanSummary } from "@/lib/types";
import { AXIS_META, sourceTint } from "@/lib/format";
import type { Axis } from "@/lib/types";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";

const SOURCES = [
  { id: "github", label: "GitHub", hint: "fast-rising AI/infra repos" },
  { id: "hn", label: "Hacker News", hint: "Show HN launches" },
  { id: "arxiv", label: "arXiv", hint: "recent cs.AI authors" },
];

function Stat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="flex flex-col">
      <span className={cn("text-lg font-semibold tabular-nums", tone)}>{value}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

const STATUS_STYLE: Record<string, string> = {
  in_review: "border-emerald-200 bg-emerald-50 text-emerald-700",
  screened_out: "border-zinc-200 bg-zinc-100 text-zinc-500",
  out_of_thesis: "border-amber-200 bg-amber-50 text-amber-700",
};

function CandidateCard({ c }: { c: ScanCandidate }) {
  return (
    <Card className="space-y-2 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn("rounded border px-1.5 py-0.5 text-xs font-medium uppercase", sourceTint(c.source))}>
          {c.source}
        </span>
        <span className="font-medium">{c.company}</span>
        <span className="text-xs text-muted-foreground">@{c.handle}</span>
        <span
          className={cn(
            "ml-auto rounded-md border px-1.5 py-0.5 text-xs font-medium",
            STATUS_STYLE[c.status] ?? "border-border bg-muted text-muted-foreground",
          )}
        >
          {c.status.replace(/_/g, " ")}
        </span>
      </div>
      <p className="text-sm text-muted-foreground">{c.why_flagged}</p>
      <div className="flex flex-wrap items-center gap-2">
        {(Object.keys(AXIS_META) as Axis[])
          .filter((a) => c.scores[a] != null)
          .map((a) => (
            <span
              key={a}
              className={cn("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs", AXIS_META[a].tint)}
            >
              <span className="font-semibold uppercase opacity-70">{AXIS_META[a].short}</span>
              <span className="font-semibold tabular-nums">{c.scores[a].toFixed(1)}</span>
            </span>
          ))}
        {c.outreach_drafted && (
          <span className="inline-flex items-center gap-1 text-xs text-blue-700">
            <Send className="size-3" /> outreach drafted
          </span>
        )}
        {c.application_id && (
          <Link
            href={`/applications/${c.application_id}`}
            className="ml-auto text-xs font-medium text-blue-700 hover:underline"
          >
            View application →
          </Link>
        )}
      </div>
    </Card>
  );
}

export default function SourcingPage() {
  const [selected, setSelected] = React.useState<Record<string, boolean>>({
    github: true,
    hn: true,
    arxiv: false,
  });
  const [limit, setLimit] = React.useState(10);
  const [scanning, setScanning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<ScanSummary | null>(null);

  const sources = Object.keys(selected).filter((s) => selected[s]);

  async function scan() {
    if (sources.length === 0) return;
    setScanning(true);
    setError(null);
    try {
      const summary = await api.scan({ sources, limit });
      setResult(summary);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Scan failed.");
    } finally {
      setScanning(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Outbound sourcing"
        subtitle="Scan live sources, dedup against memory, and funnel above-threshold founders into the pipeline."
      />
      <div className="space-y-5 px-8 py-6">
        <Card className="space-y-4 p-5">
          <div className="flex flex-wrap gap-2">
            {SOURCES.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => setSelected((prev) => ({ ...prev, [s.id]: !prev[s.id] }))}
                className={cn(
                  "flex flex-col items-start rounded-lg border px-3 py-2 text-left transition-colors",
                  selected[s.id]
                    ? "border-blue-300 bg-blue-50"
                    : "border-border bg-background hover:bg-muted",
                )}
              >
                <span className="flex items-center gap-2 text-sm font-medium">
                  <span
                    className={cn(
                      "flex size-4 items-center justify-center rounded border",
                      selected[s.id] ? "border-blue-600 bg-blue-600 text-white" : "border-border",
                    )}
                  >
                    {selected[s.id] && "✓"}
                  </span>
                  {s.label}
                </span>
                <span className="ml-6 text-xs text-muted-foreground">{s.hint}</span>
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-sm font-medium">Limit per source</label>
            <Input
              type="number"
              min={1}
              max={30}
              value={limit}
              onChange={(e) => setLimit(Math.max(1, Number(e.target.value) || 1))}
              className="h-9 w-20"
            />
            <Button size="lg" onClick={scan} disabled={scanning || sources.length === 0}>
              {scanning ? <Loader2 className="size-4 animate-spin" /> : <Radar className="size-4" />}
              {scanning ? "Scanning live sources…" : "Scan"}
            </Button>
            <span className="text-xs text-muted-foreground">
              Live network call - unchanged results dedup to zero new signals.
            </span>
          </div>
        </Card>

        {error && (
          <div className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <TriangleAlert className="size-4" /> {error}
          </div>
        )}

        {result && (
          <>
            <Card className="flex flex-wrap gap-x-8 gap-y-3 px-5 py-4">
              <Stat label="Signals fetched" value={result.signals_fetched} />
              <Stat label="New signals" value={result.signals_created} tone="text-emerald-600" />
              <Stat label="Deduplicated" value={result.signals_duplicate} />
              <Stat label="Founders created" value={result.founders_created} />
              <Stat label="Applications created" value={result.applications_created} />
              <Stat label="Outbound in review" value={result.outbound_in_review} tone="text-blue-600" />
              <Stat label="Outreach drafts" value={result.outreach_drafts} />
            </Card>

            {Object.keys(result.source_errors).length > 0 && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                <div className="mb-1 flex items-center gap-1.5 font-medium">
                  <TriangleAlert className="size-4" /> Some sources errored
                </div>
                <ul className="list-disc pl-5">
                  {Object.entries(result.source_errors).map(([src, msg]) => (
                    <li key={src}>
                      <span className="font-medium">{src}:</span> {msg}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <h2 className="mb-3 text-sm font-semibold text-muted-foreground">
                Candidates ({result.candidates.length})
              </h2>
              {result.candidates.length === 0 ? (
                <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
                  No new candidates surfaced this scan (all deduplicated against memory).
                </p>
              ) : (
                <div className="grid gap-3 md:grid-cols-2">
                  {result.candidates.map((c, i) => (
                    <CandidateCard key={`${c.source}-${c.handle}-${i}`} c={c} />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
