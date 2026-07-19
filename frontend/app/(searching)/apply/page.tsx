"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  Trash2,
  Upload,
  UserPlus,
} from "lucide-react";

import { api, ApiError } from "@/lib/api";
import type { FounderLinkInput } from "@/lib/types";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";

function Field({
  label,
  optional,
  hint,
  children,
}: {
  label: string;
  optional?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">
        {label}
        {optional && <span className="ml-1 text-xs text-muted-foreground">optional</span>}
      </label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

interface FounderForm {
  name: string;
  role: string;
  github: string;
  linkedin: string;
  website: string;
  x: string;
  bio: string;
  linksOpen: boolean;
}

const emptyFounder = (linksOpen = false): FounderForm => ({
  name: "",
  role: "",
  github: "",
  linkedin: "",
  website: "",
  x: "",
  bio: "",
  linksOpen,
});

const ROLE_OPTIONS = ["CEO", "CTO", "COO", "CPO", "Co-founder", "Founder & Engineer"];

/** Build the API payload for one founder. The API accepts name + links +
 *  other_links only, so role/bio (no dedicated field) are folded into
 *  other_links as `role: ...` / `bio: ...` context strings. Returns null when
 *  the row is effectively empty. */
function toPayload(f: FounderForm): FounderLinkInput | null {
  const name = f.name.trim();
  const github = f.github.trim();
  const linkedin = f.linkedin.trim();
  const website = f.website.trim();
  const x = f.x.trim();
  const role = f.role.trim();
  const bio = f.bio.trim();

  const other_links: string[] = [];
  if (role) other_links.push(`role: ${role}`);
  if (bio) other_links.push(`bio: ${bio}`);

  const hasAnything =
    name || github || linkedin || website || x || other_links.length > 0;
  if (!hasAnything) return null;

  return {
    name: name || undefined,
    github: github || undefined,
    linkedin: linkedin || undefined,
    website: website || undefined,
    x: x || undefined,
    other_links: other_links.length ? other_links : undefined,
  };
}

function FounderEntry({
  index,
  founder,
  onChange,
  onRemove,
}: {
  index: number;
  founder: FounderForm;
  onChange: (patch: Partial<FounderForm>) => void;
  onRemove: (() => void) | null;
}) {
  const primary = index === 0;
  const Chevron = founder.linksOpen ? ChevronDown : ChevronRight;
  const linkCount = [founder.github, founder.linkedin, founder.website, founder.x].filter(
    (v) => v.trim(),
  ).length;

  return (
    <div className="space-y-3 rounded-xl border border-border bg-background p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {primary ? "Primary founder" : `Co-founder ${index}`}
        </span>
        {onRemove && (
          <Button type="button" variant="ghost" size="xs" onClick={onRemove}>
            <Trash2 />
            Remove
          </Button>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={primary ? "Name" : "Name"} optional={!primary}>
          <Input
            value={founder.name}
            onChange={(e) => onChange({ name: e.target.value })}
            placeholder="e.g. Aria Voss"
            autoFocus={primary}
          />
        </Field>
        <Field label="Role" optional>
          <Input
            list="founder-roles"
            value={founder.role}
            onChange={(e) => onChange({ role: e.target.value })}
            placeholder="e.g. CEO / CTO"
          />
        </Field>
      </div>

      <button
        type="button"
        onClick={() => onChange({ linksOpen: !founder.linksOpen })}
        className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        <Chevron className="size-3.5" />
        Links &amp; bio
        {linkCount > 0 && !founder.linksOpen && (
          <span className="text-muted-foreground">
            · {linkCount} link{linkCount === 1 ? "" : "s"}
          </span>
        )}
      </button>

      {founder.linksOpen && (
        <div className="space-y-3 border-t border-border pt-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="GitHub handle" optional>
              <Input
                value={founder.github}
                onChange={(e) => onChange({ github: e.target.value })}
                placeholder="octocat"
              />
            </Field>
            <Field label="LinkedIn URL" optional>
              <Input
                value={founder.linkedin}
                onChange={(e) => onChange({ linkedin: e.target.value })}
                placeholder="linkedin.com/in/…"
              />
            </Field>
            <Field label="Website / blog" optional>
              <Input
                value={founder.website}
                onChange={(e) => onChange({ website: e.target.value })}
                placeholder="yoursite.com"
              />
            </Field>
            <Field label="X handle" optional>
              <Input
                value={founder.x}
                onChange={(e) => onChange({ x: e.target.value })}
                placeholder="@handle"
              />
            </Field>
          </div>
          <Field label="Short bio" optional>
            <Textarea
              value={founder.bio}
              onChange={(e) => onChange({ bio: e.target.value })}
              placeholder="One or two lines on background and what they build."
              className="min-h-16"
            />
          </Field>
        </div>
      )}
    </div>
  );
}

export default function ApplyPage() {
  const router = useRouter();
  const [company, setCompany] = React.useState({
    company_name: "",
    sector: "",
    stage: "",
    geography: "",
    one_liner: "",
    deck_text: "",
  });
  const [founders, setFounders] = React.useState<FounderForm[]>([emptyFounder(true)]);
  const [fileName, setFileName] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const setC = (k: keyof typeof company, v: string) =>
    setCompany((prev) => ({ ...prev, [k]: v }));

  const patchFounder = (i: number, patch: Partial<FounderForm>) =>
    setFounders((prev) => prev.map((f, idx) => (idx === i ? { ...f, ...patch } : f)));

  const addFounder = () => setFounders((prev) => [...prev, emptyFounder(true)]);
  const removeFounder = (i: number) =>
    setFounders((prev) => prev.filter((_, idx) => idx !== i));

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const text = await file.text();
    setC("deck_text", text);
  }

  const canSubmit = company.company_name.trim() && founders[0]?.name.trim();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    const payloadFounders = founders
      .map(toPayload)
      .filter((f): f is FounderLinkInput => f !== null);
    try {
      const app = await api.createApplication({
        company_name: company.company_name.trim(),
        deck_text: company.deck_text || undefined,
        sector: company.sector || undefined,
        stage: company.stage || undefined,
        geography: company.geography || undefined,
        one_liner: company.one_liner || undefined,
        founders: payloadFounders,
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
        subtitle="Submit a company and its team - it enters the same funnel as sourced candidates."
      />
      <datalist id="founder-roles">
        {ROLE_OPTIONS.map((r) => (
          <option key={r} value={r} />
        ))}
      </datalist>
      <form onSubmit={submit} className="mx-auto max-w-2xl space-y-4 px-8 py-6">
        <Card className="space-y-5 p-5">
          <Field label="Company name">
            <Input
              value={company.company_name}
              onChange={(e) => setC("company_name", e.target.value)}
              placeholder="e.g. TensorForge"
              autoFocus
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Sector" optional>
              <Input
                value={company.sector}
                onChange={(e) => setC("sector", e.target.value)}
                placeholder="AI infra"
              />
            </Field>
            <Field label="Stage" optional>
              <Input
                value={company.stage}
                onChange={(e) => setC("stage", e.target.value)}
                placeholder="pre-seed"
              />
            </Field>
            <Field label="Geography" optional>
              <Input
                value={company.geography}
                onChange={(e) => setC("geography", e.target.value)}
                placeholder="Berlin"
              />
            </Field>
            <Field label="One-liner" optional>
              <Input
                value={company.one_liner}
                onChange={(e) => setC("one_liner", e.target.value)}
                placeholder="What the company does in one sentence"
              />
            </Field>
          </div>
          <Field label="Deck text" optional>
            <Textarea
              value={company.deck_text}
              onChange={(e) => setC("deck_text", e.target.value)}
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
                  {fileName} loaded ({company.deck_text.length} chars)
                </span>
              )}
            </div>
          </Field>
        </Card>

        <Card className="space-y-4 p-5">
          <div>
            <h2 className="text-sm font-semibold">Founding team</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Add every co-founder - teams get funded, not just ideas. Links are
              fetched and used as evidence; auth-walled sources (LinkedIn, X) are
              stored as self-declared references, never fabricated. Missing links
              never count against a founder.
            </p>
          </div>

          <div className="space-y-3">
            {founders.map((f, i) => (
              <FounderEntry
                key={i}
                index={i}
                founder={f}
                onChange={(patch) => patchFounder(i, patch)}
                onRemove={i > 0 ? () => removeFounder(i) : null}
              />
            ))}
          </div>

          <Button type="button" variant="outline" size="sm" onClick={addFounder}>
            <UserPlus />
            Add co-founder
          </Button>
        </Card>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex items-center gap-3">
          <Button type="submit" size="lg" disabled={submitting || !canSubmit}>
            {submitting && <Loader2 className="size-4 animate-spin" />}
            Submit application
          </Button>
          <span className="text-xs text-muted-foreground">
            Analysis starts automatically - you will watch enrichment, screening,
            scoring, diligence and the memo run live.
          </span>
        </div>
      </form>
    </div>
  );
}
