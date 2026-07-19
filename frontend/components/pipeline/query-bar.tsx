"use client";

import * as React from "react";
import { ChevronDown, Loader2, Search, X } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import type { QueryResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

// The seven founder attributes the query parser actually understands
// (see backend/app/reasoning/query.py `_ATTRIBUTE_MATCHERS`). The Attribute
// dropdown only ever offers filters the structured search can honestly answer.
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

// Sector, stage and geography are single-valued (the parser resolves one of
// each); attributes compose. Tokens are the single source of truth for the
// composed structured query.
type Selected = {
  sector: string | null;
  stage: string | null;
  geography: string | null;
  attributes: string[];
};

type FilterKind = "sector" | "stage" | "geography" | "attribute";

const EMPTY: Selected = { sector: null, stage: null, geography: null, attributes: [] };

/** Compose the selected filters into the comma-separated structured query the
 *  offline (deterministic, $0) parser resolves - the same query shape the old
 *  chips ran, just assembled from the dropdowns. */
function compose(s: Selected): string {
  return [s.sector, s.stage, s.geography, ...s.attributes].filter(Boolean).join(", ");
}

function tokensOf(s: Selected): { kind: FilterKind; value: string }[] {
  const t: { kind: FilterKind; value: string }[] = [];
  if (s.sector) t.push({ kind: "sector", value: s.sector });
  if (s.stage) t.push({ kind: "stage", value: s.stage });
  if (s.geography) t.push({ kind: "geography", value: s.geography });
  for (const a of s.attributes) t.push({ kind: "attribute", value: a });
  return t;
}

function FilterSelect({
  label,
  options,
  activeValues,
  onPick,
  disabled,
}: {
  label: string;
  options: readonly string[];
  activeValues: string[];
  onPick: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="relative">
      <select
        // Controlled to "" so the control always reads as an "add filter" menu;
        // the active selection lives in the token row below, not in the box.
        value=""
        disabled={disabled || options.length === 0}
        onChange={(e) => onPick(e.target.value)}
        className="h-8 cursor-pointer appearance-none rounded-lg border border-border bg-muted/40 py-0 pr-7 pl-2.5 text-xs font-medium text-foreground transition-colors hover:bg-muted focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        aria-label={label}
      >
        <option value="">{label}</option>
        {options.map((o) => (
          <option key={o} value={o} disabled={activeValues.includes(o)}>
            {o}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute top-1/2 right-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
    </div>
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
  const [selected, setSelected] = React.useState<Selected>(EMPTY);

  // `deterministic` pins the offline parser (backend="offline"): the composed
  // filter query is already structured, so it resolves with no LLM call.
  // Free-text stays on the default parser (live LLM with offline fallback).
  async function run(query: string, deterministic = false) {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
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

  // Apply a new filter selection: recompose and run offline, or clear when the
  // last filter is removed.
  function applySelected(next: Selected) {
    setSelected(next);
    const query = compose(next);
    if (!query) {
      onClear();
      return;
    }
    run(query, true);
  }

  function pick(kind: FilterKind, value: string) {
    if (!value) return;
    if (kind === "attribute") {
      if (selected.attributes.includes(value)) return;
      applySelected({ ...selected, attributes: [...selected.attributes, value] });
    } else {
      applySelected({ ...selected, [kind]: value });
    }
  }

  function removeToken(kind: FilterKind, value: string) {
    if (kind === "attribute") {
      applySelected({
        ...selected,
        attributes: selected.attributes.filter((a) => a !== value),
      });
    } else {
      applySelected({ ...selected, [kind]: null });
    }
  }

  function clearFilters() {
    setSelected(EMPTY);
    onClear();
  }

  function clearAll() {
    setQ("");
    setSelected(EMPTY);
    onClear();
  }

  const tokens = tokensOf(selected);
  const attrsUsed = tokens.map((t) => t.value); // for disabling already-picked options

  return (
    <div className="flex flex-col gap-3">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!q.trim()) return;
          // A free-text search is its own query; drop any structured filters so
          // the token row never goes stale against the results shown.
          setSelected(EMPTY);
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
          <Button type="button" variant="outline" size="lg" onClick={clearAll}>
            <X /> Clear
          </Button>
        )}
      </form>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">Filter</span>
        <FilterSelect
          label="Sector"
          options={facets?.sectors ?? []}
          activeValues={attrsUsed}
          onPick={(v) => pick("sector", v)}
          disabled={loading}
        />
        <FilterSelect
          label="Stage"
          options={facets?.stages ?? []}
          activeValues={attrsUsed}
          onPick={(v) => pick("stage", v)}
          disabled={loading}
        />
        <FilterSelect
          label="Geography"
          options={facets?.geographies ?? []}
          activeValues={attrsUsed}
          onPick={(v) => pick("geography", v)}
          disabled={loading}
        />
        <FilterSelect
          label="Attribute"
          options={ATTRIBUTES}
          activeValues={attrsUsed}
          onPick={(v) => pick("attribute", v)}
          disabled={loading}
        />
        <span className="text-xs text-muted-foreground/70">
          Deterministic - filters and ranks the pipeline, not open-ended Q&amp;A.
        </span>
      </div>

      {tokens.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {tokens.map((t) => (
            <span
              key={`${t.kind}:${t.value}`}
              className="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 py-0.5 pr-1 pl-2 text-xs font-medium text-blue-700"
            >
              {t.value}
              <button
                type="button"
                onClick={() => removeToken(t.kind, t.value)}
                className="rounded-sm p-0.5 text-blue-500 transition-colors hover:bg-blue-100 hover:text-blue-800"
                aria-label={`Remove ${t.value}`}
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
          <button
            type="button"
            onClick={clearFilters}
            className={cn(
              "ml-0.5 text-xs font-medium text-muted-foreground underline-offset-2",
              "transition-colors hover:text-foreground hover:underline",
            )}
          >
            Clear
          </button>
        </div>
      )}

      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
