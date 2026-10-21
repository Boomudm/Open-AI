"use client";

import { cn } from "@/lib/cn";
import { Eye, EyeOff } from "lucide-react";
import { forwardRef, useState, type InputHTMLAttributes } from "react";

export type GeminiAuthInputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
  variant?: "default" | "auth";
  showPasswordToggle?: boolean;
};

export const GeminiAuthInput = forwardRef<HTMLInputElement, GeminiAuthInputProps>(
  function GeminiAuthInput(
    {
      label,
      error,
      className,
      id,
      type,
      variant = "default",
      showPasswordToggle = false,
      ...props
    },
    ref
  ) {
    const inputId = id || label.toLowerCase().replace(/\s+/g, "-");
    const [revealed, setRevealed] = useState(false);
    const isPassword = type === "password";
    const resolvedType =
      isPassword && showPasswordToggle ? (revealed ? "text" : "password") : type;
    const isAuth = variant === "auth";

    return (
      <div className="w-full">
        <label
          htmlFor={inputId}
          className={cn(
            isAuth
              ? "auth-field-label"
              : "block text-sm mb-1.5 text-gemini-text dark:text-gemini-dark-text font-medium gemini-theme-transition"
          )}
        >
          {label}
        </label>
        {isAuth ? (
          <div
            className={cn(
              "auth-input-wrap",
              error && "border-red-500 focus-within:border-red-500 focus-within:shadow-[0_0_0_2px_rgba(239,68,68,0.25)]"
            )}
          >
            <input
              ref={ref}
              id={inputId}
              type={resolvedType}
              className={cn(showPasswordToggle && isPassword && "pr-0", className)}
              aria-invalid={!!error}
              {...props}
            />
            {showPasswordToggle && isPassword && (
              <button
                type="button"
                onClick={() => setRevealed((v) => !v)}
                className="mr-2 p-1.5 rounded-md text-[var(--auth-muted)] hover:text-[var(--auth-text)] transition-colors shrink-0"
                aria-label={revealed ? "Hide password" : "Show password"}
                tabIndex={-1}
              >
                {revealed ? (
                  <EyeOff className="h-4 w-4" aria-hidden />
                ) : (
                  <Eye className="h-4 w-4" aria-hidden />
                )}
              </button>
            )}
          </div>
        ) : (
          <div className="relative">
            <input
              ref={ref}
              id={inputId}
              type={resolvedType}
              className={cn(
                "w-full h-11 px-3 text-sm transition-all duration-200 focus:outline-none",
                "rounded-lg gemini-theme-transition",
                "bg-gemini-bg dark:bg-gemini-dark-bg",
                "text-gemini-text dark:text-gemini-dark-text",
                "placeholder:text-gemini-muted dark:placeholder:text-gemini-dark-muted",
                "border",
                error
                  ? "border-red-500 focus:border-red-500 focus:ring-1 focus:ring-red-500"
                  : "border-gemini-border dark:border-gemini-dark-border focus:border-gemini-blue dark:focus:border-gemini-dark-blue focus:ring-1 focus:ring-gemini-blue dark:focus:ring-gemini-dark-blue",
                showPasswordToggle && isPassword && "pr-10",
                className
              )}
              aria-invalid={!!error}
              {...props}
            />
            {showPasswordToggle && isPassword && (
              <button
                type="button"
                onClick={() => setRevealed((v) => !v)}
                className={cn(
                  "absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md",
                  "text-landing-muted hover:text-landing-text transition-colors"
                )}
                aria-label={revealed ? "Hide password" : "Show password"}
                tabIndex={-1}
              >
                {revealed ? (
                  <EyeOff className="h-4 w-4" aria-hidden />
                ) : (
                  <Eye className="h-4 w-4" aria-hidden />
                )}
              </button>
            )}
          </div>
        )}
        {error && (
          <p className="mt-1.5 text-xs text-red-500" role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }
);
