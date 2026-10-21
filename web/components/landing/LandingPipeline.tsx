"use client";

import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { useLandingMessages } from "@/providers/LocaleProvider";
import {
  ArrowRight,
  Bot,
  Database,
  FileUp,
  Layers,
  Search,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

const STEP_ICONS: LucideIcon[] = [FileUp, Layers, Database, Search, Bot, Wrench];

export function LandingPipeline() {
  const m = useLandingMessages();

  return (
    <section id="how-it-works" className="relative border-t border-landing-border bg-landing-bg">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-16 lg:py-24">
        <ScrollReveal className="max-w-2xl">
          <p className="text-sm font-semibold uppercase tracking-wider text-sky-400 mb-3">
            {m.pipeline.eyebrow}
          </p>
          <h2 className="text-2xl sm:text-4xl font-semibold text-landing-text tracking-tight">
            {m.pipeline.title}{" "}
            <span className="landing-gradient-text">{m.pipeline.titleHighlight}</span>
          </h2>
          <p className="mt-4 text-lg text-landing-muted">{m.pipeline.subtitle}</p>
        </ScrollReveal>

        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {m.pipeline.steps.map(({ title, detail }, i) => {
            const Icon = STEP_ICONS[i] ?? FileUp;
            return (
              <ScrollReveal
                key={title}
                className="group relative flex gap-4 rounded-xl border border-landing-border bg-landing-surface/60 p-5 landing-feature-glow"
                delay={100 + i * 80}
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-landing-border bg-landing-bg text-sky-400 transition-colors group-hover:border-sky-400/40">
                  <Icon className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-landing-muted">0{i + 1}</span>
                    <h3 className="font-semibold text-landing-text">{title}</h3>
                    {i < m.pipeline.steps.length - 1 && (
                      <ArrowRight className="hidden lg:block h-3.5 w-3.5 text-landing-muted ml-auto shrink-0" />
                    )}
                  </div>
                  <p className="mt-1.5 text-sm text-landing-muted leading-relaxed">{detail}</p>
                </div>
              </ScrollReveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
