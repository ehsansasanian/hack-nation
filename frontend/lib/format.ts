// Shared display helpers: axis / trust / trend vocab, colour maps, and formatters.
// One place so every chip, badge and label reads the same across the app.

import type { Axis, Score, Trend, TrustLevel } from "./types";

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

/** Whether an application has a substantive "edge" (alpha) signal, mirroring the
 *  server-side Edge rule (cold-start | outbound | improving trend). Used only for a
 *  low-clutter inline hint in the dense pipeline table; the authoritative,
 *  evidence-cited Edge panel is server-computed on the application detail page. */
export function hasEdgeHint(app: {
  origin: string;
  scores: { cold_start: boolean; trend: Trend | null }[];
}): boolean {
  if (app.origin === "outbound") return true;
  return app.scores.some((s) => s.cold_start || s.trend === "improving");
}

export const SOURCE_TINT: Record<string, string> = {
  github: "border-zinc-200 bg-zinc-50 text-zinc-700",
  hn: "border-orange-200 bg-orange-50 text-orange-700",
  arxiv: "border-red-200 bg-red-50 text-red-700",
  news: "border-cyan-200 bg-cyan-50 text-cyan-700",
  deck: "border-blue-200 bg-blue-50 text-blue-700",
  manual: "border-violet-200 bg-violet-50 text-violet-700",
  synthetic: "border-zinc-200 bg-zinc-50 text-zinc-600",
};

export function sourceTint(source: string): string {
  return SOURCE_TINT[source] ?? SOURCE_TINT.synthetic;
}

/** A short human summary of a signal's JSON content, for evidence rows. */
export function signalSummary(content: Record<string, unknown>): string {
  const c = content as Record<string, unknown>;
  const pick = (k: string) => (c[k] == null ? undefined : String(c[k]));
  const candidates: (string | undefined)[] = [
    pick("title"),
    pick("repo") && `${pick("repo")}${c.stars != null ? ` · ${c.stars}★` : ""}`,
    pick("note"),
    pick("text"),
    pick("headline"),
    pick("kind") === "inbound_application" ? "Inbound deck submission" : undefined,
    pick("excerpt"),
    pick("summary"),
  ];
  const found = candidates.find(Boolean);
  if (found) return found;
  const entries = Object.entries(c)
    .filter(([, v]) => v != null && typeof v !== "object")
    .slice(0, 3)
    .map(([k, v]) => `${k}: ${v}`);
  return entries.join(" · ") || "signal";
}

// Confirmations that clear an axis - note that "no contradicted claim relied
// upon" contains the substring "contradict" but is a *pass*, so pass markers win.
const VALIDATOR_PASS_MARKERS = [
  "consistent with cited evidence",
  "no contradicted claim",
  "rationale holds",
];
const VALIDATOR_WARNING_MARKERS = [
  "overstat",
  "not supported",
  "unsupported",
  "hallucinat",
  "refut",
  "contradicted in diligence",
];

/** True when a validator note is flagging a problem rather than confirming the rationale. */
export function isValidatorWarning(note: string | null | undefined): boolean {
  if (!note) return false;
  const n = note.toLowerCase();
  if (VALIDATOR_PASS_MARKERS.some((m) => n.includes(m))) return false;
  return VALIDATOR_WARNING_MARKERS.some((m) => n.includes(m));
}
