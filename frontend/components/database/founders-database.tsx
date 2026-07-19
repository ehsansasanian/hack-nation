"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowUp,
  ChevronsUpDown,
  History,
  Search,
  Sparkles,
  Users,
  X,
} from "lucide-react";

import { api } from "@/lib/api";
import type {
  DirectoryFounder,
  FounderMatch,
  FounderMatches,
  RecombinationCandidate,
} from "@/lib/types";
import { Async, Spinner, useFetch } from "@/components/async";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { HypotheticalTeamCard } from "./hypothetical-team-card";

type SortKey = "name" | "classification" | "founder_score" | "available" | "returning";
type SortDir = "asc" | "desc";

const CLASSIFICATION_RANK: Record<string, number> = {
  "technical + commercial": 0,
  technical: 1,
  commercial: 2,
  unclassified: 3,
};

function ClassBadges({ f }: { f: DirectoryFounder }) {
  return (
    <span className="flex flex-wrap gap-1">
      {f.technical && (
        <span className="rounded-md border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[0.7rem] font-medium text-blue-700">
          technical
        </span>
      )}
      {f.commercial && (
        <span className="rounded-md border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[0.7rem] font-medium text-emerald-700">
          commercial
        </span>
      )}
      {!f.technical && !f.commercial && (
        <span className="rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[0.7rem] font-medium text-slate-500">
          unclassified
        </span>
      )}
    </span>
  );
}

function SortHeader({
  label,
  col,
  sort,
  onSort,
  className,
}: {
  label: string;
  col: SortKey;
  sort: { key: SortKey; dir: SortDir };
  onSort: (k: SortKey) => void;
  className?: string;
}) {
  const active = sort.key === col;
  const Icon = !active ? ChevronsUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <th className={`px-2.5 py-2.5 font-medium ${className ?? ""}`}>
      <button
        type="button"
        onClick={() => onSort(col)}
        className={`inline-flex items-center gap-1 hover:text-foreground ${
          active ? "text-foreground" : ""
        }`}
      >
        {label}
        <Icon className="size-3" />
      </button>
    </th>
  );
}

function compare(a: DirectoryFounder, b: DirectoryFounder, key: SortKey): number {
  switch (key) {
    case "name":
      return a.name.localeCompare(b.name);
    case "classification":
      return (
        (CLASSIFICATION_RANK[a.classification] ?? 9) -
        (CLASSIFICATION_RANK[b.classification] ?? 9)
      );
    case "founder_score":
      return (a.founder_score ?? -1) - (b.founder_score ?? -1);
    case "available":
      return Number(a.available) - Number(b.available);
    case "returning":
      return Number(a.returning) - Number(b.returning);
  }
}

/** A candidate chip from "find matches". Clicking completes the pair. */
function SuggestionChip({
  c,
  onPick,
}: {
  c: RecombinationCandidate;
  onPick: (id: number) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onPick(c.founder_id)}
      className="flex flex-col items-start gap-1 rounded-lg border border-violet-200 bg-white px-3 py-2 text-left transition-colors hover:border-violet-400 hover:bg-violet-50"
    >
      <span className="flex flex-wrap items-center gap-1.5">
        <span className="text-sm font-semibold text-violet-900">{c.name}</span>
        {c.founder_score != null && (
          <span className="rounded border border-border bg-background px-1 text-[0.7rem] tabular-nums text-muted-foreground">
            {c.founder_score.toFixed(1)}
          </span>
        )}
        {c.fills.map((f) => (
          <span
            key={f}
            className="rounded border border-violet-200 bg-violet-50 px-1 text-[0.7rem] font-medium text-violet-700"
          >
            {f}
          </span>
        ))}
      </span>
      <span className="text-xs text-muted-foreground">{c.why}</span>
    </button>
  );
}

