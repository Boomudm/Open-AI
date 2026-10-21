"use client";

import dynamic from "next/dynamic";
import { useInViewport } from "@/hooks/useInViewport";
import { useRef } from "react";

const LandingMarquee = dynamic(
  () => import("@/components/landing/LandingMarquee").then((m) => m.LandingMarquee),
  { loading: () => <div className="h-16" aria-hidden /> }
);
const LandingStats = dynamic(
  () => import("@/components/landing/LandingStats").then((m) => m.LandingStats),
  { loading: () => <div className="h-48" aria-hidden /> }
);
const LandingPipeline = dynamic(
  () => import("@/components/landing/LandingPipeline").then((m) => m.LandingPipeline),
  { loading: () => <div className="h-64" aria-hidden /> }
);
const LandingDocumentTypes = dynamic(
  () => import("@/components/landing/LandingDocumentTypes").then((m) => m.LandingDocumentTypes),
  { loading: () => <div className="h-64" aria-hidden /> }
);
const LandingFeatures = dynamic(
  () => import("@/components/landing/LandingFeatures").then((m) => m.LandingFeatures),
  { loading: () => <div className="h-64" aria-hidden /> }
);
const LandingDeepDive = dynamic(
  () => import("@/components/landing/LandingDeepDive").then((m) => m.LandingDeepDive),
  { loading: () => <div className="h-64" aria-hidden /> }
);
const LandingPersonas = dynamic(
  () => import("@/components/landing/LandingPersonas").then((m) => m.LandingPersonas),
  { loading: () => <div className="h-64" aria-hidden /> }
);
const LandingNeoSection = dynamic(
  () => import("@/components/landing/LandingNeoSection").then((m) => m.LandingNeoSection),
  { loading: () => <div className="h-64" aria-hidden /> }
);
const LandingTechStack = dynamic(
  () => import("@/components/landing/LandingTechStack").then((m) => m.LandingTechStack),
  { loading: () => <div className="h-48" aria-hidden /> }
);
const LandingCta = dynamic(
  () => import("@/components/landing/LandingCta").then((m) => m.LandingCta),
  { loading: () => <div className="h-32" aria-hidden /> }
);
const LandingFooter = dynamic(
  () => import("@/components/landing/LandingFooter").then((m) => m.LandingFooter),
  { loading: () => <div className="h-24" aria-hidden /> }
);

function LazySection({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const visible = useInViewport(ref, "200px 0px");
  return <div ref={ref}>{visible ? children : null}</div>;
}

export function LandingBelowFold() {
  return (
    <>
      <LazySection>
        <LandingMarquee />
      </LazySection>
      <LazySection>
        <LandingStats />
      </LazySection>
      <LazySection>
        <LandingPipeline />
      </LazySection>
      <LazySection>
        <LandingDocumentTypes />
      </LazySection>
      <LazySection>
        <LandingFeatures />
      </LazySection>
      <LazySection>
        <LandingDeepDive />
      </LazySection>
      <LazySection>
        <LandingPersonas />
      </LazySection>
      <LazySection>
        <LandingNeoSection />
      </LazySection>
      <LazySection>
        <LandingTechStack />
      </LazySection>
      <LazySection>
        <div id="cta">
          <LandingCta />
        </div>
      </LazySection>
      <LandingFooter />
    </>
  );
}
