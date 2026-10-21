"use client";

import { LandingHeroRotatingWord } from "@/components/landing/LandingHeroRotatingWord";
import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";
import { cn } from "@/lib/cn";
import { useLandingMessages } from "@/providers/LocaleProvider";
import { Activity, Bot, CheckCircle2, Zap } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

export function LandingHero() {
  const m = useLandingMessages();
  const reducedMotion = usePrefersReducedMotion();
  const [lineIndex, setLineIndex] = useState(0);
  const [charIndex, setCharIndex] = useState(0);
  const [tabVisible, setTabVisible] = useState(true);
  const [heroBadge, setHeroBadge] = useState(m.hero.badgeOnPrem);

  useEffect(() => {
    const host = window.location.hostname;
    const local =
      host === "localhost" || host === "127.0.0.1" || host.endsWith(".local");
    setHeroBadge(local ? m.hero.badgeLocal : m.hero.badgeOnPrem);
  }, [m.hero.badgeLocal, m.hero.badgeOnPrem]);

  useEffect(() => {
    const onVisibility = () => setTabVisible(!document.hidden);
    onVisibility();
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  useEffect(() => {
    setLineIndex(0);
    setCharIndex(0);
  }, [m.hero.chatLines]);

  useEffect(() => {
    if (!tabVisible || reducedMotion) return;
    const line = m.hero.chatLines[lineIndex];
    if (charIndex < line.length) {
      const t = setTimeout(() => setCharIndex((c) => c + 1), 28);
      return () => clearTimeout(t);
    }
    const pause = setTimeout(() => {
      setCharIndex(0);
      setLineIndex((i) => (i + 1) % m.hero.chatLines.length);
    }, 2200);
    return () => clearTimeout(pause);
  }, [lineIndex, charIndex, tabVisible, reducedMotion, m.hero.chatLines]);

  return (
    <section className="relative overflow-x-clip overflow-y-visible">
      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="grid gap-12 py-16 lg:grid-cols-2 lg:items-center lg:py-28 lg:gap-16">
          <ScrollReveal className="max-w-xl overflow-visible" delay={100}>
            <div className="inline-flex items-center gap-2 rounded-full border border-landing-border bg-landing-surface/80 px-3 py-1 text-xs font-medium text-landing-muted mb-6">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky-400 opacity-60" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-sky-500" />
              </span>
              {heroBadge}
            </div>

            <h1
              data-testid="landing-hero-heading"
              className="text-4xl sm:text-5xl lg:text-[3.25rem] font-semibold leading-[1.4] text-landing-text text-balance"
            >
              {m.hero.titleLine1}
              <br />
              <span className="inline-block mt-1">
                {m.hero.titleLine2}{" "}
                <LandingHeroRotatingWord words={m.hero.rotatingWords} />
              </span>
            </h1>
            <p className="mt-6 text-lg sm:text-xl leading-relaxed text-landing-muted max-w-lg">
              {m.hero.subtitle}
            </p>
            <p className="mt-3 text-sm text-landing-muted/90 max-w-lg">{m.hero.accountNote}</p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                href="/login"
                className="group landing-btn-cta rounded-md shadow-lg shadow-sky-900/25 gap-2"
              >
                {m.hero.signIn}
                <Zap className="h-4 w-4 transition-transform group-hover:scale-110" />
              </Link>
              <a
                href="#how-it-works"
                className="landing-btn-outline rounded-md"
              >
                {m.hero.seeHow}
              </a>
            </div>

            <div className="mt-10 flex flex-wrap gap-6 text-sm text-landing-muted">
              <span className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-sky-400" />
                {m.hero.statDocTypes}
              </span>
              <span className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-sky-400" />
                {m.hero.statHybridRag}
              </span>
              <span className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-sky-400" />
                {m.hero.statRbac}
              </span>
            </div>
          </ScrollReveal>

          <ScrollReveal className="relative mx-auto w-full max-w-lg lg:max-w-none" delay={350}>
            <div className="absolute -inset-4 rounded-2xl bg-gradient-to-br from-sky-500/25 via-cyan-500/15 to-blue-600/20 blur-2xl animate-landing-pulse-glow" />

            <div className="relative animate-landing-float">
              <div className="rounded-xl border border-landing-border bg-landing-surface/90 backdrop-blur-sm p-1 shadow-2xl landing-card-shine">
                <div className="rounded-lg bg-landing-bg p-4 space-y-3 overflow-hidden relative">
                  <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/60 to-transparent animate-landing-scan" />

                  <div className="flex items-center gap-2">
                    <div className="h-2.5 w-2.5 rounded-full bg-red-500/70" />
                    <div className="h-2.5 w-2.5 rounded-full bg-yellow-500/70" />
                    <div className="h-2.5 w-2.5 rounded-full bg-sky-500/80" />
                    <span className="ml-2 text-xs text-landing-muted font-mono">neo / dashboard</span>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-md border border-landing-border bg-landing-surface p-3">
                      <p className="text-xs text-landing-muted flex items-center gap-1">
                        <Activity className="h-3 w-3" /> {m.hero.machines}
                      </p>
                      <p className="text-lg font-semibold text-landing-text mt-1 font-mono">MC-001</p>
                      <p className="text-xs text-sky-400 mt-1">{m.hero.active}</p>
                    </div>
                    <div className="rounded-md border border-landing-border bg-landing-surface p-3">
                      <p className="text-xs text-landing-muted">{m.hero.openWos}</p>
                      <p className="text-lg font-semibold text-landing-text mt-1">12</p>
                      <div className="mt-2 h-1 rounded-full bg-landing-border overflow-hidden">
                        <div className="h-full w-2/3 rounded-full bg-gradient-to-r from-sky-500 to-cyan-400 animate-pulse" />
                      </div>
                    </div>
                  </div>

                  <div className="rounded-md border border-landing-border bg-landing-surface p-3 space-y-2">
                    <p className="text-xs text-landing-muted flex items-center gap-1">
                      <Bot className="h-3 w-3" /> {m.hero.askNeo}
                    </p>
                    <p className="text-sm text-landing-text font-mono min-h-[2.5rem]">
                      {reducedMotion
                        ? m.hero.chatLines[lineIndex]
                        : m.hero.chatLines[lineIndex].slice(0, charIndex)}
                      <span className="inline-block w-0.5 h-4 bg-sky-400 ml-0.5 animate-pulse align-middle" />
                    </p>
                  </div>
                </div>
              </div>

              <FloatingCard
                className="absolute -left-4 top-8 hidden sm:block animate-landing-float-delayed"
                label={m.hero.docsIndexed}
                value="1,284"
                sample={m.hero.sample}
              />
              <FloatingCard
                className="absolute -right-2 bottom-12 hidden sm:block"
                label={m.hero.avgAnswer}
                value="1.2s"
                sample={m.hero.sample}
                delay
              />
            </div>
          </ScrollReveal>
        </div>
      </div>
    </section>
  );
}

function FloatingCard({
  label,
  value,
  sample,
  className,
  delay,
}: {
  label: string;
  value: string;
  sample: string;
  className?: string;
  delay?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-landing-border bg-landing-surface/95 backdrop-blur px-3 py-2 shadow-lg",
        delay && "animate-landing-float-delayed",
        !delay && "animate-landing-float",
        className
      )}
    >
      <p className="text-[10px] uppercase tracking-wider text-landing-muted">
        {label} · {sample}
      </p>
      <p className="text-lg font-bold text-landing-text font-mono">{value}</p>
    </div>
  );
}
