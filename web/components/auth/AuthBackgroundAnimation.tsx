"use client";

import { cn } from "@/lib/cn";

type Particle = {
  left: number;
  top: number;
  size: number;
  delay: number;
  duration: number;
  tone: "blue" | "green" | "purple";
};

/** Deterministic layout — stable across renders, no hydration flicker. */
const PARTICLES: Particle[] = [
  { left: 8, top: 82, size: 3, delay: 0, duration: 14, tone: "blue" },
  { left: 14, top: 68, size: 2, delay: 2.1, duration: 16, tone: "green" },
  { left: 22, top: 91, size: 2, delay: 4.5, duration: 13, tone: "purple" },
  { left: 31, top: 74, size: 3, delay: 1.2, duration: 15, tone: "blue" },
  { left: 38, top: 58, size: 2, delay: 6.8, duration: 17, tone: "green" },
  { left: 45, top: 86, size: 2, delay: 3.4, duration: 12, tone: "blue" },
  { left: 52, top: 63, size: 3, delay: 8.2, duration: 18, tone: "purple" },
  { left: 58, top: 79, size: 2, delay: 0.6, duration: 14, tone: "green" },
  { left: 64, top: 52, size: 2, delay: 5.5, duration: 16, tone: "blue" },
  { left: 71, top: 88, size: 3, delay: 7.1, duration: 13, tone: "green" },
  { left: 76, top: 66, size: 2, delay: 2.8, duration: 15, tone: "purple" },
  { left: 83, top: 48, size: 2, delay: 9.4, duration: 17, tone: "blue" },
  { left: 88, top: 76, size: 3, delay: 4.0, duration: 14, tone: "green" },
  { left: 92, top: 61, size: 2, delay: 11.2, duration: 16, tone: "purple" },
  { left: 18, top: 44, size: 2, delay: 10.5, duration: 18, tone: "blue" },
  { left: 42, top: 38, size: 2, delay: 12.0, duration: 15, tone: "green" },
  { left: 67, top: 42, size: 2, delay: 13.5, duration: 14, tone: "purple" },
  { left: 6, top: 55, size: 2, delay: 14.2, duration: 16, tone: "blue" },
  { left: 55, top: 32, size: 2, delay: 15.8, duration: 17, tone: "green" },
  { left: 79, top: 35, size: 2, delay: 16.4, duration: 13, tone: "blue" },
];

const TONE_CLASS: Record<Particle["tone"], string> = {
  blue: "bg-blue-400/70 shadow-[0_0_10px_rgba(88,166,255,0.5)]",
  green: "bg-green-400/70 shadow-[0_0_10px_rgba(63,185,80,0.5)]",
  purple: "bg-purple-400/60 shadow-[0_0_10px_rgba(163,113,247,0.45)]",
};

/**
 * Full-screen login animation — drifting aurora, rising sensor particles,
 * soft pulse rings. Factory telemetry feel (distinct from knowledge-flow curves).
 */
export function AuthBackgroundAnimation() {
  return (
    <div className="absolute inset-0 overflow-hidden">
      <AuthAurora />
      <AuthPulseRings />
      <AuthParticleField />
      <AuthDataSweep />
    </div>
  );
}

function AuthAurora() {
  return (
    <div className="absolute inset-0">
      <div
        className="auth-aurora-band auth-aurora-band-1 absolute -left-[20%] top-[8%] h-[42%] w-[140%] rounded-[100%] opacity-40"
        style={{
          background:
            "linear-gradient(105deg, transparent 0%, rgba(88,166,255,0.22) 35%, rgba(56,139,253,0.12) 55%, transparent 80%)",
        }}
      />
      <div
        className="auth-aurora-band auth-aurora-band-2 absolute -right-[15%] top-[28%] h-[38%] w-[130%] rounded-[100%] opacity-35"
        style={{
          background:
            "linear-gradient(250deg, transparent 0%, rgba(63,185,80,0.18) 40%, rgba(46,160,67,0.1) 60%, transparent 85%)",
        }}
      />
      <div
        className="auth-aurora-band auth-aurora-band-3 absolute left-[5%] bottom-[5%] h-[45%] w-[120%] rounded-[100%] opacity-30"
        style={{
          background:
            "linear-gradient(15deg, transparent 0%, rgba(163,113,247,0.14) 45%, rgba(88,166,255,0.08) 70%, transparent 90%)",
        }}
      />
    </div>
  );
}

function AuthPulseRings() {
  return (
    <div className="absolute left-[22%] top-1/2 -translate-x-1/2 -translate-y-1/2 max-lg:left-[50%]">
      {[0, 2.4, 4.8].map((delay) => (
        <div
          key={delay}
          className="auth-pulse-ring absolute left-1/2 top-1/2 h-48 w-48 -translate-x-1/2 -translate-y-1/2 rounded-full border border-blue-400/20"
          style={{ animationDelay: `${delay}s` }}
        />
      ))}
      <div className="relative h-2 w-2 rounded-full bg-blue-400/50 shadow-[0_0_16px_rgba(88,166,255,0.6)] auth-pulse-core" />
    </div>
  );
}

function AuthParticleField() {
  return (
    <div className="absolute inset-0">
      {PARTICLES.map((p, i) => (
        <span
          key={i}
          className={cn(
            "auth-particle absolute rounded-full",
            TONE_CLASS[p.tone]
          )}
          style={{
            left: `${p.left}%`,
            top: `${p.top}%`,
            width: p.size,
            height: p.size,
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.duration}s`,
          }}
        />
      ))}
    </div>
  );
}

function AuthDataSweep() {
  return (
    <>
      <div className="auth-data-sweep auth-data-sweep-1 absolute inset-y-0 w-px bg-gradient-to-b from-transparent via-blue-400/25 to-transparent" />
      <div className="auth-data-sweep auth-data-sweep-2 absolute inset-y-0 w-px bg-gradient-to-b from-transparent via-green-400/20 to-transparent" />
      <div className="auth-scan-line absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-landing-cta/25 to-transparent" />
    </>
  );
}
