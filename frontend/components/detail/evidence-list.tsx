"use client";

import * as React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import type { Signal } from "@/lib/types";
import { relativeDate, signalSummary, sourceTint } from "@/lib/format";
import { cn } from "@/lib/utils";

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
                        sourceTint(sig.source),
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
