"use client";

import * as React from "react";
import { Loader2, Search, X } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import type { QueryResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

// The seven founder attributes the query parser actually understands
// (see backend/app/reasoning/query.py `_ATTRIBUTE_MATCHERS`). Chips only ever
// offer queries the structured search can honestly answer.
const ATTRIBUTES = [
  "technical founder",
  "repeat founder",
  "first-time founder",
  "non-technical founder",
  "enterprise traction",
  "no prior VC backing",
  "open source",
] as const;

export interface QueryFacets {
  sectors: string[];
  stages: string[];
  geographies: string[];
}

function Chip({
  label,
  onClick,
  disabled,
  active,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "rounded-full border px-2.5 py-1 text-xs transition-colors disabled:opacity-50",
        active
          ? "border-blue-300 bg-blue-50 text-blue-700"
          : "border-border bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {label}
    </button>
  );
}

export function QueryBar({
  onResults,
  onClear,
  active,
  facets,
}: {
  onResults: (r: QueryResponse) => void;
  onClear: () => void;
  active: boolean;
  facets?: QueryFacets;
}) {
  const [q, setQ] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [ran, setRan] = React.useState<string | null>(null);

  // Chips run deterministically (backend="offline"): their queries are already
  // structured, so the offline parser resolves them exactly - no LLM call.
  // Free-text stays on the default parser (live LLM with offline fallback).
  async function run(query: string, deterministic = false) {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setRan(query);
    try {
      const res = await api.query(query, deterministic ? "offline" : undefined);
      onResults(res);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Search failed. Is the backend running?",
      );
    } finally {
      setLoading(false);
    }
  }

  function runChip(query: string) {
    setQ(query);
    run(query, true);
  }

  const facetChips: { group: string; values: string[] }[] = [
    { group: "Sectors", values: facets?.sectors ?? [] },
    { group: "Stages", values: facets?.stages ?? [] },
    { group: "Geographies", values: facets?.geographies ?? [] },
  ].filter((g) => g.values.length > 0);

  const combinedExample =
    facets?.sectors[0]
      ? `technical founder, ${facets.sectors[0]}, no prior VC backing`
      : null;

  return (
    <div className="flex flex-col gap-3">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          run(q);
        }}
        className="flex items-center gap-2"
      >
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search founders by attribute, sector, stage or geography…"
            className="h-10 pl-9"
          />
        </div>
        <Button type="submit" size="lg" disabled={loading || !q.trim()}>
          {loading ? <Loader2 className="size-4 animate-spin" /> : <Search />}
          Search
        </Button>
        {active && (
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={() => {
              setQ("");
              setRan(null);
              onClear();
            }}
          >
            <X /> Clear
          </Button>
        )}
      </form>

      <p className="text-xs text-muted-foreground">
        Structured founder search - it filters and ranks the pipeline against the
        attributes below, not open-ended Q&amp;A. Tap a chip to run it, or combine
        terms with commas.
      </p>

      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="w-20 shrink-0 text-xs font-medium text-muted-foreground">
            Attributes
          </span>
          {ATTRIBUTES.map((a) => (
            <Chip
              key={a}
              label={a}
              onClick={() => runChip(a)}
              disabled={loading}
              active={ran === a}
            />
          ))}
        </div>

        {facetChips.map(({ group, values }) => (
          <div key={group} className="flex flex-wrap items-center gap-1.5">
            <span className="w-20 shrink-0 text-xs font-medium text-muted-foreground">
              {group}
            </span>
            {values.map((v) => (
              <Chip
                key={v}
                label={v}
                onClick={() => runChip(v)}
                disabled={loading}
                active={ran === v}
              />
            ))}
          </div>
        ))}

        {combinedExample && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="w-20 shrink-0 text-xs font-medium text-muted-foreground">
              Combined
            </span>
            <Chip
              label={combinedExample}
              onClick={() => runChip(combinedExample)}
              disabled={loading}
              active={ran === combinedExample}
            />
          </div>
        )}
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
