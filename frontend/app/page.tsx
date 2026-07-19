import Link from "next/link";
import { ArrowRight, Brain, LineChart, Rocket } from "lucide-react";

// Landing page - deliberately slim. Product name, one-line pitch, and two
// entry points: Investors (the pipeline dashboard and the full desk) and
// Searching Investment (the founder-facing apply flow). No investor nav here.

function EntryCard({
  href,
  icon: Icon,
  eyebrow,
  title,
  copy,
  cta,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  eyebrow: string;
  title: string;
  copy: string;
  cta: string;
}) {
  return (
    <Link
      href={href}
      className="group flex flex-col rounded-2xl border border-border bg-card p-6 shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md"
    >
      <span className="flex size-10 items-center justify-center rounded-xl bg-blue-600 text-white">
        <Icon className="size-5" />
      </span>
      <span className="mt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {eyebrow}
      </span>
      <span className="mt-1 text-lg font-semibold tracking-tight">{title}</span>
      <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
        {copy}
      </p>
      <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-blue-700">
        {cta}
        <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}

export default function LandingPage() {
  return (
    <div className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-6 py-16">
      <div className="flex items-center gap-2.5">
        <span className="flex size-9 items-center justify-center rounded-lg bg-blue-600 text-white">
          <Brain className="size-5" />
        </span>
        <span className="text-base font-semibold tracking-tight">The VC Brain</span>
      </div>

      <h1 className="mt-8 text-3xl font-semibold tracking-tight sm:text-4xl">
        Sourcing, screening, diligence and decision - on one desk.
      </h1>
      <p className="mt-3 max-w-xl text-base leading-relaxed text-muted-foreground">
        An AI-first venture funnel that scores every founder across three
        independent axes, checks each claim against the evidence, and writes the
        memo - with its trust levels and gaps shown, never hidden.
      </p>

      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        <EntryCard
          href="/pipeline"
          icon={LineChart}
          eyebrow="Investors"
          title="Open the pipeline"
          copy="Rank the funnel, run natural-language founder search, set your mandate, source outbound candidates, and read evidence-backed memos."
          cta="Enter the desk"
        />
        <EntryCard
          href="/apply"
          icon={Rocket}
          eyebrow="Searching investment"
          title="Apply for funding"
          copy="Submit your company and pitch deck. It enters the same funnel as sourced candidates and is analysed the moment it lands."
          cta="Start an application"
        />
      </div>
    </div>
  );
}
