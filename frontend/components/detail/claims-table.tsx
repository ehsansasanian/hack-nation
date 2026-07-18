"use client";

import * as React from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import type { Claim } from "@/lib/types";
import { cn } from "@/lib/utils";
import { TrustBadge } from "@/components/trust-badge";
import { WhyButton } from "@/components/trace/trace-panel";
import { Badge } from "@/components/ui/badge";

export function ClaimsTable({ claims }: { claims: Claim[] }) {
  const [open, setOpen] = React.useState<Set<number>>(new Set());

  if (claims.length === 0)
    return (
      <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
        No claims extracted yet.
      </p>
    );

  function toggle(id: number) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/40 text-left text-xs font-medium text-muted-foreground">
            <th className="w-8 px-2 py-2.5" />
            <th className="px-3 py-2.5 font-medium">Claim</th>
            <th className="px-3 py-2.5 font-medium">Category</th>
            <th className="px-3 py-2.5 font-medium">Trust</th>
          </tr>
        </thead>
        <tbody>
          {claims.map((c) => {
            const note = c.contradiction_note || c.validator_note;
            const expandable = Boolean(note);
            const isOpen = open.has(c.id);
            const contradicted = c.trust_level === "contradicted";
            return (
              <React.Fragment key={c.id}>
                <tr
                  className={cn(
                    "border-b border-border last:border-0",
                    expandable && "cursor-pointer hover:bg-muted/30",
                    contradicted && "bg-red-50/40",
                  )}
                  onClick={() => expandable && toggle(c.id)}
                >
                  <td className="px-2 py-2.5 align-top text-muted-foreground">
                    {expandable &&
                      (isOpen ? (
                        <ChevronDown className="size-4" />
                      ) : (
                        <ChevronRight className="size-4" />
                      ))}
                  </td>
                  <td className="px-3 py-2.5 align-top">{c.text}</td>
                  <td className="px-3 py-2.5 align-top">
                    {c.category && (
                      <Badge variant="muted" className="font-normal capitalize">
                        {c.category}
                      </Badge>
                    )}
                  </td>
                  <td className="px-3 py-2.5 align-top">
                    <div className="flex items-center gap-2">
                      <TrustBadge level={c.trust_level} />
                      <WhyButton kind="claim" refId={String(c.id)} />
                    </div>
                  </td>
                </tr>
                {expandable && isOpen && (
                  <tr className="border-b border-border last:border-0 bg-muted/20">
                    <td />
                    <td colSpan={3} className="px-3 pb-3 pt-0">
                      {c.contradiction_note && (
                        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900">
                          <span className="font-semibold">Contradiction: </span>
                          {c.contradiction_note}
                        </div>
                      )}
                      {c.validator_note && (
                        <div className="mt-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                          <span className="font-semibold">Validator: </span>
                          {c.validator_note}
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
