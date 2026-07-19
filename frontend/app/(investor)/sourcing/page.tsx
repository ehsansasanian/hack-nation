"use client";

import * as React from "react";
import Link from "next/link";
import { Inbox, Loader2, Lock, Radar, Send, TriangleAlert } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import type { ScanCandidate, ScanSummary } from "@/lib/types";
import { AXIS_META, sourceTint } from "@/lib/format";
import type { Axis } from "@/lib/types";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";

// Connected, real scanners - each is wired to POST /sourcing/scan.
const CONNECTED_SOURCES = [
  { id: "github", label: "GitHub", hint: "fast-rising AI/infra repos" },
  { id: "hn", label: "Hacker News", hint: "Show HN launches" },
  { id: "arxiv", label: "arXiv", hint: "recent cs.AI authors" },
  { id: "news", label: "Startup news (RSS)", hint: "TechCrunch / VentureBeat funding & launches" },
];

// Sources that would need a paid license or private API. Shown honestly as
// configurable-but-disabled - we never fabricate their data.
const LICENSED_SOURCES = [
  { label: "LinkedIn", hint: "founder & team graph" },
  { label: "PitchBook", hint: "private-market financials" },
  { label: "Preqin", hint: "fund & LP data" },
  { label: "Crunchbase", hint: "funding rounds & orgs" },
  { label: "Product Hunt", hint: "launch traction" },
];

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </h3>
  );
}

function CheckBox({ checked, disabled }: { checked: boolean; disabled?: boolean }) {
  return (
    <span
      className={cn(
        "flex size-4 items-center justify-center rounded border text-white",
        checked && !disabled && "border-blue-600 bg-blue-600",
        checked && disabled && "border-muted-foreground/40 bg-muted-foreground/40",
        !checked && "border-border",
      )}
    >
      {checked && "✓"}
    </span>
  );
}

function ConnectedToggle({
  label,
  hint,
  checked,
  onToggle,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        "flex w-full flex-col items-start rounded-lg border px-3 py-2 text-left transition-colors",
        checked ? "border-blue-300 bg-blue-50" : "border-border bg-background hover:bg-muted",
      )}
    >
      <span className="flex items-center gap-2 text-sm font-medium">
        <CheckBox checked={checked} />
        {label}
      </span>
      <span className="ml-6 text-xs text-muted-foreground">{hint}</span>
    </button>
  );
}

function LicensedSource({ label, hint }: { label: string; hint: string }) {
  return (
    <div
      aria-disabled
      title="Requires API access / license - not connected"
      className="flex w-full cursor-not-allowed flex-col items-start rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2 text-left opacity-70"
    >
      <span className="flex w-full items-center gap-2 text-sm font-medium text-muted-foreground">
        <CheckBox checked={false} disabled />
        {label}
        <span className="ml-auto inline-flex items-center gap-1 rounded-md border border-transparent bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
          <Lock className="size-3" /> requires API access / license - not connected
        </span>
      </span>
      <span className="ml-6 text-xs text-muted-foreground">{hint}</span>
    </div>
  );
}

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

// Backend keeps the `out_of_thesis` status value; surface it as "out of mandate".
const STATUS_LABEL: Record<string, string> = {
  out_of_thesis: "out of mandate",
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
          {STATUS_LABEL[c.status] ?? c.status.replace(/_/g, " ")}
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
    news: true,
  });
  const [limit, setLimit] = React.useState(10);
  const [scanning, setScanning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<ScanSummary | null>(null);

  const sources = CONNECTED_SOURCES.map((s) => s.id).filter((id) => selected[id]);

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
        <Card className="space-y-5 p-5">
          {/* Connected: real scanners wired to the scan. */}
          <div>
            <GroupLabel>Connected</GroupLabel>
            <div className="grid gap-2 sm:grid-cols-2">
              {CONNECTED_SOURCES.map((s) => (
                <ConnectedToggle
                  key={s.id}
                  label={s.label}
                  hint={s.hint}
                  checked={!!selected[s.id]}
                  onToggle={() => setSelected((prev) => ({ ...prev, [s.id]: !prev[s.id] }))}
                />
              ))}
            </div>
          </div>

          {/* Available with access: honest, disabled - never faked. */}
          <div>
            <GroupLabel>Available with access</GroupLabel>
            <div className="grid gap-2 sm:grid-cols-2">
              {LICENSED_SOURCES.map((s) => (
                <LicensedSource key={s.label} label={s.label} hint={s.hint} />
              ))}
            </div>
          </div>

          {/* Inbound applications: the other funnel leg, always on. */}
          <div>
            <GroupLabel>Inbound applications</GroupLabel>
            <div className="flex flex-col items-start gap-1 rounded-lg border border-blue-200 bg-blue-50/60 px-3 py-2 sm:flex-row sm:items-center">
              <span className="flex items-center gap-2 text-sm font-medium">
                <CheckBox checked disabled />
                <Inbox className="size-4 text-blue-700" />
                Inbound applications
                <span className="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-white/60 px-1.5 py-0.5 text-[10px] font-medium text-blue-700">
                  <Lock className="size-3" /> always on
                </span>
              </span>
              <span className="text-xs text-muted-foreground sm:ml-6">
                Founder-submitted decks converge into the same screening funnel as
                outbound finds.{" "}
                <Link href="/apply" className="font-medium text-blue-700 hover:underline">
                  Open the apply flow →
                </Link>
              </span>
            </div>
          </div>

          {/* Run controls. */}
          <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
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
                  No new outbound candidates this scan. News signals enrich memory and
                  corroborate companies; GitHub/HN finds that clear the mandate surface here.
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