function Directory({ founders }: { founders: DirectoryFounder[] }) {
  const byId = React.useMemo(
    () => new Map(founders.map((f) => [f.id, f])),
    [founders],
  );
  const [sort, setSort] = React.useState<{ key: SortKey; dir: SortDir }>({
    key: "founder_score",
    dir: "desc",
  });
  const [selected, setSelected] = React.useState<number[]>([]);

  // Match for the currently-selected pair.
  const [match, setMatch] = React.useState<FounderMatch | null>(null);
  const [matchLoading, setMatchLoading] = React.useState(false);
  const [matchError, setMatchError] = React.useState<string | null>(null);

  // "Find matches" suggestions for one founder.
  const [suggest, setSuggest] = React.useState<FounderMatches | null>(null);
  const [suggestLoading, setSuggestLoading] = React.useState(false);

  const pairKey = selected.join("-");
  React.useEffect(() => {
    if (selected.length !== 2) {
      setMatch(null);
      setMatchError(null);
      return;
    }
    let alive = true;
    setMatchLoading(true);
    setMatchError(null);
    api
      .matchFounders(selected[0], selected[1])
      .then((m) => alive && setMatch(m))
      .catch((e) => alive && setMatchError((e as Error).message))
      .finally(() => alive && setMatchLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pairKey]);

  const toggle = (id: number) =>
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      const next = [...prev, id];
      return next.length > 2 ? next.slice(1) : next; // rolling pair
    });

  const findMatches = async (id: number) => {
    setSelected([id]);
    setSuggest(null);
    setSuggestLoading(true);
    try {
      setSuggest(await api.founderMatches(id));
    } catch {
      setSuggest(null);
    } finally {
      setSuggestLoading(false);
    }
  };

  const onSort = (key: SortKey) =>
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key, dir: key === "name" ? "asc" : "desc" },
    );

  const rows = React.useMemo(() => {
    const sorted = [...founders].sort((a, b) => compare(a, b, sort.key));
    return sort.dir === "asc" ? sorted : sorted.reverse();
  }, [founders, sort]);

  const clearAll = () => {
    setSelected([]);
    setSuggest(null);
  };

  return (
    <div className="space-y-5">
      {/* selection bar */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <Users className="size-4 text-muted-foreground" />
          Assess a team
        </span>
        {selected.length === 0 ? (
          <span className="text-sm text-muted-foreground">
            Select two founders below (or use{" "}
            <span className="font-medium">Find matches</span>) to render a
            hypothetical team.
          </span>
        ) : (
          <span className="flex flex-wrap items-center gap-1.5">
            {selected.map((id) => (
              <span
                key={id}
                className="inline-flex items-center gap-1 rounded-md border border-violet-200 bg-violet-50 px-1.5 py-0.5 text-xs font-medium text-violet-800"
              >
                {byId.get(id)?.name ?? `#${id}`}
                <button type="button" onClick={() => toggle(id)} aria-label="remove">
                  <X className="size-3 hover:text-violet-950" />
                </button>
              </span>
            ))}
            {selected.length === 1 && (
              <span className="text-xs text-muted-foreground">
                pick one more, or Find matches
              </span>
            )}
            <Button variant="ghost" size="xs" onClick={clearAll}>
              Clear
            </Button>
          </span>
        )}
      </div>

      {/* directory table */}
      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full min-w-[760px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/40 text-left text-xs font-medium whitespace-nowrap text-muted-foreground">
              <th className="w-8 px-3 py-2.5" />
              <SortHeader label="Founder" col="name" sort={sort} onSort={onSort} />
              <SortHeader
                label="Classification"
                col="classification"
                sort={sort}
                onSort={onSort}
              />
              <th className="px-2.5 py-2.5 font-medium">Domain</th>
              <SortHeader
                label="Score"
                col="founder_score"
                sort={sort}
                onSort={onSort}
              />
              <SortHeader
                label="Availability"
                col="available"
                sort={sort}
                onSort={onSort}
              />
              <th className="px-2.5 py-2.5 font-medium" />
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => {
              const isSel = selected.includes(f.id);
              return (
                <tr
                  key={f.id}
                  onClick={() => toggle(f.id)}
                  className={`cursor-pointer border-b border-border last:border-0 transition-colors ${
                    isSel ? "bg-violet-50/70" : "hover:bg-violet-50/30"
                  }`}
                >
                  <td className="px-3 py-3">
                    <span
                      className={`flex size-4 items-center justify-center rounded border ${
                        isSel
                          ? "border-violet-500 bg-violet-500 text-white"
                          : "border-border bg-background"
                      }`}
                    >
                      {isSel && <span className="text-[0.6rem] leading-none">✓</span>}
                    </span>
                  </td>
                  <td className="px-2.5 py-3">
                    <span className="flex items-center gap-1.5">
                      <Link
                        href={`/founders/${f.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="font-medium hover:text-violet-700 hover:underline"
                      >
                        {f.name}
                      </Link>
                      {f.returning && (
                        <span
                          title="Returning founder - track record across more than one company"
                          className="inline-flex items-center gap-0.5 rounded border border-indigo-200 bg-indigo-50 px-1 py-0.5 text-[0.65rem] font-medium text-indigo-700"
                        >
                          <History className="size-2.5" /> returning
                        </span>
                      )}
                    </span>
                    {f.github_handle && (
                      <div className="text-xs text-muted-foreground">
                        @{f.github_handle}
                      </div>
                    )}
                  </td>
                  <td className="px-2.5 py-3">
                    <ClassBadges f={f} />
                  </td>
                  <td className="px-2.5 py-3 text-xs text-muted-foreground">
                    {f.domain ?? "-"}
                  </td>
                  <td className="px-2.5 py-3 tabular-nums">
                    {f.founder_score != null ? (
                      f.founder_score.toFixed(1)
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </td>
                  <td className="px-2.5 py-3">
                    {f.available ? (
                      <span
                        title={f.availability}
                        className="inline-flex items-center rounded-md border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-xs font-medium text-emerald-700"
                      >
                        available
                      </span>
                    ) : (
                      <span
                        title={f.availability}
                        className="inline-flex items-center rounded-md border border-border bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground"
                      >
                        committed
                      </span>
                    )}
                  </td>
                  <td className="px-2.5 py-3 text-right">
                    <Button
                      variant="outline"
                      size="xs"
                      onClick={(e) => {
                        e.stopPropagation();
                        findMatches(f.id);
                      }}
                    >
                      <Search /> Find matches
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* suggestions from "find matches" */}
      {(suggestLoading || suggest) && (
        <section className="rounded-xl border border-violet-200 bg-violet-50/30 p-4">
          <div className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-violet-900">
            <Sparkles className="size-4 text-violet-500" />
            {suggest
              ? `Complementary founders for ${suggest.founder.name}`
              : "Finding complementary founders…"}
          </div>
          {suggest && (
            <p className="mb-3 text-xs text-muted-foreground">
              {suggest.needs.length > 0
                ? `Missing coverage: ${suggest.needs.join(", ")}. `
                : "Team coverage already broad. "}
              Available founders from Memory, ranked by fit. Pick one to render the
              hypothetical team.
            </p>
          )}
          {suggestLoading ? (
            <Spinner />
          ) : suggest && suggest.candidates.length > 0 ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {suggest.candidates.map((c) => (
                <SuggestionChip
                  key={c.founder_id}
                  c={c}
                  onPick={(id) => setSelected([suggest.founder.id, id])}
                />
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No available complementary founder found in Memory for this founder.
            </p>
          )}
        </section>
      )}

      {/* the hypothetical team card */}
      {matchLoading && <Spinner label="Assessing team…" />}
      {matchError && <p className="text-sm text-red-700">{matchError}</p>}
      {match && !matchLoading && <HypotheticalTeamCard match={match} />}
    </div>
  );
}

export function FoundersDatabase() {
  const state = useFetch(() => api.founders(), []);
  return (
    <div>
      <PageHeader
        title="Database"
        subtitle="Founder directory + hypothetical team matching - deterministic, no LLM."
      />
      <div className="px-8 py-6">
        <Async state={state}>{(founders) => <Directory founders={founders} />}</Async>
      </div>
    </div>
  );
}
