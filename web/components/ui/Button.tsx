import { cn } from "@/lib/cn";
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { forwardRef } from "react";
import { Tooltip } from "./Tooltip";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-spark-accent text-spark-text-inverse border border-spark-accent hover:bg-spark-accent/90",
  secondary:
    "spark-glass text-spark-text-primary border border-spark-border hover:border-spark-border-strong hover:bg-spark-hover",
  ghost:
    "bg-transparent text-spark-text-secondary border border-transparent hover:bg-spark-hover hover:text-spark-accent",
  danger:
    "bg-spark-critical-muted text-spark-critical border border-spark-critical/40 hover:border-spark-critical",
};

const sizeClasses: Record<Size, string> = {
  sm: "h-7 px-2.5 text-xs gap-1.5",
  md: "h-9 px-3.5 text-sm gap-2",
  lg: "h-11 px-4 text-sm gap-2",
};

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  /** Hover hint — useful for icon-only buttons */
  tooltip?: ReactNode;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    loading = false,
    leftIcon,
    rightIcon,
    tooltip,
    className,
    disabled,
    children,
    ...props
  },
  ref
) {
  const isDisabled = disabled || loading;

  const button = (
    <button
      ref={ref}
      type="button"
      disabled={isDisabled}
      className={cn(
        "inline-flex items-center justify-center font-mono font-medium rounded-spark-md",
        "transition-colors duration-fast spark-focus-ring",
        "disabled:opacity-40 disabled:pointer-events-none",
        variantClasses[variant],
        sizeClasses[size],
        className
      )}
      {...props}
    >
      {loading ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" aria-hidden />
      ) : (
        leftIcon
      )}
      {children}
      {!loading && rightIcon}
    </button>
  );

  if (tooltip) {
    return <Tooltip content={tooltip}>{button}</Tooltip>;
  }

  return button;
});
