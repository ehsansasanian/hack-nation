// Shared display helpers: axis / trust / trend vocab, colour maps, and formatters.
// One place so every chip, badge and label reads the same across the app.

import type { Axis, Score, TrustLevel } from "./types";

export const AXIS_META: Record<Axis, { label: string; short: string; tint: string }> = {
  founder: {
    label: "Founder",
    short: "F",
    tint: "border-indigo-200 bg-indigo-50 text-indigo-700",
  },
  market: {
    label: "Market",
    short: "M",
    tint: "border-teal-200 bg-teal-50 text-teal-700",
  },
  idea_vs_market: {
    label: "Idea vs Market",
    short: "I",
    tint: "border-amber-200 bg-amber-50 text-amber-800",
  },
};

export const AXIS_ORDER: Axis[] = ["founder", "market", "idea_vs_market"];

export const TRUST_META: Record<
  TrustLevel,
  { label: string; badge: string; dot: string }
> = {
  verified: {
    label: "Verified",
    badge: "border-emerald-200 bg-emerald-50 text-emerald-700",
    dot: "bg-emerald-500",
  },
  consistent: {
    label: "Consistent",
    badge: "border-sky-200 bg-sky-50 text-sky-700",
    dot: "bg-sky-500",
  },
  unverified: {
    label: "Unverified",
    badge: "border-zinc-200 bg-zinc-50 text-zinc-500",
    dot: "bg-zinc-400",
  },
  contradicted: {
    label: "Contradicted",
    badge: "border-red-200 bg-red-50 text-red-700",
    dot: "bg-red-500",
  },
};

/** Order scores by the canonical axis order and drop unknown axes. */
export function orderedScores(scores: Score[]): Score[] {
  return AXIS_ORDER.map((a) => scores.find((s) => s.axis === a)).filter(
    (s): s is Score => Boolean(s),
  );
}

/** A cold-start score renders as a range; otherwise a single figure. */
export function scoreDisplay(score: Score): string {
  if (score.cold_start && score.score_low != null && score.score_high != null) {
    return `${score.score_low.toFixed(1)}-${score.score_high.toFixed(1)}`;
  }
  return score.value.toFixed(1);
}

export function fmt(n: number | null | undefined, digits = 1): string {
  if (n == null) return "-";
  return n.toFixed(digits);
}

export type Recommendation = "invest" | "pass" | "need-more-info" | "unknown";

export function parseRecommendation(text: string | null | undefined): {
  kind: Recommendation;
  headline: string;
  detail: string;
} {
  const raw = text ?? "";
  const lower = raw.toLowerCase();
  let kind: Recommendation = "unknown";
  let headline = "Recommendation";
  if (lower.startsWith("invest")) {
    kind = "invest";
    headline = "Invest $100K";
  } else if (lower.startsWith("pass")) {
    kind = "pass";
    headline = "Pass";
  } else if (lower.startsWith("need-more-info") || lower.startsWith("need more")) {
    kind = "need-more-info";
    headline = "Need more info";
  }
  // Detail is everything after the leading "verb - "
  const dashIdx = raw.indexOf(" - ");
  const detail = dashIdx >= 0 ? raw.slice(dashIdx + 3) : raw;
  return { kind, headline, detail };
}

export const RECOMMENDATION_STYLE: Record<Recommendation, string> = {
  invest: "border-emerald-200 bg-emerald-50 text-emerald-900",
  pass: "border-red-200 bg-red-50 text-red-900",
  "need-more-info": "border-amber-200 bg-amber-50 text-amber-900",
  unknown: "border-zinc-200 bg-zinc-50 text-zinc-900",
};

export function relativeDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/** Count claims flagged as contradicted (for the pipeline trust summary). */
export function contradictionCount(claims: { trust_level: TrustLevel | null }[]): number {
  return claims.filter((c) => c.trust_level === "contradicted").length;
}
