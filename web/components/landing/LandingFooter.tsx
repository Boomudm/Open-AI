"use client";

import { useLandingMessages } from "@/providers/LocaleProvider";
import Link from "next/link";

export function LandingFooter() {
  const m = useLandingMessages();
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-landing-border bg-landing-bg">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-10">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-landing-muted">
            © {year} {m.footer.copyright}
          </p>
          <nav className="flex flex-wrap items-center gap-4 text-sm">
            <Link href="/privacy" className="text-landing-muted hover:text-landing-text transition-colors">
              {m.footer.privacy}
            </Link>
            <Link href="/login" className="text-landing-muted hover:text-landing-text transition-colors">
              {m.footer.signIn}
            </Link>
          </nav>
        </div>
      </div>
    </footer>
  );
}
