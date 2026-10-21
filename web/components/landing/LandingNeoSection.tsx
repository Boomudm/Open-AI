"use client";

import { NeoMascot } from "@/components/chat/gemini/NeoMascot";
import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { useLandingMessages } from "@/providers/LocaleProvider";
import { Download, MessageSquareWarning, Smartphone } from "lucide-react";

export function LandingNeoSection() {
  const m = useLandingMessages();

  return (
    <section className="relative border-t border-landing-border overflow-hidden">
      <div className="absolute inset-0 landing-hero-glow opacity-40" aria-hidden />
      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-16 lg:py-24">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
          <ScrollReveal>
            <p className="text-sm font-semibold uppercase tracking-wider text-sky-400 mb-3">
              {m.neo.eyebrow}
            </p>
            <h2 className="text-2xl sm:text-4xl font-semibold text-landing-text tracking-tight">
              {m.neo.title}{" "}
              <span className="landing-gradient-text">{m.neo.titleHighlight}</span>
            </h2>
            <p className="mt-4 text-lg text-landing-muted">{m.neo.subtitle}</p>

            <div className="mt-8 space-y-4">
              <div className="flex gap-3 rounded-lg border border-landing-border bg-landing-surface/80 p-4">
                <Smartphone className="h-5 w-5 text-sky-400 shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium text-landing-text text-sm">{m.neo.installTitle}</p>
                  <p className="text-sm text-landing-muted mt-1">{m.neo.installDesc}</p>
                </div>
              </div>
              <div className="flex gap-3 rounded-lg border border-landing-border bg-landing-surface/80 p-4">
                <Download className="h-5 w-5 text-cyan-400 shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium text-landing-text text-sm">{m.neo.offlineTitle}</p>
                  <p className="text-sm text-landing-muted mt-1">{m.neo.offlineDesc}</p>
                </div>
              </div>
              <div className="flex gap-3 rounded-lg border border-landing-border bg-landing-surface/80 p-4">
                <MessageSquareWarning className="h-5 w-5 text-blue-400 shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium text-landing-text text-sm">{m.neo.feedbackTitle}</p>
                  <p className="text-sm text-landing-muted mt-1">{m.neo.feedbackDesc}</p>
                </div>
              </div>
            </div>
          </ScrollReveal>

          <ScrollReveal className="relative flex justify-center" delay={200}>
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="h-64 w-64 rounded-full bg-gradient-to-br from-sky-500/25 via-cyan-500/15 to-blue-600/20 blur-3xl animate-landing-pulse-glow" />
            </div>
            <NeoMascot size="xl" animation="idle" priority />
          </ScrollReveal>
        </div>

        <ScrollReveal className="mt-16" delay={300}>
          <p className="text-sm font-semibold uppercase tracking-wider text-landing-muted mb-6 text-center">
            {m.neo.roiEyebrow}
          </p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {m.neo.roi.map(({ title, desc }) => (
              <div
                key={title}
                className="rounded-lg border border-landing-border bg-landing-surface/60 px-4 py-3 landing-card-shine"
              >
                <p className="font-medium text-sm text-landing-text">{title}</p>
                <p className="text-xs text-landing-muted mt-1">{desc}</p>
              </div>
            ))}
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
