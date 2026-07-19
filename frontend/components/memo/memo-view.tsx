"use client";

import * as React from "react";
import Link from "next/link";
import { Ban, Printer } from "lucide-react";

import { api } from "@/lib/api";
import type { Claim, Trace, TrustLevel } from "@/lib/types";
import { Async, useFetch } from "@/components/async";
import { PageHeader } from "@/components/page-header";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TrustBadge } from "@/components/trust-badge";
import { TraceProvider, WhyButton } from "@/components/trace/trace-panel";
import { RecommendationBanner } from "./recommendation-banner";

async function loadMemo(id: string) {
  const [memo, app, trace] = await Promise.all([
    api.memo(id),
    api.application(id),
    api.trace(id).catch((): Trace | null => null),
  ]);
  return { memo, app, trace };
}

/** A "Not disclosed: a; b" line becomes a distinct, non-fabricated gap callout. */
function GapCallout({ text }: { text: string }) {
  const items = text
    .replace(/^not disclosed:\s*/i, "")
    .split(/;\s*/)
    .filter(Boolean);
  return (
    <div className="rounded-lg border border-dashed border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
      <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide">
        <Ban className="size-3.5" /> Not disclosed
      </div>
      <ul className="list-disc pl-5">
        {items.map((it, i) => (
          <li key={i}>{it}</li>
        ))}
      </ul>
    </div>
  );
}

/** A claim/figure line of the form "[verified] (revenue) $50k MRR" renders with its
 *  trust badge; any other bullet renders as plain text. Lets the Financials and Cap
 *  table sections show claimed figures with the same trust vocabulary as the rest. */
const TRUST_LINE_RE = /^\[(verified|consistent|unverified|contradicted)\]\s*(\([^)]*\)\s*)?(.*)$/i;

function Bullet({ text }: { text: string }) {
  const m = text.match(TRUST_LINE_RE);
  if (!m) return <>{text}</>;
  const level = m[1].toLowerCase() as TrustLevel;
  const rest = `${m[2] ?? ""}${m[3] ?? ""}`.trim();
  return (
    <span className="flex items-start justify-between gap-2">
      <span className="min-w-0">{rest}</span>
      <TrustBadge level={level} className="shrink-0" />
    </span>
  );
}

function Prose({ text }: { text: string }) {
  const lines = text.split("\n").map((l) => l.trim());
  const blocks: React.ReactNode[] = [];
  let bullets: string[] = [];

  const flush = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="list-disc space-y-1 pl-5">
          {bullets.map((b, i) => (
            <li key={i}>
              <Bullet text={b} />
            </li>
          ))}
        </ul>,
      );
      bullets = [];
    }
  };

  for (const line of lines) {
    if (!line) continue;
    if (/^not disclosed:/i.test(line)) {
      flush();
      blocks.push(<GapCallout key={`gap-${blocks.length}`} text={line} />);
    } else if (line.startsWith("- ")) {
      bullets.push(line.slice(2));
    } else {
      flush();
      blocks.push(
        <p key={`p-${blocks.length}`} className="leading-relaxed">
          {line}
        </p>,
      );
    }
  }
  flush();
  return <div className="space-y-2 text-sm text-foreground/90">{blocks}</div>;
}

// Data-dependent sections with nothing on file: kept visible (awareness) but
// de-emphasised to a slim muted row - never a big empty card.
const MUTED_SENTINELS = new Set([
  "Not disclosed at this stage.",
  "No mandate constraints configured.",
]);

function MutedSection({ title, text }: { title: string; text: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 rounded-lg border border-dashed border-border/70 bg-muted/30 px-4 py-2.5 text-sm">
      <span className="font-medium text-muted-foreground">{title}</span>
      <span className="text-muted-foreground/80">{text}</span>
    </div>
  );
}

const SWOT_KEYS = ["Strengths", "Weaknesses", "Opportunities", "Threats"] as const;

