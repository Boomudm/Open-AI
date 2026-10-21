"use client";

import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { useLandingMessages } from "@/providers/LocaleProvider";

const CATEGORY_COLORS = [
  "text-sky-400 border-sky-400/30 bg-sky-500/10",
  "text-cyan-400 border-cyan-400/30 bg-cyan-500/10",
  "text-blue-400 border-blue-400/30 bg-blue-500/10",
  "text-indigo-400 border-indigo-400/30 bg-indigo-500/10",
  "text-teal-400 border-teal-400/30 bg-teal-500/10",
];

export function LandingDocumentTypes() {
  const m = useLandingMessages();

  return (
    <section id="documents" className="relative border-t border-landing-border bg-landing-surface/20">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-16 lg:py-24">
        <ScrollReveal className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6">
          <div className="max-w-2xl">
            <p className="text-sm font-semibold uppercase tracking-wider text-cyan-400 mb-3">
              {m.documents.eyebrow}
            </p>
            <h2 className="text-2xl sm:text-4xl font-semibold text-landing-text tracking-tight">
              {m.documents.title}{" "}
              <span className="landing-gradient-text">{m.documents.titleHighlight}</span>
            </h2>
            <p className="mt-4 text-lg text-landing-muted">{m.documents.subtitle}</p>
          </div>
          <p className="text-4xl font-bold landing-gradient-text shrink-0">15</p>
        </ScrollReveal>

        <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {m.documents.categories.map(({ name, types }, ci) => (
            <ScrollReveal
              key={name}
              className="rounded-xl border border-landing-border bg-landing-surface p-4 landing-card-shine"
              delay={100 + ci * 80}
            >
              <span
                className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-semibold ${CATEGORY_COLORS[ci % CATEGORY_COLORS.length]}`}
              >
                {name}
              </span>
              <ul className="mt-4 space-y-2">
                {types.map((t) => (
                  <li
                    key={t}
                    className="font-mono text-xs text-landing-muted hover:text-landing-text transition-colors"
                  >
                    {t}
                  </li>
                ))}
              </ul>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  );
}
