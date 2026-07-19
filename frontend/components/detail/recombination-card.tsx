"use client";

import * as React from "react";
import Link from "next/link";
import {
  FlaskConical,
  Lightbulb,
  RefreshCw,
  Sparkles,
  UserPlus,
} from "lucide-react";

import { api, ApiError } from "@/lib/api";
import type { Recombination, RecombinationCandidate } from "@/lib/types";
import { Button } from "@/components/ui/button";

// The card is deliberately styled apart from the rest of the page (violet, dashed)
// and every surface repeats the word "hypothetical" - a recombination note must
// never be mistaken for the application's real, unchanged assessment.

const FILL_TONE: Record<string, string> = {
  technical: "border-blue-200 bg-blue-50 text-blue-700",
  commercial: "border-emerald-200 bg-emerald-50 text-emerald-700",
  domain: "border-amber-200 bg-amber-50 text-amber-700",
};

function FillBadge({ fill }: { fill: string }) {
  const tone = FILL_TONE[fill] ?? "border-slate-200 bg-slate-50 text-slate-600";
  return (
    <span className={`rounded-md border px-1.5 py-0.5 text-xs font-medium ${tone}`}>
      {fill}
    </span>
  );
}

function CandidateRow({ c }: { c: RecombinationCandidate }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className="flex flex-wrap items-center gap-2">
        <UserPlus className="size-4 text-violet-500" />
        <Link
          href={`/founders/${c.founder_id}`}
          className="text-sm font-semibold hover:text-violet-700"
        >
          {c.name}
        </Link>
        {c.founder_score != null && (
          <span
            title="Persistent founder score"
            className="inline-flex items-center rounded-md border border-border bg-background px-1.5 py-0.5 text-xs tabular-nums text-muted-foreground"
          >
            score {c.founder_score.toFixed(1)}
          </span>
        )}
        {c.fills.map((f) => (
          <FillBadge key={f} fill={f} />
        ))}
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-foreground/80">{c.why}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        <span className="font-medium">Availability:</span> {c.availability}
      </p>
    </div>
  );
}

function Note({ note }: { note: Recombination }) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-dashed border-violet-300 bg-violet-50/70 px-3 py-2.5 text-sm text-violet-900">
        <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-violet-700">
          <FlaskConical className="size-3.5" /> Contingent IC note · hypothetical
        </div>
        <p className="leading-relaxed">{note.contingent_note}</p>
      </div>

      {note.candidates.length > 0 && (
        <div>
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
            <Sparkles className="size-3.5" /> Proposed complementary co-founders (from
            Memory)
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {note.candidates.map((c) => (
              <CandidateRow key={c.founder_id} c={c} />
            ))}
          </div>
        </div>
      )}

      {note.idea_pivots.length > 0 && (
        <div>
          <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
            <Lightbulb className="size-3.5" /> Idea pivots to validate
          </div>
          <ul className="list-disc space-y-1 pl-5 text-sm text-foreground/85">
            {note.idea_pivots.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Re-evaluate in {note.reeval_weeks} weeks · narrative by {note.backend}. These
        proposals are hypothetical - the three axis scores above are unchanged.
      </p>
    </div>
  );
}

export function RecombinationCard({ appId }: { appId: number }) {
  const [note, setNote] = React.useState<Recombination | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .recombination(appId)
      .then((r) => alive && setNote(r))
      .catch((e) => {
        // 404 just means "not generated yet" - not an error to surface.
        if (alive && !(e instanceof ApiError && e.status === 404)) {
          setError((e as Error).message);
        }
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [appId]);

  const generate = React.useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      // Chips/detail use the deterministic offline path (no LLM spend on the demo).
      setNote(await api.recombine(appId, "offline"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [appId]);

  if (loading) return null; // avoid a flash before we know if a note exists

  return (
    <section className="rounded-xl border border-violet-200 bg-violet-50/30 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-violet-900">
          <FlaskConical className="size-4 text-violet-500" />
          Recombination
          <span className="rounded-md border border-violet-300 bg-violet-100 px-1.5 py-0.5 text-xs font-medium text-violet-700">
            Hypothetical
          </span>
        </h2>
        {note ? (
          <Button variant="outline" size="sm" onClick={generate} disabled={busy}>
            <RefreshCw className={busy ? "animate-spin" : ""} /> Regenerate
          </Button>
        ) : (
          <Button variant="outline" size="sm" onClick={generate} disabled={busy}>
            <Sparkles /> {busy ? "Exploring…" : "Explore recombination"}
          </Button>
        )}
      </div>

      {!note && (
        <p className="text-sm text-muted-foreground">
          This application is below the bar as-is. Explore what would make it
          investible: complementary co-founders from Memory and idea pivots, with a
          clearly-labeled contingent IC note. This never changes the real scores.
        </p>
      )}

      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}

      {note && <Note note={note} />}
    </section>
  );
}
