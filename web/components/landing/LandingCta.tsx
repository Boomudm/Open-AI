"use client";

import { ScrollReveal } from "@/components/landing/ScrollReveal";
import { useLandingMessages } from "@/providers/LocaleProvider";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

export function LandingCta() {
  const m = useLandingMessages();

  return (
    <section className="relative overflow-hidden border-t border-landing-border">
      <div className="absolute inset-0 landing-hero-glow opacity-60" aria-hidden />
      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-20 lg:py-28">
        <ScrollReveal className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl sm:text-4xl font-semibold text-landing-text tracking-tight">
            {m.cta.title}
          </h2>
          <p className="mt-4 text-lg text-landing-muted">{m.cta.subtitle}</p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/login"
              className="group inline-flex h-12 items-center gap-2 px-6 text-sm font-semibold landing-btn-cta rounded-md shadow-lg shadow-sky-900/25"
            >
              {m.cta.getStarted}
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Link>
            <Link
              href="/login"
              className="inline-flex h-12 items-center px-6 text-sm font-medium landing-btn-outline rounded-md"
            >
              {m.cta.signIn}
            </Link>
          </div>
          <p className="mt-6 text-xs text-landing-muted">{m.cta.footnote}</p>
        </ScrollReveal>
      </div>
    </section>
  );
}
