"use client";

import { NeoLogo } from "@/components/chat/gemini/NeoLogo";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/cn";
import { useLandingMessages } from "@/providers/LocaleProvider";
import { Menu, Moon, Sun, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type LandingNavProps = {
  variant?: "marketing" | "auth";
};

export function LandingNav({ variant = "marketing" }: LandingNavProps) {
  const m = useLandingMessages();
  const isAuth = variant === "auth";
  const { theme, toggle } = useTheme();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const navLinks = useMemo(
    () =>
      [
        { href: "#how-it-works", label: m.nav.pipeline },
        { href: "#documents", label: m.nav.documents },
        { href: "#capabilities", label: m.nav.capabilities },
        { href: "#personas", label: m.nav.personas },
        { href: "#stack", label: m.nav.stack },
      ] as const,
    [m.nav]
  );

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!mobileOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  const closeMobile = () => setMobileOpen(false);

  return (
    <header
      className={cn(
        "sticky top-0 z-50 transition-all duration-300",
        scrolled
          ? "border-b border-landing-border bg-landing-bg/90 backdrop-blur-lg shadow-lg shadow-sky-950/20"
          : "border-b border-transparent bg-transparent"
      )}
    >
      <div className="mx-auto flex min-h-16 max-w-7xl items-center justify-between gap-3 sm:gap-4 px-4 sm:px-6 lg:px-8 py-2">
        <Link href="/" className="flex items-center gap-2 shrink-0" aria-label="Neo Chat home">
          <NeoLogo heightClass="h-6 sm:h-7" priority />
        </Link>

        {!isAuth && (
          <nav className="hidden md:flex items-center gap-6 lg:gap-8 text-sm text-landing-muted">
            {navLinks.map((link) => (
              <a key={link.href} href={link.href} className="hover:text-landing-text transition-colors">
                {link.label}
              </a>
            ))}
          </nav>
        )}

        <div className="flex items-center gap-2 sm:gap-3">
          {!isAuth && (
            <button
              type="button"
              onClick={() => setMobileOpen((open) => !open)}
              className={cn(
                "md:hidden h-11 w-11 flex items-center justify-center rounded-md",
                "border border-landing-border text-landing-muted",
                "hover:text-landing-text hover:bg-landing-surface transition-colors"
              )}
              aria-label={mobileOpen ? m.nav.closeMenu : m.nav.openMenu}
              aria-expanded={mobileOpen}
            >
              {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          )}
          <LanguageSwitcher ariaLabel={m.nav.language} />
          <button
            type="button"
            onClick={toggle}
            className={cn(
              "h-11 w-11 flex items-center justify-center rounded-md",
              "border border-landing-border text-landing-muted",
              "hover:text-landing-text hover:bg-landing-surface transition-colors"
            )}
            aria-label={theme === "dark" ? m.nav.switchLight : m.nav.switchDark}
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          {isAuth ? (
            <span
              aria-current="page"
              className="landing-btn-outline rounded-md opacity-90"
            >
              {m.nav.signIn}
            </span>
          ) : (
            <Link
              href="/login"
              className="landing-btn-outline rounded-md"
            >
              {m.nav.signIn}
            </Link>
          )}
          {isAuth ? (
            <Link
              href="/"
              className="landing-btn-cta rounded-md"
            >
              {m.nav.home}
            </Link>
          ) : (
            <a
              href="#how-it-works"
              className="landing-btn-cta rounded-md"
            >
              {m.nav.explore}
            </a>
          )}
        </div>
      </div>

      {mobileOpen && (
        <>
          <button
            type="button"
            aria-label={m.nav.closeMenu}
            className="fixed inset-0 z-40 bg-black/40 md:hidden"
            onClick={closeMobile}
          />
          <nav
            className={cn(
              "md:hidden relative z-50 border-t border-landing-border bg-landing-bg/95 backdrop-blur-lg",
              "px-4 py-3 flex flex-col gap-1"
            )}
          >
            {!isAuth &&
              navLinks.map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  onClick={closeMobile}
                  className="rounded-md px-3 py-2.5 text-sm font-medium text-landing-muted hover:text-landing-text hover:bg-landing-surface transition-colors"
                >
                  {link.label}
                </a>
              ))}
            {isAuth ? (
              <>
                <span className="mt-2 inline-flex h-11 items-center justify-center px-3 text-sm font-medium landing-btn-outline rounded-md opacity-90">
                  {m.nav.signIn}
                </span>
                <Link
                  href="/"
                  onClick={closeMobile}
                  className="inline-flex h-11 items-center justify-center px-3 text-sm font-semibold landing-btn-cta rounded-md"
                >
                  {m.nav.home}
                </Link>
              </>
            ) : (
              <Link
                href="/login"
                onClick={closeMobile}
                className="mt-2 inline-flex h-11 items-center justify-center px-3 text-sm font-medium landing-btn-outline rounded-md"
              >
                {m.nav.signIn}
              </Link>
            )}
          </nav>
        </>
      )}
    </header>
  );
}
