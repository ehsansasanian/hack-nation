"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { CircleCheck, Loader2 } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import type { Thesis } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Async, useFetch } from "@/components/async";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { TagInput } from "@/components/ui/tag-input";

const DEFAULT_THESIS: Thesis = {
  id: 0,
  name: "New thesis",
  sectors: [],
  stages: [],
  geographies: [],
  check_size: null,
  ownership_target: null,
  risk_appetite: "medium",
  active: true,
};

async function loadThesis(): Promise<Thesis> {
  try {
    return await api.thesis();
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return DEFAULT_THESIS;
    throw e;
  }
}

const SECTORS = ["AI infra", "devtools", "fintech", "health", "SaaS", "security", "robotics"];
const STAGES = ["pre-seed", "seed", "series-a"];
const GEOS = ["Europe", "US", "Berlin", "London", "San Francisco", "remote"];
const RISK = ["low", "medium", "high"] as const;

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">{label}</label>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {children}
    </div>
  );
}

function ThesisForm({ initial }: { initial: Thesis }) {
  const router = useRouter();
  const [t, setT] = React.useState(initial);
  const [saving, setSaving] = React.useState(false);
  const [saved, setSaved] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const set = <K extends keyof Thesis>(k: K, v: Thesis[K]) =>
    setT((prev) => ({ ...prev, [k]: v }));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.updateThesis({
        name: t.name,
        sectors: t.sectors,
        stages: t.stages,
        geographies: t.geographies,
        check_size: t.check_size,
        ownership_target: t.ownership_target,
        risk_appetite: t.risk_appetite,
        active: true,
      });
      setSaved(true);
      setTimeout(() => router.push("/"), 1400);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the thesis.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="mx-auto max-w-2xl space-y-4 px-8 py-6">
      {saved && (
        <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <CircleCheck className="size-4" />
          Thesis saved. Re-run scoring (CLI or per-application) to re-rank the pipeline
          against it. Redirecting…
        </div>
      )}
      <Card className="space-y-5 p-5">
        <Field label="Thesis name">
          <Input value={t.name} onChange={(e) => set("name", e.target.value)} />
        </Field>
        <Field
          label="Sectors"
          hint="Hard filter - companies outside these sectors are screened out."
        >
          <TagInput
            values={t.sectors}
            onChange={(v) => set("sectors", v)}
            placeholder="Add a sector and press Enter"
            suggestions={SECTORS}
          />
        </Field>
        <Field label="Stages">
          <TagInput
            values={t.stages}
            onChange={(v) => set("stages", v)}
            placeholder="e.g. pre-seed"
            suggestions={STAGES}
          />
        </Field>
        <Field label="Geographies" hint="Leave empty for no geographic restriction (any).">
          <TagInput
            values={t.geographies}
            onChange={(v) => set("geographies", v)}
            placeholder="Add a geography (optional)"
            suggestions={GEOS}
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Check size">
            <Input
              value={t.check_size ?? ""}
              onChange={(e) => set("check_size", e.target.value || null)}
              placeholder="$100K"
            />
          </Field>
          <Field label="Ownership target">
            <Input
              value={t.ownership_target ?? ""}
              onChange={(e) => set("ownership_target", e.target.value || null)}
              placeholder="7-10%"
            />
          </Field>
        </div>
        <Field label="Risk appetite">
          <div className="inline-flex rounded-lg border border-border p-0.5">
            {RISK.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => set("risk_appetite", r)}
                className={cn(
                  "rounded-md px-3 py-1 text-sm font-medium capitalize transition-colors",
                  t.risk_appetite === r
                    ? "bg-blue-600 text-white"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {r}
              </button>
            ))}
          </div>
        </Field>
      </Card>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex items-center gap-3">
        <Button type="submit" size="lg" disabled={saving || saved}>
          {saving && <Loader2 className="size-4 animate-spin" />}
          Save thesis
        </Button>
        <span className="text-xs text-muted-foreground">
          Saving stores the active thesis; scoring re-runs pick it up.
        </span>
      </div>
    </form>
  );
}

export default function ThesisPage() {
  const state = useFetch(loadThesis, []);
  return (
    <div>
      <PageHeader
        title="Investment thesis"
        subtitle="The hard filter and scoring lens for every application - inbound and outbound."
      />
      <Async state={state}>{(thesis) => <ThesisForm initial={thesis} />}</Async>
    </div>
  );
}
