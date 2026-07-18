"use client";

import * as React from "react";
import Link from "next/link";
import { Ban } from "lucide-react";

import { api } from "@/lib/api";
import type { Claim } from "@/lib/types";
import { Async, useFetch } from "@/components/async";
import { PageHeader } from "@/components/page-header";
import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TrustBadge } from "@/components/trust-badge";
import { RecommendationBanner } from "./recommendation-banner";

async function loadMemo(id: string) {
  const [memo, app] = await Promise.all([api.memo(id), api.application(id)]);
  return { memo, app };
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

function Prose({ text }: { text: string }) {
  const lines = text.split("\n").map((l) => l.trim());
  const blocks: React.ReactNode[] = [];
  let bullets: string[] = [];

  const flush = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="list-disc space-y-1 pl-5">
          {bullets.map((b, i) => (
            <li key={i}>{b}</li>
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

const SWOT_KEYS = ["Strengths", "Weaknesses", "Opportunities", "Threats"] as const;

function Swot({ text }: { text: string }) {
  const map: Record<string, string[]> = {};
  for (const line of text.split("\n")) {
    const m = line.match(/^(Strengths|Weaknesses|Opportunities|Threats):\s*(.*)$/);
    if (m) {
      const val = m[2].trim();
      map[m[1]] =
        !val || /^none/i.test(val) ? [] : val.split(/;\s*/).filter(Boolean);
    }
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
            <TrustBadge level={c.trust_level} className="shrink-0" />
          </li>
        ))}
      </ul>
    </div>
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
  else body = <Prose text={text} />;
  return (
    <Card className="p-5">
      <h2 className="mb-3 text-sm font-semibold tracking-tight">{title}</h2>
      {body}
    </Card>
  );
}

// Preferred section order per the memo spec (Appendix 1).
const SECTION_ORDER = [
  "Company snapshot",
  "Investment hypotheses",
  "Problem & product",
  "Traction & KPIs",
  "SWOT",
];

export function MemoView({ id }: { id: string }) {
  const state = useFetch(() => loadMemo(id), [id]);
  return (
    <Async state={state}>
      {({ memo, app }) => {
        const titles = Object.keys(memo.sections);
        const ordered = [
          ...SECTION_ORDER.filter((t) => titles.includes(t)),
          ...titles.filter((t) => !SECTION_ORDER.includes(t)),
        ];
        return (
          <div>
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
                <Link
                  href={`/applications/${app.id}`}
                  className={buttonVariants({ variant: "outline", size: "sm" })}
                >
                  Back to detail
                </Link>
              }
            />
            <div className="mx-auto max-w-3xl space-y-4 px-8 py-6">
              <RecommendationBanner recommendation={memo.recommendation} />
              {ordered.map((title) => (
                <Section
                  key={title}
                  title={title}
                  text={memo.sections[title]}
                  claims={app.claims}
                />
              ))}
            </div>
          </div>
        );
      }}
    </Async>
  );
}