function Swot({ text }: { text: string }) {
  const map: Record<string, string[]> = {};
  // Match each quadrant label and capture everything up to the next label (or end),
  // so both the newline-separated (offline) and inline run-on (LLM) formats parse.
  const re =
    /(Strengths|Weaknesses|Opportunities|Threats)\s*:\s*([\s\S]*?)(?=(?:Strengths|Weaknesses|Opportunities|Threats)\s*:|$)/gi;
  for (const m of text.matchAll(re)) {
    const key = m[1][0].toUpperCase() + m[1].slice(1).toLowerCase();
    const val = m[2].trim().replace(/[.;]+\s*$/, "");
    map[key] = !val || /^none/i.test(val) ? [] : val.split(/;\s*/).filter(Boolean);
  }
  const tone: Record<string, string> = {
    Strengths: "text-emerald-700",
    Weaknesses: "text-amber-700",
    Opportunities: "text-sky-700",
    Threats: "text-red-700",
  };
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {SWOT_KEYS.map((k) => (
        <div key={k} className="rounded-lg border border-border p-3">
          <div className={`mb-1.5 text-xs font-semibold uppercase tracking-wide ${tone[k]}`}>
            {k}
          </div>
          {map[k]?.length ? (
            <ul className="list-disc space-y-1 pl-4 text-sm text-foreground/90">
              {map[k].map((it, i) => (
                <li key={i}>{it}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">None noted</p>
          )}
        </div>
      ))}
    </div>
  );
}

/** Traction section: keep the summary prose, then render structured claims with real trust badges. */
function Traction({ text, claims }: { text: string; claims: Claim[] }) {
  const summary = text.split("Claims & trust levels:")[0].trim();
  const kpis = claims.filter(
    (c) => c.category === "traction" || c.category === "revenue",
  );
  const shown = kpis.length ? kpis : claims;
  return (
    <div className="space-y-3">
      {summary && <Prose text={summary} />}
      <ul className="space-y-1.5">
        {shown.map((c) => (
          <li
            key={c.id}
            className="flex items-start justify-between gap-3 rounded-lg border border-border px-3 py-2 text-sm"
          >
            <span className="min-w-0">{c.text}</span>
            <span className="flex shrink-0 items-center gap-2">
              <TrustBadge level={c.trust_level} />
              <WhyButton kind="claim" refId={String(c.id)} className="print-hide" />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const FIT_TONE: Record<string, string> = {
  met: "border-emerald-200 bg-emerald-50 text-emerald-800",
  gap: "border-red-200 bg-red-50 text-red-800",
  unknown: "border-slate-200 bg-slate-50 text-slate-600",
};

/** Mandate fit: each configured constraint vs its realized value, met/gap/unknown. */
function MandateFit({ text }: { text: string }) {
  const rows = text
    .split("\n")
    .map((l) =>
      l.match(
        /^-\s*\[(met|gap|unknown)\]\s*(.*?)\s*-\s*mandate:\s*(.*?)\s*\|\s*realized:\s*(.*)$/i,
      ),
    )
    .filter((m): m is RegExpMatchArray => m !== null);
  if (!rows.length) return <Prose text={text} />;
  return (
    <ul className="space-y-1.5">
      {rows.map((m, i) => {
        const [, status, label, target, realized] = m;
        const tone = FIT_TONE[status.toLowerCase()] ?? FIT_TONE.unknown;
        return (
          <li
            key={i}
            className="flex items-start justify-between gap-3 rounded-lg border border-border px-3 py-2 text-sm"
          >
            <span className="min-w-0">
              <span className="font-medium">{label}</span>
              <span className="block text-xs text-muted-foreground">
                mandate: {target} · realized: {realized}
              </span>
            </span>
            <span
              className={`shrink-0 rounded-md border px-2 py-0.5 text-xs font-semibold uppercase ${tone}`}
            >
              {status}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function Section({
  title,
  text,
  claims,
}: {
  title: string;
  text: string;
  claims: Claim[];
}) {
  let body: React.ReactNode;
  if (title === "SWOT") body = <Swot text={text} />;
  else if (title.startsWith("Traction")) body = <Traction text={text} claims={claims} />;
  else if (title === "Mandate fit") body = <MandateFit text={text} />;
  else body = <Prose text={text} />;
  return (
    <Card className="p-5">
      <h2 className="mb-3 text-sm font-semibold tracking-tight">{title}</h2>
      {body}
    </Card>
  );
}

// The full VC memo checklist in fixed order (mirrors the backend's MEMO_SECTION_ORDER).
// The backend already emits sections in this order; this keeps the client robust and
// explicit, and any unexpected key falls through to the end.
const SECTION_ORDER = [
  "Company snapshot",
  "Investment hypotheses",
  "SWOT",
  "Team & history",
  "Problem & product",
  "Technology & defensibility",
  "Market sizing",
  "Competition",
  "Traction & KPIs",
  "Financials & round structure",
  "Cap table",
  "Due diligence log",
  "Exit perspective",
  "Bear case",
  "Mandate fit",
];

export function MemoView({ id }: { id: string }) {
  const state = useFetch(() => loadMemo(id), [id]);
  return (
    <Async state={state}>
      {({ memo, app, trace }) => {
        const titles = Object.keys(memo.sections);
        const ordered = [
          ...SECTION_ORDER.filter((t) => titles.includes(t)),
          ...titles.filter((t) => !SECTION_ORDER.includes(t)),
        ];
        return (
          <TraceProvider trace={trace}>
            <PageHeader
              title={
                <span className="flex items-center gap-2">
                  <Link
                    href={`/applications/${app.id}`}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    {app.company.name}
                  </Link>
                  <span className="text-muted-foreground">/</span>
                  Memo
                </span>
              }
              subtitle="Investment memo - every claim carries its trust level; gaps are flagged, not filled."
              actions={
                <span className="flex items-center gap-2 print-hide">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => window.print()}
                  >
                    <Printer /> Download PDF
                  </Button>
                  <Link
                    href={`/applications/${app.id}`}
                    className={buttonVariants({ variant: "outline", size: "sm" })}
                  >
                    Back to detail
                  </Link>
                </span>
              }
            />
            <div className="mx-auto max-w-3xl space-y-4 px-8 py-6">
              <RecommendationBanner recommendation={memo.recommendation} />
              {ordered.map((title) => {
                const text = memo.sections[title] ?? "";
                return MUTED_SENTINELS.has(text.trim()) ? (
                  <MutedSection key={title} title={title} text={text.trim()} />
                ) : (
                  <Section
                    key={title}
                    title={title}
                    text={text}
                    claims={app.claims}
                  />
                );
              })}
            </div>
          </TraceProvider>
        );
      }}
    </Async>
  );
}
