import type { ScoreHistoryEntry } from "@/lib/types";
import { relativeDate } from "@/lib/format";

// A dependency-free SVG area/line chart of the persistent Founder Score over time.
// Uses a fixed viewBox coordinate system and scales responsively via CSS.
const W = 640;
const H = 240;
const PAD = { top: 16, right: 20, bottom: 28, left: 30 };

export function ScoreChart({ history }: { history: ScoreHistoryEntry[] }) {
  const points = [...history]
    .map((h) => ({ ...h, t: new Date(h.timestamp).getTime() }))
    .filter((h) => Number.isFinite(h.t) && Number.isFinite(h.score))
    .sort((a, b) => a.t - b.t);

  if (points.length === 0)
    return (
      <p className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
        No score history yet.
      </p>
    );

  const tMin = points[0].t;
  const tMax = points[points.length - 1].t;
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  const x = (t: number) =>
    tMax === tMin
      ? PAD.left + innerW / 2
      : PAD.left + ((t - tMin) / (tMax - tMin)) * innerW;
  const y = (s: number) => PAD.top + (1 - s / 10) * innerH;

  const coords = points.map((p) => ({ ...p, cx: x(p.t), cy: y(p.score) }));
  const line = coords.map((c, i) => `${i ? "L" : "M"}${c.cx},${c.cy}`).join(" ");
  const area = `${line} L${coords[coords.length - 1].cx},${y(0)} L${coords[0].cx},${y(0)} Z`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Founder score over time">
      <defs>
        <linearGradient id="scoreFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="rgb(37 99 235)" stopOpacity="0.18" />
          <stop offset="100%" stopColor="rgb(37 99 235)" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* y gridlines + labels */}
      {[0, 2, 4, 6, 8, 10].map((s) => (
        <g key={s}>
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={y(s)}
            y2={y(s)}
            stroke="currentColor"
            className="text-border"
            strokeWidth={1}
          />
          <text
            x={PAD.left - 6}
            y={y(s) + 3}
            textAnchor="end"
            className="fill-muted-foreground text-[10px]"
          >
            {s}
          </text>
        </g>
      ))}

      <path d={area} fill="url(#scoreFill)" />
      <path d={line} fill="none" stroke="rgb(37 99 235)" strokeWidth={2} />

      {coords.map((c, i) => (
        <g key={i}>
          <circle cx={c.cx} cy={c.cy} r={3.5} fill="white" stroke="rgb(37 99 235)" strokeWidth={2}>
            <title>
              {relativeDate(c.timestamp)}: {c.score.toFixed(1)}
              {c.note ? ` - ${c.note}` : ""}
            </title>
          </circle>
          <text
            x={c.cx}
            y={c.cy - 9}
            textAnchor="middle"
            className="fill-foreground text-[10px] font-medium tabular-nums"
          >
            {c.score.toFixed(1)}
          </text>
        </g>
      ))}

      {/* x labels: first and last */}
      {[coords[0], coords[coords.length - 1]].map((c, i) =>
        coords.length === 1 && i === 1 ? null : (
          <text
            key={i}
            x={c.cx}
            y={H - 8}
            textAnchor={i === 0 ? "start" : "end"}
            className="fill-muted-foreground text-[10px]"
          >
            {relativeDate(c.timestamp)}
          </text>
        ),
      )}
    </svg>
  );
}
