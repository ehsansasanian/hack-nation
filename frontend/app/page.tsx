import Link from "next/link";
import { ArrowRight, Brain } from "lucide-react";

// Landing page - deliberately minimal. A full-viewport deep-blue hero, the
// product wordmark, and two entry points: Investors (the pipeline desk) and
// Searching Investment (the founder-facing apply flow). No investor nav here.
//
// The hero blue is a deep, confident shade of the app's blue-600 accent.

export default function LandingPage() {
  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-[#0f2a5e] px-6 py-16 text-white">
      <div className="flex w-full max-w-2xl flex-col items-center text-center">
        <span className="flex size-12 items-center justify-center rounded-2xl bg-white/10 ring-1 ring-white/15">
          <Brain className="size-6" />
        </span>

        <h1 className="mt-8 text-6xl font-semibold tracking-tight sm:text-7xl md:text-8xl">
          DealAI
        </h1>

        <div className="mt-11 flex w-full flex-col items-center justify-center gap-3 sm:w-auto sm:flex-row">
          <Link
            href="/pipeline"
            className="group inline-flex w-full items-center justify-center gap-2 rounded-full bg-white px-7 py-3 text-sm font-semibold text-[#0f2a5e] shadow-sm transition-all hover:bg-white/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-[#0f2a5e] sm:w-auto"
          >
            Investors
            <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
          <Link
            href="/apply"
            className="group inline-flex w-full items-center justify-center gap-2 rounded-full border border-white/40 px-7 py-3 text-sm font-semibold text-white transition-all hover:border-white/70 hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-[#0f2a5e] sm:w-auto"
          >
            Searching Investment
            <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
        </div>
      </div>
    </main>
  );
}
