"use client";

import { cn } from "@/lib/cn";

export type NeoLogoProps = {
  className?: string;
  /** Tailwind height class, e.g. h-7 */
  heightClass?: string;
  priority?: boolean;
};

export function NeoLogo({
  className,
  heightClass = "h-7",
  priority = false,
}: NeoLogoProps) {
  return (
    <span
      className={cn("inline-flex shrink-0 items-center gap-2.5 select-none", className)}
      aria-label="Spark Ops"
      data-priority={priority || undefined}
    >
      <svg viewBox="0 0 32 32" role="img" aria-hidden="true" className={cn("w-auto shrink-0", heightClass)}>
        <defs>
          <linearGradient id="spark-mark-gradient" x1="4" y1="3" x2="28" y2="29">
            <stop stopColor="#38bdf8" />
            <stop offset="1" stopColor="#22c55e" />
          </linearGradient>
        </defs>
        <path d="M16 2.5 28 9.25v13.5L16 29.5 4 22.75V9.25L16 2.5Z" fill="url(#spark-mark-gradient)" />
        <path d="m17.7 7.2-8 10.4h5.2l-1 7.2 8.4-11h-5.4l.8-6.6Z" fill="white" fillOpacity=".96" />
      </svg>
      <span className="flex flex-col leading-none">
        <span className="text-[0.82rem] font-bold tracking-[0.2em] text-current">SPARK</span>
        <span className="mt-1 text-[0.56rem] font-semibold tracking-[0.32em] text-sky-500">OPS</span>
      </span>
    </span>
  );
}
