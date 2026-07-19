"use client";

import * as React from "react";

import { api } from "@/lib/api";
import type { Application, QueryResponse } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Async, useFetch } from "@/components/async";
import { QueryBar, type QueryFacets } from "@/components/pipeline/query-bar";
import { QueryResults } from "@/components/pipeline/query-results";
import {
  PipelineTable,
  type PipelineRow,
} from "@/components/pipeline/pipeline-table";

async function loadPipeline(): Promise<PipelineRow[]> {
  const apps = await api.pipeline();
  // Enrich each row with a per-claim trust summary (the pipeline endpoint
  // carries scores but not claims). Failures degrade gracefully to no summary.
  const details = await Promise.allSettled(apps.map((a) => api.application(a.id)));
  const rows: PipelineRow[] = apps.map((app, i) => {
    const d = details[i];
    if (d.status !== "fulfilled") return { app };
    const claims = d.value.claims;
    return {
      app,
      trust: {
        contradicted: claims.filter((c) => c.trust_level === "contradicted").length,
        verified: claims.filter((c) => c.trust_level === "verified").length,
        total: claims.length,
      },
    };
  });
  return rank(rows);
}

function bestScore(app: Application): number {
  return app.scores.reduce((m, s) => Math.max(m, s.value), 0);
}

/** Distinct sectors/stages/geos actually present in the pipeline, for the search chips. */
function computeFacets(rows: PipelineRow[]): QueryFacets {
  const uniq = (vals: (string | null)[]) =>
    [...new Set(vals.filter((v): v is string => Boolean(v)))].sort();
  return {
    sectors: uniq(rows.map((r) => r.app.company.sector)),
    stages: uniq(rows.map((r) => r.app.company.stage)),
    geographies: uniq(rows.map((r) => r.app.company.geography)),
  };
}

/** Screened-out applications sink to the bottom; the rest lead with their strongest axis. */
function rank(rows: PipelineRow[]): PipelineRow[] {
  return [...rows].sort((a, b) => {
    const aOut = a.app.status === "screened_out" ? 1 : 0;
    const bOut = b.app.status === "screened_out" ? 1 : 0;
    if (aOut !== bOut) return aOut - bOut;
    return bestScore(b.app) - bestScore(a.app);
  });
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="flex flex-col">
      <span className={`text-lg font-semibold tabular-nums ${tone ?? ""}`}>{value}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

export default function PipelinePage() {
  const state = useFetch(loadPipeline, []);
  const [results, setResults] = React.useState<QueryResponse | null>(null);

  return (
    <div>
      <PageHeader
        title="Pipeline"
        subtitle="Every application ranked across three independent axes - never averaged."
      />
      <div className="space-y-5 px-8 py-6">
        <QueryBar
          onResults={setResults}
          onClear={() => setResults(null)}
          active={results !== null}
          facets={state.data ? computeFacets(state.data) : undefined}
        />

        {results ? (
          <QueryResults data={results} />
        ) : (
          <Async state={state}>
            {(rows) => {
              const active = rows.filter((r) => r.app.status !== "screened_out");
              const contradicted = rows.filter(
                (r) => (r.trust?.contradicted ?? 0) > 0,
              ).length;
              const coldStart = rows.filter((r) =>
                r.app.scores.some((s) => s.cold_start),
              ).length;
              const outbound = rows.filter((r) => r.app.origin === "outbound").length;
              return (
                <>
                  <div className="flex flex-wrap gap-x-10 gap-y-3 rounded-xl border border-border bg-card px-5 py-4">
                    <Stat label="Applications" value={rows.length} />
                    <Stat label="Active in funnel" value={active.length} />
                    <Stat label="Outbound sourced" value={outbound} />
                    <Stat
                      label="With contradictions"
                      value={contradicted}
                      tone={contradicted ? "text-red-600" : undefined}
                    />
                    <Stat label="Cold-start" value={coldStart} />
                  </div>
                  <PipelineTable rows={rows} />
                </>
              );
            }}
          </Async>
        )}
      </div>
    </div>
  );
}
