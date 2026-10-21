"use client";

import { NocTip } from "@/components/system-admin/NocTip";
import type { SystemAdminDashboard } from "@/lib/api";
import { buildNocDebugLinks } from "@/lib/system-admin/nocDebugLinks";

export function NocDebugLinks({ data, promUp }: { data: SystemAdminDashboard; promUp: boolean }) {
  const links = buildNocDebugLinks(data, promUp);

  return (
    <div className="noc-debug-links" aria-label="Debug consoles">
      <div className="noc-debug-links-row">
        {links.map(({ id, label, href, icon: Icon, tip, muted }) => {
          const tile = (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className={`noc-debug-link ${muted ? "noc-debug-link-muted" : ""}`}
            >
              <Icon className="noc-debug-link-icon" aria-hidden />
              <span className="noc-debug-link-label">{label}</span>
            </a>
          );
          return (
            <NocTip key={id} content={tip}>
              {tile}
            </NocTip>
          );
        })}
      </div>
    </div>
  );
}
