import { cn } from "@/lib/utils";
import type { TrustLevel } from "@/lib/types";
import { TRUST_META } from "@/lib/format";

export function TrustBadge({
  level,
  className,
}: {
  level: TrustLevel | null | undefined;
  className?: string;
}) {
  if (!level) return null;
  const meta = TRUST_META[level];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium",
        meta.badge,
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", meta.dot)} />
      {meta.label}
    </span>
  );
}
