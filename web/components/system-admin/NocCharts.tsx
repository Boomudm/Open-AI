"use client";

import { NocTip, type NocTipContent } from "@/components/system-admin/NocTip";
import { useId } from "react";

export type SeriesPoint = {
  date?: string;
  label?: string;
  ts?: number;
  value: number;
};

export type SplitPoint = {
  date: string;
  prompt: number;
  completion: number;
};

export type IngestStatusPoint = {
  date: string;
  completed: number;
  failed: number;
  deleted: number;
  pending_review: number;
  queued: number;
};

const G = {
  grid: "rgba(0, 229, 255, 0.07)",
  axis: "#5a7a8f",
  text: "#8eb4cc",
  blue: "#5794f2",
  green: "#73bf69",
  orange: "#ff9830",
  red: "#f2495c",
  yellow: "#fade2a",
  purple: "#b877d9",
};

function dayLabel(date?: string, label?: string, ts?: number): string {
  // Hourly series carry an epoch `ts` — derive the hour label from it in the
  // viewer's local timezone rather than trusting the pre-formatted `label`
  // string, which the backend formats in UTC (e.g. "03:00" shown at 10:03 ICT).
  if (ts != null) {
    const d = new Date(ts * 1000);
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }
  if (label) return label;
  if (!date) return "";
  const p = date.split("-");
  return p.length >= 3 ? `${p[1]}/${p[2]}` : date.slice(5);
}

function fmtAxis(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 10_000) return `${(v / 1_000).toFixed(0)}k`;
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
  if (v < 1 && v > 0) return v.toFixed(2);
  return String(Math.round(v));
}

function yTicks(max: number, count = 4): number[] {
  if (max <= 0) return [0];
  const step = max / count;
  return Array.from({ length: count + 1 }, (_, i) => Math.round(step * i));
}

/** Grafana-style panel wrapper */
export function GrafanaPanel({
  title,
  subtitle,
  legend,
  children,
  className = "",
  alert,
  tip,
}: {
  title: string;
  subtitle?: string;
  legend?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  alert?: boolean;
  tip?: NocTipContent;
}) {
  const panel = (
    <section className={`grafana-panel flex min-h-0 flex-col ${alert ? "grafana-panel-alert" : ""} ${className}`}>
      <header className="grafana-panel-header shrink-0">
        <div className="min-w-0 flex-1">
          <h3 className="grafana-panel-title">{title}</h3>
          {subtitle ? <p className="grafana-panel-sub">{subtitle}</p> : null}
        </div>
        {legend ? <div className="grafana-legend shrink-0">{legend}</div> : null}
      </header>
      <div className="grafana-panel-body min-h-0 flex-1">{children}</div>
    </section>
  );
  if (!tip) return panel;
  return <NocTip content={tip}>{panel}</NocTip>;
}

/** Area / line time-series with Y-axis */
export function GrafanaTimeSeries({
  points,
  color = G.blue,
  unit = "",
  fallbackLabel = "ไม่มีข้อมูล",
}: {
  points: SeriesPoint[];
  color?: string;
  unit?: string;
  fallbackLabel?: string;
}) {
  const gradId = useId();
  const W = 400;
  const H = 160;
  const padL = 44;
  const padR = 8;
  const padT = 20;
  const padB = 28;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const values = points.map((p) => Math.max(0, p.value));
  const max = Math.max(...values, 1);
  const ticks = yTicks(max);

  if (points.length < 2) {
    // A single point can't draw a line/trend — treat it the same as "no data"
    // rather than plotting one invisible dot in the corner.
    return <div className="grafana-chart-empty">{fallbackLabel}</div>;
  }

  const coords = values.map((v, i) => ({
    x: padL + (i / Math.max(values.length - 1, 1)) * innerW,
    y: padT + innerH - (v / max) * innerH,
    v,
  }));

  const line = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x},${c.y}`).join(" ");
  const area = `${line} L${coords[coords.length - 1].x},${padT + innerH} L${coords[0].x},${padT + innerH} Z`;

  const xLabels = points.filter((_, i) => i % Math.max(1, Math.floor(points.length / 6)) === 0 || i === points.length - 1);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="grafana-chart-svg" preserveAspectRatio="none">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.35} />
          <stop offset="100%" stopColor={color} stopOpacity={0.02} />
        </linearGradient>
      </defs>

      {ticks.map((t) => {
        const y = padT + innerH - (t / max) * innerH;
        return (
          <g key={t}>
            <line x1={padL} y1={y} x2={W - padR} y2={y} stroke={G.grid} strokeWidth={1} />
            <text x={padL - 6} y={y + 4} textAnchor="end" className="grafana-axis-text">
              {fmtAxis(t)}
              {unit}
            </text>
          </g>
        );
      })}

      <path d={area} fill={`url(#${gradId})`} />
      <path d={line} fill="none" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke" />

      {coords.map((c, i) => (
        <circle key={i} cx={c.x} cy={c.y} r={2.5} fill={color} opacity={0.9} />
      ))}

      {xLabels.map((p) => {
        const i = points.indexOf(p);
        const x = padL + (i / Math.max(points.length - 1, 1)) * innerW;
        return (
          <text key={i} x={x} y={H - 6} textAnchor="middle" className="grafana-axis-text">
            {dayLabel(p.date, p.label, p.ts)}
          </text>
        );
      })}
    </svg>
  );
}

