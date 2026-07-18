import { ArrowDownToLine, Radar } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Origin } from "@/lib/types";

export function OriginBadge({
  origin,
  className,
}: {
  origin: Origin;
  className?: string;
}) {
  const inbound = origin === "inbound";
  const Icon = inbound ? ArrowDownToLine : Radar;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium",
        inbound
          ? "border-zinc-200 bg-zinc-50 text-zinc-600"
          : "border-blue-200 bg-blue-50 text-blue-700",
        className,
      )}
      title={inbound ? "Inbound application" : "Sourced outbound"}
    >
      <Icon className="size-3" />
      {inbound ? "Inbound" : "Outbound"}
    </span>
  );
}
