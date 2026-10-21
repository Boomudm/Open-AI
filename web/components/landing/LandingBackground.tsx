"use client";

import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";
import { cn } from "@/lib/cn";

export function LandingBackground() {
  const reducedMotion = usePrefersReducedMotion();

  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden" aria-hidden>
      <div className="landing-grid-bg absolute inset-0" />
      <div className={cn("landing-hero-glow absolute inset-0", reducedMotion && "opacity-60")} />

      {!reducedMotion && (
        <>
          <div
            className="landing-bg-orb absolute -top-32 -left-32 h-[480px] w-[480px] rounded-full opacity-35 blur-3xl animate-landing-pulse-glow"
            style={{ background: "radial-gradient(circle, rgba(14,165,233,0.55) 0%, transparent 70%)" }}
          />
          <div
            className="landing-bg-orb absolute top-1/3 -right-24 h-[400px] w-[400px] rounded-full opacity-28 blur-3xl animate-landing-pulse-glow max-md:hidden"
            style={{
              background: "radial-gradient(circle, rgba(34,211,238,0.5) 0%, transparent 70%)",
              animationDelay: "1.5s",
            }}
          />
          <div
            className="landing-bg-orb absolute bottom-0 left-1/3 h-[360px] w-[360px] rounded-full opacity-22 blur-3xl animate-landing-pulse-glow max-md:hidden"
            style={{
              background: "radial-gradient(circle, rgba(29,78,216,0.45) 0%, transparent 70%)",
              animationDelay: "3s",
            }}
          />

          <div className="landing-bg-orb absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-[600px] w-[600px] animate-landing-orbit opacity-[0.08] max-md:hidden">
            <div className="absolute top-0 left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-sky-400" />
            <div className="absolute bottom-0 left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-cyan-400" />
            <div className="absolute top-1/2 left-0 h-2 w-2 -translate-y-1/2 rounded-full bg-blue-500" />
            <div className="absolute top-1/2 right-0 h-2 w-2 -translate-y-1/2 rounded-full bg-sky-300" />
            <div className="absolute inset-8 rounded-full border border-dashed border-landing-border" />
          </div>
        </>
      )}
    </div>
  );
}
