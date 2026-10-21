"use client";

import Link from "next/link";
import { AuthLayout, AuthPanel } from "@/components/auth/AuthLayout";
import { AuthTab } from "@/components/auth/AuthDivider";

export default function SignupPage() {
  return (
    <AuthLayout>
      <AuthPanel>
        <div className="mb-8 flex justify-center gap-4">
          <AuthTab active>Sign Up</AuthTab>
          <AuthTab active={false} href="/login">
            Log In
          </AuthTab>
        </div>

        <div className="space-y-4 text-center">
          <h1 className="text-lg font-medium text-[var(--auth-text)]">
            Accounts are created by your administrator
          </h1>
          <p className="text-sm text-[var(--auth-muted)] leading-relaxed">
            Neo Chat does not offer self-service signup — your plant admin will create an
            account and share credentials with you.
          </p>
          <Link
            href="/login"
            className="auth-continue-btn gemini-focus-ring inline-flex min-h-[2.1875rem] w-full items-center justify-center no-underline"
          >
            Back to log in
          </Link>
        </div>
      </AuthPanel>
    </AuthLayout>
  );
}
