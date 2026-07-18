"use client";

import * as React from "react";
import { Loader2, Search, X } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import type { QueryResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const EXAMPLES = [
  "technical founder, Berlin, AI infra, no prior VC backing",
  "fintech pre-seed with real traction",
  "cold-start health founder",
];

export function QueryBar({
  onResults,
  onClear,
  active,
}: {
  onResults: (r: QueryResponse) => void;
  onClear: () => void;
  active: boolean;
}) {
  const [q, setQ] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function run(query: string) {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.query(query);
      onResults(res);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Query failed. Is the backend running?",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
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
            placeholder="Ask the pipeline in plain English…"
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
              onClear();
            }}
          >
            <X /> Clear
          </Button>
        )}
      </form>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-muted-foreground">Try:</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => {
              setQ(ex);
              run(ex);
            }}
            className="rounded-full border border-border bg-muted/50 px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            {ex}
          </button>
        ))}
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
