import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Trend } from "@/lib/types";

const META: Record<Trend, { icon: typeof Minus; className: string; label: string }> = {
  improving: { icon: ArrowUpRight, className: "text-emerald-600", label: "Improving" },
  declining: { icon: ArrowDownRight, className: "text-red-600", label: "Declining" },
  stable: { icon: Minus, className: "text-zinc-400", label: "Stable" },
};

export function TrendArrow({
  trend,
  className,
  withLabel = false,
}: {
  trend: Trend | null | undefined;
  className?: string;
  withLabel?: boolean;
}) {
  if (!trend) return null;
  const { icon: Icon, className: color, label } = META[trend];
  return (
    <span
      className={cn("inline-flex items-center gap-0.5", color, className)}
      title={label}
    >
      <Icon className="size-3.5" strokeWidth={2.5} />
      {withLabel && <span className="text-xs font-medium">{label}</span>}
    </span>
  );
}
