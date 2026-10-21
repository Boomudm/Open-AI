import { cn } from "@/lib/cn";
import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";

export type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  error?: string;
  hint?: string;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
};

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  {
    label,
    error,
    hint,
    leftIcon,
    rightIcon,
    className,
    id,
    ...props
  },
  ref
) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");

  return (
    <div className="flex flex-col gap-1.5 w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="text-xs font-mono uppercase tracking-wider text-spark-text-secondary"
        >
          {label}
        </label>
      )}
      <div className="relative flex items-center">
        {leftIcon && (
          <span className="absolute left-2.5 text-spark-text-secondary pointer-events-none">
            {leftIcon}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            "w-full h-9 bg-spark-bg/60 backdrop-blur-sm border rounded-spark-md",
            "text-sm text-spark-text-primary font-sans placeholder:text-spark-text-muted",
            "transition-colors duration-fast spark-focus-ring",
            error
              ? "border-spark-critical"
              : "border-spark-border hover:border-spark-border-strong focus:border-spark-accent",
            leftIcon ? "pl-8 pr-3" : "px-3",
            rightIcon ? "pr-8" : undefined,
            className
          )}
          aria-invalid={!!error}
          aria-describedby={
            error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined
          }
          {...props}
        />
        {rightIcon && (
          <span className="absolute right-2.5 text-spark-text-secondary pointer-events-none">
            {rightIcon}
          </span>
        )}
      </div>
      {error && (
        <p
          id={`${inputId}-error`}
          className="text-xs text-spark-critical font-mono"
          role="alert"
        >
          {error}
        </p>
      )}
      {hint && !error && (
        <p id={`${inputId}-hint`} className="text-xs text-spark-text-muted font-sans">
          {hint}
        </p>
      )}
    </div>
  );
});

export type SelectProps = InputHTMLAttributes<HTMLSelectElement> & {
  label?: string;
  error?: string;
  options: { value: string; label: string }[];
};

export function Select({
  label,
  error,
  options,
  className,
  id,
  ...props
}: SelectProps) {
  const selectId = id || label?.toLowerCase().replace(/\s+/g, "-");

  return (
    <div className="flex flex-col gap-1.5 w-full">
      {label && (
        <label
          htmlFor={selectId}
          className="text-xs font-mono uppercase tracking-wider text-spark-text-secondary"
        >
          {label}
        </label>
      )}
      <select
        id={selectId}
        className={cn(
          "w-full h-9 bg-spark-bg/60 backdrop-blur-sm border rounded-spark-md px-3",
          "text-sm text-spark-text-primary font-mono",
          "transition-colors duration-fast spark-focus-ring appearance-none",
          "bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%2712%27 height=%2712%27 viewBox=%270 0 24 24%27 fill=%27none%27 stroke=%27%236B7A8D%27 stroke-width=%272%27%3E%3Cpath d=%27m6 9 6 6 6-6%27/%3E%3C/svg%3E')] bg-no-repeat bg-[right_0.5rem_center]",
          error
            ? "border-spark-critical"
            : "border-spark-border hover:border-spark-border-strong focus:border-spark-accent",
          className
        )}
        aria-invalid={!!error}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && (
        <p className="text-xs text-spark-critical font-mono" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
