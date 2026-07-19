"use client";

import { Clock, EyeOff, Radar, Sparkles, TrendingUp } from "lucide-react";

import type { Edge, EdgeLine } from "@/lib/types";

// The Edge panel answers "why might this be alpha an incumbent tool misses?" - and
// does it honestly: every line is derived from stored data and cites its own
// evidence, and the whole thing is strictly qualitative (no expected-return numbers,
// no fabricated percentages). Server-computed so it stays consistent and traceable.

const LINE_ICON: Record<string, typeof Sparkles> = {
  cold_start: EyeOff,
  outbound: Radar,
  momentum: TrendingUp,
  recency: Clock,
};

function EdgeRow({ line }: { line: EdgeLine }) {
  const Icon = LINE_ICON[line.key] ?? Sparkles;
  return (
    <div className="flex gap-2.5">
      <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md border border-emerald-200 bg-emerald-50 text-emerald-600">
        <Icon className="size-3.5" />
      </span>
      <div className="min-w-0">
        <div className="text-sm font-medium text-foreground">{line.label}</div>
        <p className="text-xs leading-relaxed text-foreground/75">{line.detail}</p>
        <p className="mt-0.5 text-[0.7rem] text-muted-foreground">
          <span className="font-medium">Evidence:</span>{" "}
          <span className="font-mono">{line.evidence}</span>
        </p>
      </div>
    </div>
  );
}

export function EdgePanel({ edge }: { edge: Edge }) {
  return (
    <section className="rounded-xl border border-emerald-200 bg-emerald-50/30 p-4">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-emerald-900">
          <Sparkles className="size-4 text-emerald-500" />
          Edge
          <span className="rounded-md border border-emerald-300 bg-emerald-100 px-1.5 py-0.5 text-xs font-medium text-emerald-700">
            alpha
          </span>
        </h2>
        <span className="text-xs text-muted-foreground">
          qualitative &amp; evidence-cited - no return estimates
        </span>
      </div>

      {edge.has_edge ? (
        <>
          <p className="mb-3 text-sm text-emerald-900/90">{edge.summary}</p>
          <div className="space-y-3">
            {edge.lines.map((l) => (
              <EdgeRow key={l.key} line={l} />
            ))}
          </div>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          No distinct edge over incumbent tools is derivable from the stored data for
          this application - shown honestly rather than invented.
        </p>
      )}
    </section>
  );
}
