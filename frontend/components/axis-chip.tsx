import { cn } from "@/lib/utils";
import type { Score } from "@/lib/types";
import { AXIS_META, scoreDisplay } from "@/lib/format";
import { TrendArrow } from "./trend-arrow";

/**
 * One axis score rendered as a self-contained tinted chip. Scores are never
 * merged: each axis gets its own chip. Cold-start scores show a range and a
 * dashed border to signal wider uncertainty.
 */
export function AxisChip({
  score,
  showLabel = false,
  showTrend = true,
  className,
}: {
  score: Score;
  showLabel?: boolean;
  showTrend?: boolean;
  className?: string;
}) {
  const meta = AXIS_META[score.axis];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-sm leading-none",
        meta.tint,
        score.cold_start && "border-dashed",
        className,
      )}
      title={
        score.cold_start
          ? `${meta.label}: cold-start range (low evidence, wider uncertainty)`
          : `${meta.label} score`
      }
    >
      <span className="text-[0.65rem] font-semibold uppercase tracking-wide opacity-70">
        {showLabel ? meta.label : meta.short}
      </span>
      <span className="font-semibold tabular-nums">{scoreDisplay(score)}</span>
      {showTrend && <TrendArrow trend={score.trend} />}
    </span>
  );
}
