import { ShieldCheck, TriangleAlert } from "lucide-react";

import type { Score, Signal } from "@/lib/types";
import { AXIS_META, isValidatorWarning, scoreDisplay } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { TrendArrow } from "@/components/trend-arrow";
import { WhyButton } from "@/components/trace/trace-panel";
import { EvidenceList } from "./evidence-list";

export function AxisCard({
  score,
  signalsById,
}: {
  score: Score;
  signalsById: Map<number, Signal>;
}) {
  const meta = AXIS_META[score.axis];
  const confidence = score.confidence != null ? Math.round(score.confidence * 100) : null;
  const warning = isValidatorWarning(score.validator_note);

  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {meta.label}
          </div>
          <div className="mt-1 flex items-center gap-2">
            <span
              className={cn(
                "inline-flex items-baseline gap-1 rounded-lg border px-2 py-1",
                meta.tint,
                score.cold_start && "border-dashed",
              )}
            >
              <span className="text-2xl font-semibold tabular-nums leading-none">
                {scoreDisplay(score)}
              </span>
              <span className="text-xs opacity-60">/10</span>
            </span>
            <TrendArrow trend={score.trend} withLabel />
          </div>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          {score.cold_start && (
            <span className="rounded-md border border-dashed border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[0.7rem] font-medium text-amber-800">
              cold-start range
            </span>
          )}
          <WhyButton kind="score" refId={score.axis} />
        </div>
      </div>

      {confidence != null && (
        <div>
          <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
            <span>Confidence</span>
            <span className="tabular-nums">{confidence}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className={cn(
                "h-full rounded-full",
                confidence >= 66
                  ? "bg-emerald-500"
                  : confidence >= 40
                    ? "bg-amber-500"
                    : "bg-red-400",
              )}
              style={{ width: `${confidence}%` }}
            />
          </div>
        </div>
      )}

      {score.rationale && (
        <p className="text-sm leading-relaxed text-foreground/90">{score.rationale}</p>
      )}

      {score.validator_note && (
        <div
          className={cn(
            "flex items-start gap-1.5 rounded-lg border px-2.5 py-2 text-xs",
            warning
              ? "border-amber-200 bg-amber-50 text-amber-900"
              : "border-emerald-200 bg-emerald-50 text-emerald-800",
          )}
        >
          {warning ? (
            <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          ) : (
            <ShieldCheck className="mt-0.5 size-3.5 shrink-0" />
          )}
          <span>
            <span className="font-medium">Validator:</span> {score.validator_note}
          </span>
        </div>
      )}

      <EvidenceList ids={score.evidence_signal_ids} signalsById={signalsById} />
    </Card>
  );
}
