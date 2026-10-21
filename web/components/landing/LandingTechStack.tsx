"use client";

import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { useLandingMessages } from "@/providers/LocaleProvider";

export function LandingTechStack() {
  const m = useLandingMessages();

  return (
    <section id="stack" className="relative border-t border-landing-border bg-landing-bg">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-16 lg:py-20">
        <ScrollReveal className="text-center max-w-2xl mx-auto">
          <p className="text-sm font-semibold uppercase tracking-wider text-landing-muted mb-3">
            {m.stack.eyebrow}
          </p>
          <h2 className="text-2xl sm:text-3xl font-semibold text-landing-text tracking-tight">
            {m.stack.title}
          </h2>
          <p className="mt-3 text-landing-muted">{m.stack.subtitle}</p>
        </ScrollReveal>

        <ScrollReveal className="mt-10 flex flex-wrap justify-center gap-3" delay={150}>
          {m.stack.items.map(({ name, role }) => (
            <div
              key={name}
              className="group rounded-lg border border-landing-border bg-landing-surface px-4 py-3 text-center min-w-[140px] landing-feature-glow landing-card-shine"
            >
              <p className="font-semibold text-sm text-landing-text group-hover:text-sky-400 transition-colors">
                {name}
              </p>
              <p className="text-[11px] text-landing-muted mt-1">{role}</p>
            </div>
          ))}
        </ScrollReveal>

        <ScrollReveal delay={250}>
          <p className="mt-8 text-center text-xs text-landing-muted">{m.stack.footnote}</p>
        </ScrollReveal>
      </div>
    </section>
  );
}
