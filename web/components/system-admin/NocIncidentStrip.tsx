"use client";

import { NocTip, type NocTipContent } from "@/components/system-admin/NocTip";
import type { SystemAdminDashboard } from "@/lib/api";
import { AlertTriangle, Info, ShieldAlert } from "lucide-react";

type Incident = SystemAdminDashboard["incidents"][number];

function severityIcon(sev: string) {
  if (sev === "critical") return ShieldAlert;
  if (sev === "warn") return AlertTriangle;
  return Info;
}

function severityClass(sev: string) {
  if (sev === "critical") return "critical";
  if (sev === "warn") return "warn";
  return "info";
}

function incidentTip(inc: Incident): NocTipContent {
  return {
    title: inc.title,
    lines: [inc.detail, `แหล่ง: ${inc.source}`, inc.at ? new Date(inc.at).toLocaleString("th-TH") : ""].filter(Boolean),
  };
}

export function NocIncidentStrip({ incidents }: { incidents: Incident[] }) {
  const items = incidents.slice(0, 12);
  const hasCritical = items.some((i) => i.severity === "critical");

  return (
    <div className={`noc-incident-strip ${hasCritical ? "noc-incident-critical" : ""}`} role="list">
      {items.map((inc, idx) => {
        const Icon = severityIcon(inc.severity);
        const chip = (
          <div className={`noc-incident-chip ${severityClass(inc.severity)}`} role="listitem">
            <Icon className="noc-incident-icon" aria-hidden />
            <span className="noc-incident-title">{inc.title}</span>
            <span className="noc-incident-detail">{inc.detail}</span>
          </div>
        );
        return (
          <NocTip key={`${inc.source}-${inc.title}-${idx}`} content={incidentTip(inc)}>
            {chip}
          </NocTip>
        );
      })}
    </div>
  );
}
