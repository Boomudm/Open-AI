"use client";

import { useLandingMessages } from "@/providers/LocaleProvider";

export function LandingMarquee() {
  const m = useLandingMessages();
  const row = [...m.marquee, ...m.marquee];

  return (
    <section className="relative border-y border-landing-border bg-landing-surface/50 overflow-hidden py-4">
      <div className="flex animate-landing-marquee whitespace-nowrap">
        {row.map((tag, i) => (
          <span
            key={`${tag}-${i}`}
            className="mx-6 inline-flex items-center gap-2 text-sm font-medium text-landing-muted"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-sky-400 shrink-0" />
            {tag}
          </span>
        ))}
      </div>
    </section>
  );
}
