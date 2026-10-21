"use client";

import { AuthBackground } from "@/components/auth/AuthBackground";
import { AuthHero } from "@/components/auth/AuthHero";
import { AuthThemeToggle } from "@/components/auth/AuthThemeToggle";
import { NeoLogo } from "@/components/chat/gemini/NeoLogo";
import { cn } from "@/lib/cn";
import type { ReactNode } from "react";

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div
      data-testid="auth-page"
      className="auth-page relative flex min-h-[100dvh] flex-col overflow-hidden"
    >
      <AuthBackground />
      <AuthThemeToggle />
      <div className="relative flex flex-grow items-center justify-center flex-col gap-8 px-4 py-8 sm:gap-12 sm:px-6 sm:py-14 lg:px-12 lg:flex-row lg:items-center lg:gap-12 lg:py-16 2xl:gap-32">
        <AuthHero />
        <div className="z-10 w-full max-w-[500px] lg:mb-16 lg:flex-grow">
          <div className="mb-8 flex justify-center lg:hidden">
            <NeoLogo heightClass="h-8" priority />
          </div>
          {children}
        </div>
      </div>
    </div>
  );
}

export function AuthPanel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "auth-panel w-full overflow-hidden rounded-xl border",
        "px-6 py-7 sm:px-10 sm:py-9",
        className
      )}
    >
      {children}
    </div>
  );
}

export function AuthCard({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <AuthPanel className={className}>{children}</AuthPanel>;
}

export { NeoLogo };
