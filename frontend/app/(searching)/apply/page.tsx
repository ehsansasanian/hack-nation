"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Loader2, Upload } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";

function Field({
  label,
  optional,
  children,
}: {
  label: string;
  optional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">
        {label}
        {optional && <span className="ml-1 text-xs text-muted-foreground">optional</span>}
      </label>
      {children}
    </div>
  );
}

export default function ApplyPage() {
  const router = useRouter();
  const [form, setForm] = React.useState({
    company_name: "",
    founder_name: "",
    sector: "",
    stage: "",
    geography: "",
    one_liner: "",
    deck_text: "",
  });
  const [fileName, setFileName] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const set = (k: keyof typeof form, v: string) =>
    setForm((prev) => ({ ...prev, [k]: v }));

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const text = await file.text();
    set("deck_text", text);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.company_name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const app = await api.createApplication({
        company_name: form.company_name.trim(),
        deck_text: form.deck_text || undefined,
        founder_name: form.founder_name || undefined,
        sector: form.sector || undefined,
        stage: form.stage || undefined,
        geography: form.geography || undefined,
        one_liner: form.one_liner || undefined,
      });
      router.push(`/applications/${app.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit the application.");
      setSubmitting(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="New inbound application"
        subtitle="Submit a company and its deck - it enters the same funnel as sourced candidates."
      />
      <form onSubmit={submit} className="mx-auto max-w-2xl space-y-4 px-8 py-6">
        <Card className="space-y-5 p-5">
          <Field label="Company name">
            <Input
              value={form.company_name}
              onChange={(e) => set("company_name", e.target.value)}
              placeholder="e.g. TensorForge"
              autoFocus
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Founder name" optional>
              <Input
                value={form.founder_name}
                onChange={(e) => set("founder_name", e.target.value)}
                placeholder="e.g. Aria Voss"
              />
            </Field>
            <Field label="Sector" optional>
              <Input
                value={form.sector}
                onChange={(e) => set("sector", e.target.value)}
                placeholder="AI infra"
              />
            </Field>
            <Field label="Stage" optional>
              <Input
                value={form.stage}
                onChange={(e) => set("stage", e.target.value)}
                placeholder="pre-seed"
              />
            </Field>
            <Field label="Geography" optional>
              <Input
                value={form.geography}
                onChange={(e) => set("geography", e.target.value)}
                placeholder="Berlin"
              />
            </Field>
          </div>
          <Field label="One-liner" optional>
            <Input
              value={form.one_liner}
              onChange={(e) => set("one_liner", e.target.value)}
              placeholder="What the company does in one sentence"
            />
          </Field>
          <Field label="Deck text" optional>
            <Textarea
              value={form.deck_text}
              onChange={(e) => set("deck_text", e.target.value)}
              placeholder="Paste the pitch deck text here, or upload a .txt / .md file below."
              className="min-h-40"
            />
            <div className="flex items-center gap-2">
              <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-background px-2.5 py-1 text-xs font-medium hover:bg-muted">
                <Upload className="size-3.5" />
                Upload .txt / .md
                <input
                  type="file"
                  accept=".txt,.md,text/plain,text/markdown"
                  className="hidden"
                  onChange={onFile}
                />
              </label>
              {fileName && (
                <span className="text-xs text-muted-foreground">
                  {fileName} loaded ({form.deck_text.length} chars)
                </span>
              )}
            </div>
          </Field>
        </Card>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex items-center gap-3">
          <Button type="submit" size="lg" disabled={submitting || !form.company_name.trim()}>
            {submitting && <Loader2 className="size-4 animate-spin" />}
            Submit application
          </Button>
          <span className="text-xs text-muted-foreground">
            Analysis starts automatically - you will watch screening, scoring, diligence and the memo run live.
          </span>
        </div>
      </form>
    </div>
  );
}
