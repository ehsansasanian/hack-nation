"use client";

import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { api } from "@/lib/api";
import { Async, useFetch } from "@/components/async";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScoreChart } from "./score-chart";
import { SignalTimeline } from "./signal-timeline";

const LINK_LABELS: Record<string, string> = {
  github: "GitHub",
  linkedin: "LinkedIn",
  twitter: "Twitter",
};

export function FounderProfile({ id }: { id: string }) {
  const state = useFetch(() => api.founder(id), [id]);
  return (
    <Async state={state}>
      {(f) => (
        <div>
          <PageHeader
            title={
              <span className="flex items-center gap-2">
                <Link href="/pipeline" className="text-muted-foreground hover:text-foreground">
                  Pipeline
                </Link>
                <span className="text-muted-foreground">/</span>
                {f.name}
              </span>
            }
            subtitle={f.bio ?? undefined}
          />
          <div className="space-y-6 px-8 py-6">
            {/* header row: score + links + companies */}
            <div className="flex flex-wrap items-stretch gap-4">
              <Card className="flex min-w-[180px] flex-col justify-center px-5 py-4">
                <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Founder score
                </span>
                <span className="mt-1 text-4xl font-semibold tabular-nums text-blue-700">
                  {f.founder_score != null ? f.founder_score.toFixed(1) : "-"}
                </span>
                <span className="text-xs text-muted-foreground">
                  persistent · never resets
                </span>
              </Card>
              <Card className="flex flex-1 flex-col justify-center gap-3 px-5 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  {f.github_handle && (
                    <Badge variant="outline">@{f.github_handle}</Badge>
                  )}
                  {Object.entries(f.links).map(([k, url]) => (
                    <a
                      key={k}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-xs font-medium text-blue-700 hover:bg-blue-50"
                    >
                      {LINK_LABELS[k] ?? k}
                      <ExternalLink className="size-3" />
                    </a>
                  ))}
                </div>
                {f.companies.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-xs text-muted-foreground">Companies:</span>
                    {f.companies.map((c) => (
                      <Badge key={c.id} variant="muted">
                        {c.name}
                      </Badge>
                    ))}
                  </div>
                )}
              </Card>
            </div>

            <section>
              <h2 className="mb-3 text-sm font-semibold text-muted-foreground">
                Founder score history
                <span className="ml-2 font-normal">across companies and scoring runs</span>
              </h2>
              <Card className="p-5">
                <ScoreChart history={f.score_history} />
              </Card>
            </section>

            <section>
              <h2 className="mb-3 text-sm font-semibold text-muted-foreground">
                Signal timeline
              </h2>
              <SignalTimeline signals={f.signals} />
            </section>
          </div>
        </div>
      )}
    </Async>
  );
}
