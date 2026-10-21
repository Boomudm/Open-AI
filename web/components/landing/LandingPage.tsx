import { LandingBackground } from "@/components/landing/LandingBackground";
import { LandingBelowFold } from "@/components/landing/LandingBelowFold";
import { LandingHero } from "@/components/landing/LandingHero";
import { LandingNav } from "@/components/landing/LandingNav";

export function LandingPage() {
  return (
    <div
      data-testid="landing-page"
      className="landing-page relative min-h-[100dvh] flex flex-col bg-landing-bg text-landing-text"
    >
      <LandingBackground />
      <div className="relative z-10 flex flex-col flex-1">
        <LandingNav />
        <main className="flex-1">
          <LandingHero />
          <LandingBelowFold />
        </main>
      </div>
    </div>
  );
}
