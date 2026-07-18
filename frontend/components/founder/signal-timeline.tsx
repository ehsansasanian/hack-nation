import type { Signal } from "@/lib/types";
import { relativeDate, signalSummary, sourceTint } from "@/lib/format";
import { cn } from "@/lib/utils";

export function SignalTimeline({ signals }: { signals: Signal[] }) {
  if (signals.length === 0)
    return (
      <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
        No signals ingested for this founder yet.
      </p>
    );

  const groups = new Map<string, Signal[]>();
  for (const s of signals) {
    if (!groups.has(s.source)) groups.set(s.source, []);
    groups.get(s.source)!.push(s);
  }
  for (const list of groups.values())
    list.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

  return (
    <div className="space-y-5">
      {[...groups.entries()].map(([source, list]) => (
        <div key={source}>
          <div className="mb-2 flex items-center gap-2">
            <span
              className={cn(
                "rounded border px-1.5 py-0.5 text-xs font-medium uppercase",
                sourceTint(source),
              )}
            >
              {source}
            </span>
            <span className="text-xs text-muted-foreground">
              {list.length} signal{list.length === 1 ? "" : "s"}
            </span>
          </div>
          <ol className="relative ml-1 border-l border-border pl-4">
            {list.map((s) => (
              <li key={s.id} className="mb-3 last:mb-0">
                <span className="absolute -left-[5px] mt-1.5 size-2 rounded-full bg-blue-500" />
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm text-foreground/90">{signalSummary(s.content)}</p>
                  <time className="shrink-0 text-xs text-muted-foreground">
                    {relativeDate(s.timestamp)}
                  </time>
                </div>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  );
}
