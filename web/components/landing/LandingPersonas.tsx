"use client";

import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { useLandingMessages } from "@/providers/LocaleProvider";
import { LayoutDashboard, MessageSquare, ShieldCheck } from "lucide-react";
import type { LucideIcon } from "lucide-react";

const PERSONA_ICONS: LucideIcon[] = [ShieldCheck, LayoutDashboard, MessageSquare];
const PERSONA_COLORS = [
  "from-blue-600/20 to-sky-500/5 border-sky-400/20",
  "from-sky-500/20 to-cyan-500/5 border-cyan-400/20",
  "from-cyan-500/20 to-teal-500/5 border-teal-400/20",
];

export function LandingPersonas() {
  const m = useLandingMessages();

  return (
    <section id="personas" className="relative border-t border-landing-border bg-landing-surface/20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-16 lg:py-24">
        <ScrollReveal className="max-w-2xl">
          <p className="text-sm font-semibold uppercase tracking-wider text-cyan-400 mb-3">
            {m.personas.eyebrow}
          </p>
          <h2 className="text-2xl sm:text-4xl font-semibold text-landing-text tracking-tight">
            {m.personas.title}
          </h2>
          <p className="mt-4 text-lg text-landing-muted">{m.personas.subtitle}</p>
        </ScrollReveal>

        <div className="mt-12 grid gap-6 lg:grid-cols-3">
          {m.personas.items.map(({ role, user, access, routes, home }, i) => {
            const Icon = PERSONA_ICONS[i] ?? ShieldCheck;
            return (
              <ScrollReveal
                key={role}
                as="article"
                className={`relative overflow-hidden rounded-xl border bg-gradient-to-br p-6 landing-feature-glow ${PERSONA_COLORS[i]}`}
                delay={100 + i * 100}
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-landing-border bg-landing-bg/80">
                    <Icon className="h-5 w-5 text-landing-text" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-landing-text">{role}</h3>
                    <p className="text-xs font-mono text-landing-muted">{user}</p>
                  </div>
                </div>
                <p className="mt-4 text-sm text-landing-muted">{access}</p>
                <ul className="mt-4 flex flex-wrap gap-1.5">
                  {routes.map((r) => (
                    <li
                      key={r}
                      className="rounded-md border border-landing-border bg-landing-bg/60 px-2 py-0.5 text-xs font-mono text-landing-muted"
                    >
                      {r}
                    </li>
                  ))}
                </ul>
                <p className="mt-4 text-xs text-landing-muted">
                  {m.personas.homeRoute}{" "}
                  <span className="font-mono text-landing-text">{home}</span>
                </p>
              </ScrollReveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