/** Vertical bar chart with Y-axis */
export function GrafanaBarChart({
  points,
  color = G.green,
  unit = "",
}: {
  points: SeriesPoint[];
  color?: string;
  unit?: string;
}) {
  const W = 400;
  const H = 160;
  const padL = 44;
  const padR = 8;
  const padT = 20;
  const padB = 28;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const values = points.map((p) => Math.max(0, p.value));
  const max = Math.max(...values, 1);
  const ticks = yTicks(max);
  const barW = innerW / Math.max(points.length, 1) - 4;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="grafana-chart-svg" preserveAspectRatio="none">
      {ticks.map((t) => {
        const y = padT + innerH - (t / max) * innerH;
        return (
          <g key={t}>
            <line x1={padL} y1={y} x2={W - padR} y2={y} stroke={G.grid} strokeWidth={1} />
            <text x={padL - 6} y={y + 4} textAnchor="end" className="grafana-axis-text">
              {fmtAxis(t)}
              {unit}
            </text>
          </g>
        );
      })}

      {points.map((p, i) => {
        const v = Math.max(0, p.value);
        const h = Math.max(2, (v / max) * innerH);
        const x = padL + i * (innerW / points.length) + 2;
        const y = padT + innerH - h;
        return (
          <g key={p.date ?? p.label ?? i}>
            <rect x={x} y={y} width={barW} height={h} fill={color} rx={1} opacity={v > 0 ? 0.9 : 0.25} />
            {v > 0 ? (
              <text x={x + barW / 2} y={Math.max(y - 4, 9)} textAnchor="middle" className="grafana-bar-value">
                {fmtAxis(v)}
              </text>
            ) : null}
            <text x={x + barW / 2} y={H - 6} textAnchor="middle" className="grafana-axis-text">
              {dayLabel(p.date, p.label, p.ts)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** Stacked bar — prompt vs completion tokens */
export function GrafanaStackedBars({
  points,
}: {
  points: SplitPoint[];
}) {
  const W = 400;
  const H = 160;
  const padL = 44;
  const padR = 8;
  const padT = 20;
  const padB = 28;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const totals = points.map((p) => p.prompt + p.completion);
  const max = Math.max(...totals, 1);
  const ticks = yTicks(max);
  const barW = innerW / Math.max(points.length, 1) - 4;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="grafana-chart-svg" preserveAspectRatio="none">
      {ticks.map((t) => {
        const y = padT + innerH - (t / max) * innerH;
        return (
          <g key={t}>
            <line x1={padL} y1={y} x2={W - padR} y2={y} stroke={G.grid} strokeWidth={1} />
            <text x={padL - 6} y={y + 4} textAnchor="end" className="grafana-axis-text">
              {fmtAxis(t)}
            </text>
          </g>
        );
      })}

      {points.map((p, i) => {
        const total = p.prompt + p.completion;
        const totalH = Math.max(2, (total / max) * innerH);
        const promptH = total > 0 ? (p.prompt / total) * totalH : 0;
        const complH = totalH - promptH;
        const x = padL + i * (innerW / points.length) + 2;
        const baseY = padT + innerH;
        return (
          <g key={p.date}>
            {complH > 0 ? (
              <rect x={x} y={baseY - totalH} width={barW} height={complH} fill={G.purple} rx={1} />
            ) : null}
            {promptH > 0 ? (
              <rect x={x} y={baseY - promptH} width={barW} height={promptH} fill={G.blue} rx={1} />
            ) : total === 0 ? (
              <rect x={x} y={baseY - 4} width={barW} height={4} fill={G.grid} rx={1} />
            ) : null}
            <text x={x + barW / 2} y={H - 6} textAnchor="middle" className="grafana-axis-text">
              {dayLabel(p.date)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** Stacked bar — ingest jobs per day by outcome (completed / queued / failed) */
export function GrafanaIngestBars({
  points,
}: {
  points: IngestStatusPoint[];
}) {
  const W = 400;
  const H = 160;
  const padL = 44;
  const padR = 8;
  const padT = 20;
  const padB = 28;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const totals = points.map((p) => p.completed + p.queued + p.failed + p.deleted + p.pending_review);
  const max = Math.max(...totals, 1);
  const ticks = yTicks(max);
  const barW = innerW / Math.max(points.length, 1) - 4;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="grafana-chart-svg" preserveAspectRatio="none">
      {ticks.map((t) => {
        const y = padT + innerH - (t / max) * innerH;
        return (
          <g key={t}>
            <line x1={padL} y1={y} x2={W - padR} y2={y} stroke={G.grid} strokeWidth={1} />
            <text x={padL - 6} y={y + 4} textAnchor="end" className="grafana-axis-text">
              {fmtAxis(t)}
            </text>
          </g>
        );
      })}

      {points.map((p, i) => {
        const total = p.completed + p.queued + p.failed + p.deleted + p.pending_review;
        const totalH = Math.max(2, (total / max) * innerH);
        const completedH = total > 0 ? (p.completed / total) * totalH : 0;
        const queuedH = total > 0 ? (p.queued / total) * totalH : 0;
        const failedH = total > 0 ? (p.failed / total) * totalH : 0;
        const pendingReviewH = total > 0 ? (p.pending_review / total) * totalH : 0;
        const deletedH = total > 0 ? totalH - completedH - queuedH - failedH - pendingReviewH : 0;
        const x = padL + i * (innerW / points.length) + 2;
        const baseY = padT + innerH;
        return (
          <g key={p.date}>
            {completedH > 0 ? (
              <rect x={x} y={baseY - completedH} width={barW} height={completedH} fill={G.green} rx={1} />
            ) : null}
            {queuedH > 0 ? (
              <rect x={x} y={baseY - completedH - queuedH} width={barW} height={queuedH} fill={G.yellow} rx={1} />
            ) : null}
            {pendingReviewH > 0 ? (
              <rect
                x={x}
                y={baseY - completedH - queuedH - pendingReviewH}
                width={barW}
                height={pendingReviewH}
                fill={G.orange}
                rx={1}
              />
            ) : null}
            {failedH > 0 ? (
              <rect
                x={x}
                y={baseY - completedH - queuedH - pendingReviewH - failedH}
                width={barW}
                height={failedH}
                fill={G.red}
                rx={1}
              />
            ) : null}
            {deletedH > 0 ? (
              <rect x={x} y={baseY - totalH} width={barW} height={deletedH} fill={G.purple} rx={1} />
            ) : null}
            {total === 0 ? (
              <rect x={x} y={baseY - 4} width={barW} height={4} fill={G.grid} rx={1} />
            ) : null}
            <text x={x + barW / 2} y={H - 6} textAnchor="middle" className="grafana-axis-text">
              {dayLabel(p.date)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

const DONUT_COLORS = [G.green, G.orange, G.blue, G.red, G.yellow, G.purple];

/** Donut chart for categorical breakdown */
export function GrafanaDonut({
  slices,
  size = 120,
  fill = false,
  compact = false,
}: {
  slices: Array<{ label: string; value: number }>;
  size?: number;
  /** Stretch to fill panel height when true. */
  fill?: boolean;
  /** Hide legend list — for narrow side panels. */
  compact?: boolean;
}) {
  const donutSize = compact ? Math.min(size, 72) : size;
  const wrapClass = [
    fill && !compact ? "noc-donut-fill" : "",
    compact ? "noc-donut-compact" : "flex h-full items-center gap-4",
  ]
    .filter(Boolean)
    .join(" ");
  const svgProps = compact
    ? { width: donutSize, height: donutSize, className: "noc-donut-svg shrink-0" }
    : fill
      ? { className: "noc-donut-svg", viewBox: `0 0 ${donutSize} ${donutSize}` }
      : { width: donutSize, height: donutSize, className: "shrink-0" };

  const total = slices.reduce((a, s) => a + s.value, 0);
  const cx = donutSize / 2;
  const cy = donutSize / 2;
  const r = donutSize * 0.38;
  const ir = donutSize * 0.26;

  if (total === 0) {
    return (
      <div className={wrapClass || "flex items-center justify-center"}>
        <svg {...svgProps}>
          <circle cx={cx} cy={cy} r={r} fill="none" stroke={G.grid} strokeWidth={r - ir} />
          <text x={cx} y={cy + 5} textAnchor="middle" className="grafana-donut-center">
            0
          </text>
        </svg>
        {!compact ? <p className="text-sm text-[var(--gf-muted)]">ไม่มี ingest jobs</p> : null}
      </div>
    );
  }

  let angle = -Math.PI / 2;
  const arcs = slices.map((s, i) => {
    const frac = s.value / total;
    const sweep = frac * Math.PI * 2;
    const startAngle = angle;
    angle += sweep;
    const x1 = cx + r * Math.cos(startAngle);
    const y1 = cy + r * Math.sin(startAngle);
    let d: string;
    if (sweep >= Math.PI * 2 - 1e-6) {
      // A full circle (single slice at 100%) has identical start/end points,
      // which a single SVG arc command draws as nothing — split into two
      // semicircle arcs instead so it actually renders.
      const midAngle = startAngle + Math.PI;
      const xm = cx + r * Math.cos(midAngle);
      const ym = cy + r * Math.sin(midAngle);
      d = `M ${x1} ${y1} A ${r} ${r} 0 1 1 ${xm} ${ym} A ${r} ${r} 0 1 1 ${x1} ${y1}`;
    } else {
      const x2 = cx + r * Math.cos(angle);
      const y2 = cy + r * Math.sin(angle);
      const large = sweep > Math.PI ? 1 : 0;
      d = `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
    }
    return { d, color: DONUT_COLORS[i % DONUT_COLORS.length], ...s, pct: frac * 100 };
  });

  return (
    <div className={wrapClass || "flex items-center justify-center"}>
      <svg {...svgProps}>
        {arcs.map((a) => (
          <path key={a.label} d={a.d} fill="none" stroke={a.color} strokeWidth={r - ir} strokeLinecap="butt" />
        ))}
        <text x={cx} y={cy + 6} textAnchor="middle" className="grafana-donut-center">
          {total}
        </text>
      </svg>
      {!compact ? (
        <ul className="min-w-0 flex-1 space-y-1">
          {arcs.map((a) => (
            <li key={a.label} className="flex items-center gap-2 text-sm">
              <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: a.color }} />
              <span className="truncate capitalize text-[var(--gf-text)]">{a.label}</span>
              <span className="ml-auto tabular-nums text-[var(--gf-muted)]">
                {a.value} ({a.pct.toFixed(0)}%)
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Big stat — Grafana single-stat panel */
export function GrafanaStat({
  label,
  value,
  unit,
  color,
  spark,
  delta,
  tip,
  secondary,
}: {
  label: string;
  value: string;
  unit?: string;
  color?: string;
  spark?: SeriesPoint[];
  delta?: { pct: number; label?: string } | null;
  tip?: NocTipContent;
  /** Second metric shown in the same cell (e.g. p95 latency next to Requests/s). */
  secondary?: { label: string; value: string };
}) {
  const deltaPct = delta?.pct;
  const deltaUp = deltaPct != null && deltaPct >= 0;
  const stat = (
    <div className="grafana-stat">
      <p className="grafana-stat-label">{label}</p>
      <div className="grafana-stat-row-inner">
        <p className="grafana-stat-value" style={{ color: color ?? "var(--gf-text-bright)" }}>
          {value}
          {unit ? <span className="grafana-stat-unit">{unit}</span> : null}
        </p>
        {deltaPct != null && Number.isFinite(deltaPct) ? (
          <span className={`grafana-stat-delta ${deltaUp ? "up" : "down"}`} title={delta?.label ?? "vs yesterday"}>
            {deltaUp ? "+" : ""}
            {deltaPct.toFixed(0)}%
          </span>
        ) : null}
      </div>
      {secondary ? (
        <p className="grafana-stat-secondary">
          {secondary.label}: <span className="tabular-nums">{secondary.value}</span>
        </p>
      ) : null}
      {spark && spark.length > 1 ? (
        <div className="grafana-stat-spark mt-1 h-8">
          <GrafanaTimeSeries points={spark} color={color ?? G.blue} />
        </div>
      ) : null}
    </div>
  );
  if (!tip) return stat;
  return <NocTip content={tip}>{stat}</NocTip>;
}

export function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="grafana-legend-item">
      <span className="grafana-legend-dot" style={{ background: color }} />
      {label}
    </span>
  );
}
