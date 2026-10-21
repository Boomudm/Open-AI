"use client";

import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { useLandingMessages } from "@/providers/LocaleProvider";

export function LandingStats() {
  const m = useLandingMessages();

  return (
    <section className="relative border-y border-landing-border bg-landing-surface/30">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-6">
          {m.stats.map(({ value, label }, i) => (
            <ScrollReveal key={label} className="text-center" delay={50 + i * 60}>
              <p className="text-2xl sm:text-3xl font-bold landing-gradient-text">{value}</p>
              <p className="mt-1.5 text-xs sm:text-sm text-landing-muted leading-snug">{label}</p>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  );
}
