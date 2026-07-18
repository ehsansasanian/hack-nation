"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, ShieldAlert } from "lucide-react";

import type { Application } from "@/lib/types";
import { AXIS_META, AXIS_ORDER, orderedScores } from "@/lib/format";
import { cn } from "@/lib/utils";
import { AxisChip } from "@/components/axis-chip";
import { OriginBadge } from "@/components/origin-badge";

export interface TrustSummary {
  contradicted: number;
  verified: number;
  total: number;
}

export interface PipelineRow {
  app: Application;
  trust?: TrustSummary;
}

function TrustCell({ row }: { row: PipelineRow }) {
  const t = row.trust;
  if (!t || t.total === 0)
    return <span className="text-xs text-muted-foreground">-</span>;
  if (t.contradicted > 0)
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-red-50 px-1.5 py-0.5 text-xs font-medium text-red-700">
        <ShieldAlert className="size-3" />
        {t.contradicted} contradicted
      </span>
    );
  if (t.verified > 0)
    return (
      <span className="inline-flex items-center gap-1 text-xs text-emerald-700">
        <Check className="size-3" />
        {t.verified} verified
      </span>
    );
  return <span className="text-xs text-muted-foreground">{t.total} claims</span>;
}

function FitCell({ app }: { app: Application }) {
  if (app.status === "screened_out")
    return (
      <span
        className="inline-flex items-center gap-1 rounded-md border border-red-200 bg-red-50 px-1.5 py-0.5 text-xs font-medium text-red-700"
        title={app.screening_rationale ?? "Screened out"}
      >
        Screened out
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 text-xs text-emerald-700">
      <Check className="size-3" /> In thesis
    </span>
  );
}

export function PipelineTable({ rows }: { rows: PipelineRow[] }) {
  const router = useRouter();
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full min-w-[820px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/40 text-left text-xs font-medium whitespace-nowrap text-muted-foreground">
            <th className="px-4 py-2.5 font-medium">Company</th>
            {AXIS_ORDER.map((a) => (
              <th key={a} className="px-2.5 py-2.5 font-medium">
                {a === "idea_vs_market" ? "Idea vs Mkt" : AXIS_META[a].label}
              </th>
            ))}
            <th className="px-2.5 py-2.5 font-medium">Trust</th>
            <th className="px-2.5 py-2.5 font-medium">Origin</th>
            <th className="px-2.5 py-2.5 font-medium">Fit</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ app, trust }) => {
            const scores = orderedScores(app.scores);
            const screened = app.status === "screened_out";
            return (
              <tr
                key={app.id}
                onClick={() => router.push(`/applications/${app.id}`)}
                className={cn(
                  "cursor-pointer border-b border-border last:border-0 transition-colors hover:bg-blue-50/40",
                  screened && "opacity-70",
                )}
              >
                <td className="px-4 py-3">
                  <Link
                    href={`/applications/${app.id}`}
                    onClick={(e) => e.stopPropagation()}
                    className="font-medium hover:text-blue-700 hover:underline"
                  >
                    {app.company.name}
                  </Link>
                  <div className="mt-0.5 max-w-[240px] truncate text-xs text-muted-foreground">
                    {app.company.one_liner ??
                      [app.company.sector, app.company.stage, app.company.geography]
                        .filter(Boolean)
                        .join(" · ")}
                  </div>
                </td>
                {AXIS_ORDER.map((axis) => {
                  const s = scores.find((x) => x.axis === axis);
                  return (
                    <td key={axis} className="px-2.5 py-3">
                      {s ? (
                        <AxisChip score={s} />
                      ) : (
                        <span className="text-xs text-muted-foreground">-</span>
                      )}
                    </td>
                  );
                })}
                <td className="px-2.5 py-3">
                  <TrustCell row={{ app, trust }} />
                </td>
                <td className="px-2.5 py-3">
                  <OriginBadge origin={app.origin} />
                </td>
                <td className="px-2.5 py-3">
                  <FitCell app={app} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
