import { CircleCheck, CircleHelp, CircleX } from "lucide-react";

import { parseRecommendation, RECOMMENDATION_STYLE } from "@/lib/format";
import type { Recommendation } from "@/lib/format";
import { cn } from "@/lib/utils";

const ICON: Record<Recommendation, typeof CircleCheck> = {
  invest: CircleCheck,
  pass: CircleX,
  "need-more-info": CircleHelp,
  unknown: CircleHelp,
};

export function RecommendationBanner({ recommendation }: { recommendation: string | null }) {
  const { kind, headline, detail } = parseRecommendation(recommendation);
  const Icon = ICON[kind];
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-xl border px-5 py-4",
        RECOMMENDATION_STYLE[kind],
      )}
    >
      <Icon className="mt-0.5 size-6 shrink-0" />
      <div>
        <div className="text-[0.7rem] font-medium uppercase tracking-wide opacity-70">
          Recommendation
        </div>
        <div className="text-lg font-semibold">{headline}</div>
        {detail && <p className="mt-1 text-sm opacity-90">{detail}</p>}
      </div>
    </div>
  );
}
