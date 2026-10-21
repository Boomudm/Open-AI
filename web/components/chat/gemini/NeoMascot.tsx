"use client";

import { cn } from "@/lib/cn";
import Image from "next/image";

const NEO_MASCOT_SRC = "/neo/neo-head.png";

export type NeoMascotAnimation = "idle" | "thinking" | "bounce";

export type NeoMascotProps = {
  className?: string;
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  animation?: NeoMascotAnimation;
  priority?: boolean;
};

const SIZE_CLASS: Record<NonNullable<NeoMascotProps["size"]>, string> = {
  xs: "h-8 w-8",
  sm: "h-12 w-12",
  md: "h-24 w-24",
  lg: "h-36 w-36",
  xl: "h-48 w-48 sm:h-56 sm:w-56",
};

const ANIMATION_CLASS: Record<NeoMascotAnimation, string> = {
  idle: "animate-neo-float",
  thinking: "animate-neo-think",
  bounce: "animate-neo-bounce",
};

export function NeoMascot({
  className,
  size = "md",
  animation = "idle",
  priority = false,
}: NeoMascotProps) {
  return (
    <div
      className={cn(
        "relative shrink-0 pointer-events-none select-none",
        SIZE_CLASS[size],
        ANIMATION_CLASS[animation],
        className
      )}
      aria-hidden
    >
      <Image
        src={NEO_MASCOT_SRC}
        alt=""
        fill
        priority={priority}
        sizes="(max-width: 640px) 192px, 224px"
        className="object-contain object-bottom drop-shadow-sm"
      />
    </div>
  );
}
