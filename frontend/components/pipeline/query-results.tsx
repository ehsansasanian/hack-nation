import Link from "next/link";

import type { QueryResponse } from "@/lib/types";
import { AXIS_META, AXIS_ORDER } from "@/lib/format";
import type { Axis } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

export function QueryResults({ data }: { data: QueryResponse }) {
  const { parsed, results, backend } = data;
  const parsedChips = [
    parsed.sector && `sector: ${parsed.sector}`,
    parsed.geography && `geo: ${parsed.geography}`,
    parsed.stage && `stage: ${parsed.stage}`,
    ...parsed.attributes.map((a) => a),
  ].filter(Boolean) as string[];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">
          {results.length} match{results.length === 1 ? "" : "es"}
        </span>
        <span className="text-muted-foreground">for</span>
        <span className="font-mono text-xs">&ldquo;{data.query}&rdquo;</span>
        <span className="ml-auto text-xs text-muted-foreground">
          parsed via {backend}
        </span>
      </div>
      {parsedChips.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Understood as:</span>
          {parsedChips.map((c) => (
            <Badge key={c} variant="muted" className="font-normal">
              {c}
            </Badge>
          ))}
        </div>
      )}
      <ol className="flex flex-col gap-2">
        {results.map((m, i) => (
          <li key={m.application_id}>
            <Link
              href={`/applications/${m.application_id}`}
              className="flex items-start gap-3 rounded-xl border border-border bg-card p-4 transition-colors hover:border-blue-300 hover:bg-blue-50/30"
            >
              <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md bg-muted text-xs font-semibold text-muted-foreground tabular-nums">
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{m.company}</span>
                  {m.partial && (
                    <Badge variant="outline" className="text-amber-700">
                      partial match
                    </Badge>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {[m.sector, m.stage, m.geography].filter(Boolean).join(" · ")}
                  </span>
                  <span className="ml-auto text-sm font-semibold tabular-nums text-blue-700">
                    {m.match_score.toFixed(1)}
                  </span>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{m.rationale}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {AXIS_ORDER.filter((a) => m.scores[a] != null).map((a: Axis) => (
                    <span
                      key={a}
                      className={cn(
                        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs",
                        AXIS_META[a].tint,
                      )}
                    >
                      <span className="font-semibold uppercase opacity-70">
                        {AXIS_META[a].short}
                      </span>
                      <span className="font-semibold tabular-nums">
                        {m.scores[a].toFixed(1)}
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            </Link>
          </li>
        ))}
        {results.length === 0 && (
          <li className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            No applications matched this query.
          </li>
        )}
      </ol>
    </div>
  );
}
