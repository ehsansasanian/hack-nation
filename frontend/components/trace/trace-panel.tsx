"use client";

// Phase 6 agentic traceability: a "Why?" affordance on every axis score and claim.
// One TraceProvider per detail/memo page holds the trace and renders a single
// slide-over sheet; a WhyButton anywhere inside opens it focused on one item and
// renders that item's chain: the exact signals it reasoned over -> the rationale
// that cited them -> the validator outcome -> where it landed in the memo.

import * as React from "react";
import {
  ArrowRight,
  FileSignature,
  Filter,
  HelpCircle,
  ListChecks,
  Radio,
  ScrollText,
  ShieldCheck,
  TriangleAlert,
  X,
} from "lucide-react";

import type { Trace, TraceSignal, TraceStep, TraceStepKind } from "@/lib/types";
import {
  AXIS_META,
  isValidatorWarning,
  relativeDate,
  sourceTint,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import { TrustBadge } from "@/components/trust-badge";

type Selection = { kind: "score" | "claim"; ref: string } | null;

const TraceCtx = React.createContext<{
  trace: Trace | null;
  select: (s: Selection) => void;
} | null>(null);

const KIND_ICON: Record<TraceStepKind, React.ComponentType<{ className?: string }>> = {
  signals: Radio,
  screening: Filter,
  score: ListChecks,
  claim: ScrollText,
  memo: FileSignature,
};

export function TraceProvider({
  trace,
  children,
}: {
  trace: Trace | null;
  children: React.ReactNode;
}) {
  const [selection, setSelection] = React.useState<Selection>(null);
  return (
    <TraceCtx.Provider value={{ trace, select: setSelection }}>
      {children}
      {trace && (
        <TraceSheet
          trace={trace}
          selection={selection}
          onClose={() => setSelection(null)}
          onSelect={setSelection}
        />
      )}
    </TraceCtx.Provider>
  );
}

/** A small "Why?" button that opens the trace sheet focused on one item. */
export function WhyButton({
  kind,
  refId,
  className,
}: {
  kind: "score" | "claim";
  refId: string;
  className?: string;
}) {
  const ctx = React.useContext(TraceCtx);
  if (!ctx?.trace) return null;
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        ctx.select({ kind, ref: refId });
      }}
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-border bg-background px-1.5 py-0.5 text-xs font-medium text-muted-foreground transition-colors hover:border-blue-300 hover:text-blue-700",
        className,
      )}
    >
      <HelpCircle className="size-3" />
      Why?
    </button>
  );
}

function stepFor(trace: Trace, selection: Exclude<Selection, null>): TraceStep | undefined {
  return trace.steps.find((s) => s.kind === selection.kind && s.ref === selection.ref);
}

function SignalRow({ sig, tag }: { sig: TraceSignal; tag?: string }) {
  return (
    <li className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 px-2.5 py-1.5 text-xs">
      <span
        className={cn(
          "shrink-0 rounded border px-1 py-0.5 font-medium uppercase",
          sourceTint(sig.source),
        )}
      >
        {sig.source}
      </span>
      <span className="min-w-0 flex-1 text-foreground">
        {tag && <span className="mr-1 font-medium text-muted-foreground">{tag}</span>}
        {sig.excerpt}
      </span>
      <span className="shrink-0 text-muted-foreground">{relativeDate(sig.timestamp)}</span>
    </li>
  );
}

function ChainStage({
  n,
  label,
  children,
}: {
  n: number;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-blue-100 text-[0.7rem] font-semibold text-blue-700">
          {n}
        </span>
        <span className="mt-1 w-px flex-1 bg-border" />
      </div>
      <div className="min-w-0 flex-1 pb-4">
        <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {label}
        </div>
        {children}
      </div>
    </div>
  );
}

