"use client";

import * as React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import type { Signal } from "@/lib/types";
import { relativeDate, signalSummary } from "@/lib/format";
import { cn } from "@/lib/utils";

const SOURCE_TINT: Record<string, string> = {
  github: "border-zinc-200 bg-zinc-50 text-zinc-700",
  hn: "border-orange-200 bg-orange-50 text-orange-700",
  arxiv: "border-red-200 bg-red-50 text-red-700",
  deck: "border-blue-200 bg-blue-50 text-blue-700",
  manual: "border-violet-200 bg-violet-50 text-violet-700",
  synthetic: "border-zinc-200 bg-zinc-50 text-zinc-600",
};

export function EvidenceList({
  ids,
  signalsById,
}: {
  ids: number[];
  signalsById: Map<number, Signal>;
}) {
  const [open, setOpen] = React.useState(false);
  if (ids.length === 0)
    return (
      <p className="text-xs text-muted-foreground">No evidence signals cited.</p>
    );

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        Evidence · {ids.length} signal{ids.length === 1 ? "" : "s"}
      </button>
      {open && (
        <ul className="mt-2 flex flex-col gap-1.5">
          {ids.map((id) => {
            const sig = signalsById.get(id);
            return (
              <li
                key={id}
                className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-2.5 py-1.5 text-xs"
              >
                {sig ? (
                  <>
                    <span
                      className={cn(
                        "shrink-0 rounded border px-1 py-0.5 font-medium uppercase",
                        SOURCE_TINT[sig.source] ?? SOURCE_TINT.synthetic,
                      )}
                    >
                      {sig.source}
                    </span>
                    <span className="min-w-0 flex-1 text-foreground">
                      {signalSummary(sig.content)}
                    </span>
                    <span className="shrink-0 text-muted-foreground">
                      {relativeDate(sig.timestamp)}
                    </span>
                  </>
                ) : (
                  <span className="text-muted-foreground">signal #{id}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
