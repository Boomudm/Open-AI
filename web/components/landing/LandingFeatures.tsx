"use client";

import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { cn } from "@/lib/cn";
import { useLandingMessages } from "@/providers/LocaleProvider";
import { BarChart3, Bot, ClipboardList, FileText, MessageSquare, Shield } from "lucide-react";
import type { LucideIcon } from "lucide-react";

const FEATURE_META: { icon: LucideIcon; span?: string; accent: string }[] = [
  { icon: Bot, span: "lg:col-span-2", accent: "from-sky-500/20 to-cyan-500/10" },
  { icon: FileText, accent: "from-blue-500/20 to-sky-500/10" },
  { icon: ClipboardList, accent: "from-cyan-500/20 to-teal-500/10" },
  { icon: BarChart3, accent: "from-indigo-500/20 to-blue-500/10" },
  { icon: Shield, span: "lg:col-span-2", accent: "from-blue-600/20 to-sky-500/10" },
  { icon: MessageSquare, accent: "from-sky-400/20 to-cyan-400/10" },
];

export function LandingFeatures() {
  const m = useLandingMessages();

  return (
    <section id="features" className="relative bg-landing-bg">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-16 lg:py-24">
        <ScrollReveal className="max-w-2xl">
          <p className="text-sm font-semibold uppercase tracking-wider text-sky-400 mb-3">
            {m.features.eyebrow}
          </p>
          <h2 className="text-2xl sm:text-4xl font-semibold text-landing-text tracking-tight">
            {m.features.title}{" "}
            <span className="landing-gradient-text">{m.features.titleHighlight}</span>
          </h2>
          <p className="mt-4 text-lg text-landing-muted">{m.features.subtitle}</p>
        </ScrollReveal>

        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {m.features.items.map(({ title, description }, i) => {
            const meta = FEATURE_META[i] ?? FEATURE_META[0];
            const Icon = meta.icon;
            return (
              <ScrollReveal
                key={title}
                as="article"
                className={cn(
                  "group relative rounded-xl border border-landing-border bg-landing-surface p-6",
                  "landing-feature-glow landing-card-shine",
                  meta.span
                )}
                delay={150 + i * 80}
              >
                <div
                  className={cn(
                    "absolute inset-0 rounded-xl bg-gradient-to-br opacity-0 transition-opacity duration-300 group-hover:opacity-100",
                    meta.accent
                  )}
                />
                <div className="relative">
                  <div className="flex h-11 w-11 items-center justify-center rounded-lg border border-landing-border bg-landing-bg text-landing-text transition-transform duration-300 group-hover:scale-110 group-hover:border-sky-400/40">
                    <Icon className="h-5 w-5" aria-hidden />
                  </div>
                  <h3 className="mt-4 text-lg font-semibold text-landing-text">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-landing-muted">{description}</p>
                </div>
              </ScrollReveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
