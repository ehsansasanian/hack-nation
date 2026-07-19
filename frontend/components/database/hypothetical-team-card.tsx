"use client";

import Link from "next/link";
import {
  Check,
  FlaskConical,
  Handshake,
  TriangleAlert,
  User,
  X,
} from "lucide-react";

import type { FounderMatch, MatchFounder } from "@/lib/types";

// Reuses the recombination card's visual language (violet, dashed, and the word
// "hypothetical" repeated on every surface): a matched team is a what-if, never a
// change to either founder's persistent score or any real application assessment.

function ClassBadges({ f }: { f: MatchFounder }) {
  return (
    <span className="flex flex-wrap gap-1">
      {f.technical && (
        <span className="rounded-md border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[0.7rem] font-medium text-blue-700">
          technical
        </span>
      )}
      {f.commercial && (
        <span className="rounded-md border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[0.7rem] font-medium text-emerald-700">
          commercial
        </span>
      )}
      {!f.technical && !f.commercial && (
        <span className="rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[0.7rem] font-medium text-slate-500">
          unclassified
        </span>
      )}
    </span>
  );
}

function FounderPane({ f }: { f: MatchFounder }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="flex flex-wrap items-center gap-2">
        <User className="size-4 text-violet-500" />
        <Link
          href={`/founders/${f.id}`}
          className="text-sm font-semibold hover:text-violet-700"
        >
          {f.name}
        </Link>
        {f.founder_score != null && (
          <span
            title="Persistent founder score"
            className="inline-flex items-center rounded-md border border-border bg-background px-1.5 py-0.5 text-xs tabular-nums text-muted-foreground"
          >
            score {f.founder_score.toFixed(1)}
          </span>
        )}
      </div>
      <div className="mt-1.5">
        <ClassBadges f={f} />
      </div>
      {f.domain && (
        <p className="mt-1 text-xs text-muted-foreground">domain: {f.domain}</p>
      )}
      <p className="mt-1 text-[0.7rem] text-muted-foreground">
        {f.available ? "available" : "committed"} - {f.availability}
      </p>
    </div>
  );
}

function Coverage({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium ${
        ok
          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
          : "border-amber-200 bg-amber-50 text-amber-700"
      }`}
    >
      {ok ? <Check className="size-3" /> : <X className="size-3" />}
      {label}
    </span>
  );
}

export function HypotheticalTeamCard({ match }: { match: FounderMatch }) {
  return (
    <section className="rounded-xl border border-violet-200 bg-violet-50/30 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-violet-900">
          <FlaskConical className="size-4 text-violet-500" />
          Hypothetical team
          <span className="rounded-md border border-violet-300 bg-violet-100 px-1.5 py-0.5 text-xs font-medium text-violet-700">
            Hypothetical
          </span>
        </h2>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <FounderPane f={match.founder_a} />
        <FounderPane f={match.founder_b} />
      </div>

      <div className="mt-4 rounded-lg border border-dashed border-violet-300 bg-violet-50/70 px-3 py-2.5">
        <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-violet-700">
          <FlaskConical className="size-3.5" /> Complementarity verdict · hypothetical
        </div>
        <p className="text-sm font-medium text-violet-900">{match.verdict}</p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <Coverage ok={match.technical} label="technical covered" />
          <Coverage ok={match.commercial} label="commercial covered" />
          <span className="inline-flex items-center rounded-md border border-violet-200 bg-white px-1.5 py-0.5 text-xs font-medium tabular-nums text-violet-700">
            founder-axis lift {match.lift >= 0 ? "+" : ""}
            {match.lift.toFixed(2)}
          </span>
          {match.prior_collab && (
            <span className="inline-flex items-center gap-1 rounded-md border border-indigo-200 bg-indigo-50 px-1.5 py-0.5 text-xs font-medium text-indigo-700">
              <Handshake className="size-3" /> prior collaboration
            </span>
          )}
        </div>
      </div>

      {match.gaps.length > 0 && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2 text-xs text-amber-900">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          <span>
            <span className="font-medium">Remaining gaps:</span> {match.gaps.join("; ")}
          </span>
        </div>
      )}

      <p className="mt-3 text-sm leading-relaxed text-foreground/85">
        {match.rationale}
      </p>

      {match.patterns && (
        <p className="mt-2 text-xs text-muted-foreground">{match.patterns}</p>
      )}

      <p className="mt-3 text-xs text-muted-foreground">
        This pairing is hypothetical - it changes neither founder&apos;s persistent
        score nor any application&apos;s three-axis assessment.
      </p>
    </section>
  );
}