/** The focused four-part chain for the selected score or claim. */
function FocusedChain({
  trace,
  step,
  sigMap,
}: {
  trace: Trace;
  step: TraceStep;
  sigMap: Map<number, TraceSignal>;
}) {
  const d = step.detail;
  const cited = step.signal_ids.map((id) => sigMap.get(id)).filter(Boolean) as TraceSignal[];
  const origin = step.source_signal_id != null ? sigMap.get(step.source_signal_id) : undefined;
  const validatorWarning = isValidatorWarning(d.validator_note);

  return (
    <div className="space-y-1">
      {/* header for the item */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {step.kind === "score" && d.axis && (
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-sm font-medium",
              AXIS_META[d.axis as keyof typeof AXIS_META]?.tint,
            )}
          >
            {AXIS_META[d.axis as keyof typeof AXIS_META]?.label}
            <span className="tabular-nums">{step.status}</span>
          </span>
        )}
        {step.kind === "claim" && (
          <>
            <TrustBadge level={d.trust_level ?? null} />
            {d.category && (
              <span className="rounded border border-border px-1.5 py-0.5 text-xs capitalize text-muted-foreground">
                {d.category}
              </span>
            )}
          </>
        )}
      </div>
      {step.kind === "claim" && (
        <p className="mb-3 text-sm font-medium text-foreground">&ldquo;{step.title}&rdquo;</p>
      )}

      {/* 1. signals */}
      <ChainStage n={1} label="Signals it reasoned over">
        <ul className="flex flex-col gap-1.5">
          {step.kind === "claim" && origin && (
            <SignalRow sig={origin} tag="extracted from" />
          )}
          {cited.length > 0 ? (
            cited.map((s) => (
              <SignalRow
                key={s.id}
                sig={s}
                tag={step.kind === "claim" ? "checked against" : undefined}
              />
            ))
          ) : (
            <li className="text-xs text-muted-foreground">
              {step.kind === "claim"
                ? "No corroborating or conflicting signal on file - left unverified rather than penalised."
                : "No external signals cited."}
            </li>
          )}
        </ul>
      </ChainStage>

      {/* 2. rationale */}
      <ChainStage n={2} label={step.kind === "score" ? "Scoring rationale" : "Truth-gap outcome"}>
        <p className="text-sm leading-relaxed text-foreground/90">
          {step.summary || "-"}
        </p>
      </ChainStage>

      {/* 3. validator */}
      <ChainStage n={3} label="Validator (self-correction)">
        {d.validator_note ? (
          <div
            className={cn(
              "flex items-start gap-1.5 rounded-lg border px-2.5 py-2 text-xs",
              validatorWarning
                ? "border-amber-200 bg-amber-50 text-amber-900"
                : "border-emerald-200 bg-emerald-50 text-emerald-800",
            )}
          >
            {validatorWarning ? (
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
            ) : (
              <ShieldCheck className="mt-0.5 size-3.5 shrink-0" />
            )}
            <span>{d.validator_note}</span>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            Left unchanged by the refutation pass.
          </p>
        )}
      </ChainStage>

      {/* 4. memo landing */}
      <div className="flex gap-3">
        <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-blue-100 text-[0.7rem] font-semibold text-blue-700">
          4
        </span>
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Where it lands in the memo
          </div>
          {d.memo_section ? (
            <div className="space-y-1 text-sm text-foreground/90">
              <p>
                Rendered in the{" "}
                <span className="font-medium">{d.memo_section}</span> section.
              </p>
              {step.kind === "score" && trace.memo_recommendation && (
                <p className="text-xs text-muted-foreground">
                  Cited in the recommendation: {trace.memo_recommendation}
                </p>
              )}
              {step.kind === "claim" && d.influenced_recommendation && (
                <p className="text-xs font-medium text-red-700">
                  This contradicted core claim drove the recommendation down.
                </p>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              No memo generated yet for this application.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/** The compact end-to-end chain, with the selected step highlighted. */
function FullChain({
  trace,
  active,
  onSelect,
}: {
  trace: Trace;
  active?: TraceStep;
  onSelect: (s: Selection) => void;
}) {
  return (
    <ol className="space-y-1">
      {trace.steps.map((s) => {
        const Icon = KIND_ICON[s.kind];
        const selectable = s.kind === "score" || s.kind === "claim";
        const isActive = active && s.kind === active.kind && s.ref === active.ref;
        return (
          <li key={`${s.kind}-${s.ref ?? s.index}`}>
            <button
              type="button"
              disabled={!selectable}
              onClick={() =>
                selectable && onSelect({ kind: s.kind as "score" | "claim", ref: s.ref! })
              }
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs",
                selectable && "hover:bg-muted",
                isActive && "bg-blue-50 ring-1 ring-blue-200",
                !selectable && "cursor-default",
              )}
            >
              <Icon className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate text-foreground">{s.title}</span>
              {s.status && (
                <span className="shrink-0 tabular-nums text-muted-foreground">{s.status}</span>
              )}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function TraceSheet({
  trace,
  selection,
  onClose,
  onSelect,
}: {
  trace: Trace;
  selection: Selection;
  onClose: () => void;
  onSelect: (s: Selection) => void;
}) {
  const open = selection !== null;

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open || !selection) return null;
  const step = stepFor(trace, selection);
  const sigMap = new Map(trace.signals.map((s) => [s.id, s]));

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0 bg-black/30 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden
      />
      <aside className="relative flex h-full w-full max-w-md flex-col border-l border-border bg-background shadow-xl">
        <header className="flex items-start justify-between gap-2 border-b border-border px-5 py-4">
          <div>
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <ArrowRight className="size-3.5" /> Reasoning trace
            </div>
            <h2 className="mt-0.5 text-sm font-semibold text-foreground">
              {trace.company.name}
            </h2>
            {trace.backend && (
              <p className="text-xs text-muted-foreground">via {trace.backend}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            <X className="size-4" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {step ? (
            <FocusedChain trace={trace} step={step} sigMap={sigMap} />
          ) : (
            <p className="text-sm text-muted-foreground">
              This item is not part of the recorded chain yet.
            </p>
          )}

          <div className="mt-4 border-t border-border pt-4">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Full chain
            </div>
            <FullChain trace={trace} active={step} onSelect={onSelect} />
          </div>
        </div>
      </aside>
    </div>
  );
}
