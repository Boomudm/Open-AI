"use client";

import type { MachineHeatmapCell } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useMemo } from "react";

type MachineHeatmapProps = {
  data: MachineHeatmapCell[];
  loading?: boolean;
};

/** Sqrt scale so one hot week does not wash out the grid. */
function heatIntensity(total: number, maxTotal: number): number {
  if (total <= 0 || maxTotal <= 0) return 0;
  return Math.sqrt(total) / Math.sqrt(maxTotal);
}

function heatColor(total: number, maxTotal: number): string {
  if (total <= 0) return "bg-gemini-border/20 dark:bg-gemini-dark-border/20";
  const t = heatIntensity(total, maxTotal);
  if (t >= 0.85) return "bg-red-500/80";
  if (t >= 0.6) return "bg-amber-500/75";
  if (t >= 0.35) return "bg-gemini-blue/65 dark:bg-gemini-dark-blue/65";
  return "bg-gemini-blue/35 dark:bg-gemini-dark-blue/35";
}

const LEGEND = [
  { label: "ต่ำ", className: "bg-gemini-blue/35 dark:bg-gemini-dark-blue/35" },
  { label: "กลาง", className: "bg-gemini-blue/65 dark:bg-gemini-dark-blue/65" },
  { label: "สูง", className: "bg-amber-500/75" },
  { label: "สูงมาก", className: "bg-red-500/80" },
];

export function MachineHeatmap({ data, loading }: MachineHeatmapProps) {
  const { machines, weeks, grid, max } = useMemo(() => {
    const machineSet = new Set<string>();
    const weekSet = new Set<string>();
    const grid = new Map<string, MachineHeatmapCell>();
    let max = 0;
    for (const cell of data) {
      machineSet.add(cell.machine_id);
      weekSet.add(cell.week);
      grid.set(`${cell.machine_id}|${cell.week}`, cell);
      max = Math.max(max, cell.total);
    }
    return {
      machines: Array.from(machineSet).sort().slice(0, 12),
      weeks: Array.from(weekSet).sort().slice(-8),
      grid,
      max: max || 1,
    };
  }, [data]);

  if (loading) {
    return <div className="h-40 rounded-2xl bg-gemini-surface/60 animate-pulse" />;
  }

  if (!data.length) {
    return (
      <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted py-6 text-center">
        ยังไม่มีกิจกรรมคำถาม/ซ่อมรายสัปดาห์
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full text-[10px] border-collapse min-w-[280px]">
          <thead>
            <tr>
              <th className="text-left p-1 text-gemini-muted dark:text-gemini-dark-muted">เครื่อง</th>
              {weeks.map((w) => (
                <th key={w} className="p-1 text-gemini-muted dark:text-gemini-dark-muted font-normal">
                  {w.slice(-3)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {machines.map((machine) => (
              <tr key={machine}>
                <td className="p-1 text-gemini-text dark:text-gemini-dark-text whitespace-nowrap">{machine}</td>
                {weeks.map((week) => {
                  const cell = grid.get(`${machine}|${week}`);
                  const total = cell?.total ?? 0;
                  return (
                    <td key={week} className="p-0.5">
                      <div
                        title={`รวม ${total} (AI ${cell?.ai_count ?? 0} · ซ่อม ${cell?.repair_count ?? 0})`}
                        className={cn("h-5 w-5 rounded-sm", heatColor(total, max))}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-[10px] text-gemini-muted dark:text-gemini-dark-muted">
        <span>สเกล (√): สูงสุด {max}/สัปดาห์</span>
        {LEGEND.map((item) => (
          <span key={item.label} className="inline-flex items-center gap-1">
            <span className={cn("h-3 w-3 rounded-sm", item.className)} />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
}
