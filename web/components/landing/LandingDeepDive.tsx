"use client";

import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { cn } from "@/lib/cn";
import { useLandingMessages } from "@/providers/LocaleProvider";
import {
  AlertTriangle,
  BarChart3,
  Bell,
  Bot,
  ClipboardList,
  LineChart,
  Package,
  Radio,
  Shield,
  WifiOff,
} from "lucide-react";
import { useState } from "react";
import type { LucideIcon } from "lucide-react";

const TAB_ICONS: Record<string, LucideIcon> = {
  rag: Bot,
  analytics: BarChart3,
  ops: ClipboardList,
  insights: LineChart,
  security: Shield,
  offline: WifiOff,
};

const QUICK_ICONS: LucideIcon[] = [AlertTriangle, Package, Bell, Radio];

export function LandingDeepDive() {
  const m = useLandingMessages();
  const [active, setActive] = useState(m.deepDive.tabs[0]?.id ?? "rag");
  const tab = m.deepDive.tabs.find((t) => t.id === active) ?? m.deepDive.tabs[0];
  const Icon = TAB_ICONS[tab.id] ?? Bot;

  return (
    <section id="capabilities" className="relative border-t border-landing-border bg-landing-bg">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-16 lg:py-24">
        <ScrollReveal className="max-w-2xl">
          <p className="text-sm font-semibold uppercase tracking-wider text-sky-400 mb-3">
            {m.deepDive.eyebrow}
          </p>
          <h2 className="text-2xl sm:text-4xl font-semibold text-landing-text tracking-tight">
            {m.deepDive.title}
          </h2>
          <p className="mt-4 text-lg text-landing-muted">{m.deepDive.subtitle}</p>
        </ScrollReveal>

        <ScrollReveal className="mt-10 flex flex-wrap gap-2" delay={150}>
          {m.deepDive.tabs.map(({ id, label }) => {
            const TabIcon = TAB_ICONS[id] ?? Bot;
            return (
              <button
                key={id}
                type="button"
                onClick={() => setActive(id)}
                className={cn(
                  "inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition-all",
                  active === id
                    ? "border-sky-400/50 bg-sky-500/15 text-landing-text shadow-lg shadow-sky-900/20"
                    : "border-landing-border text-landing-muted hover:text-landing-text hover:bg-landing-surface"
                )}
              >
                <TabIcon className="h-4 w-4" />
                {label}
              </button>
            );
          })}
        </ScrollReveal>

        <ScrollReveal
          key={active}
          className="mt-8 rounded-xl border border-landing-border bg-landing-surface p-6 sm:p-8 landing-feature-glow"
          delay={200}
        >
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-landing-border bg-landing-bg text-sky-400">
              <Icon className="h-6 w-6" />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="text-xl font-semibold text-landing-text">{tab.headline}</h3>
              {tab.endpoint && (
                <code className="mt-2 inline-block rounded bg-landing-bg border border-landing-border px-2 py-1 text-xs font-mono text-cyan-400">
                  {tab.endpoint}
                </code>
              )}
              <ul className="mt-5 space-y-3">
                {tab.bullets.map((b) => (
                  <li key={b} className="flex gap-3 text-sm text-landing-muted leading-relaxed">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-400" />
                    {b}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </ScrollReveal>

        <ScrollReveal className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-3" delay={250}>
          {m.deepDive.quickLinks.map(({ label, path }, i) => {
            const I = QUICK_ICONS[i] ?? Radio;
            return (
              <div
                key={path}
                className="flex items-center gap-2 rounded-lg border border-landing-border bg-landing-surface/50 px-3 py-2.5 text-xs"
              >
                <I className="h-3.5 w-3.5 text-landing-muted shrink-0" />
                <span className="text-landing-muted truncate">{label}</span>
                <code className="ml-auto font-mono text-[10px] text-landing-muted/70 truncate">{path}</code>
              </div>
            );
          })}
        </ScrollReveal>
      </div>
    </section>
  );
}
