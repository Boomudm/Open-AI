"use client";

import { cn } from "@/lib/cn";
import {
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactElement,
  type ReactNode,
  type Ref,
} from "react";

function assignRef<T>(ref: Ref<T> | undefined, value: T | null) {
  if (!ref) return;
  if (typeof ref === "function") {
    ref(value);
    return;
  }
  (ref as { current: T | null }).current = value;
}

function mergeRefs<T>(...refs: Array<Ref<T> | undefined | null>) {
  return (value: T | null) => {
    for (const ref of refs) assignRef(ref, value);
  };
}
import { createPortal } from "react-dom";

export type TooltipSide = "top" | "bottom" | "left" | "right";

export type TooltipProps = {
  content: ReactNode;
  children: ReactElement;
  side?: TooltipSide;
  /** Skip tooltip when the control already shows a visible label */
  disabled?: boolean;
  className?: string;
};

const GAP = 8;
const SHOW_DELAY_MS = 350;

function computeCoords(
  rect: DOMRect,
  side: TooltipSide,
  tipRect: DOMRect
): CSSProperties {
  switch (side) {
    case "bottom":
      return {
        top: rect.bottom + GAP,
        left: rect.left + rect.width / 2 - tipRect.width / 2,
      };
    case "left":
      return {
        top: rect.top + rect.height / 2 - tipRect.height / 2,
        left: rect.left - tipRect.width - GAP,
      };
    case "right":
      return {
        top: rect.top + rect.height / 2 - tipRect.height / 2,
        left: rect.right + GAP,
      };
    case "top":
    default:
      return {
        top: rect.top - tipRect.height - GAP,
        left: rect.left + rect.width / 2 - tipRect.width / 2,
      };
  }
}

function clampHorizontal(left: number, width: number): number {
  const pad = 8;
  return Math.min(Math.max(left, pad), window.innerWidth - width - pad);
}

/** Short hover hint for icon-only controls. Renders in a portal so sidebars do not clip it. */
export function Tooltip({
  content,
  children,
  side = "top",
  disabled = false,
  className,
}: TooltipProps) {
  const id = useId();
  const triggerRef = useRef<HTMLElement>(null);
  const tipRef = useRef<HTMLSpanElement>(null);
  const hideTimerRef = useRef<number | null>(null);
  const showTimerRef = useRef<number | null>(null);
  const [open, setOpen] = useState(false);
  const [style, setStyle] = useState<CSSProperties>({});

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    const tip = tipRef.current;
    if (!trigger || !tip) return;
    const rect = trigger.getBoundingClientRect();
    const tipRect = tip.getBoundingClientRect();
    const coords = computeCoords(rect, side, tipRect);
    if (typeof coords.left === "number") {
      coords.left = clampHorizontal(coords.left, tipRect.width);
    }
    setStyle({ ...coords, position: "fixed" });
  }, [side]);

  useLayoutEffect(() => {
    if (!open) return;
    updatePosition();
  }, [open, content, side, updatePosition]);

  useEffect(() => {
    if (!open) return;
    const onReposition = () => updatePosition();
    window.addEventListener("scroll", onReposition, true);
    window.addEventListener("resize", onReposition);
    return () => {
      window.removeEventListener("scroll", onReposition, true);
      window.removeEventListener("resize", onReposition);
    };
  }, [open, updatePosition]);

  const clearTimers = useCallback(() => {
    if (showTimerRef.current) window.clearTimeout(showTimerRef.current);
    if (hideTimerRef.current) window.clearTimeout(hideTimerRef.current);
    showTimerRef.current = null;
    hideTimerRef.current = null;
  }, []);

  const show = useCallback(() => {
    if (disabled || content == null || content === "") return;
    clearTimers();
    showTimerRef.current = window.setTimeout(() => setOpen(true), SHOW_DELAY_MS);
  }, [clearTimers, content, disabled]);

  const hide = useCallback(() => {
    clearTimers();
    setOpen(false);
  }, [clearTimers]);

  useEffect(() => () => clearTimers(), [clearTimers]);

  if (!isValidElement(children)) return children;

  type TriggerProps = {
    ref?: React.Ref<HTMLElement>;
    onMouseEnter?: (event: React.MouseEvent<HTMLElement>) => void;
    onMouseLeave?: (event: React.MouseEvent<HTMLElement>) => void;
    onFocus?: (event: React.FocusEvent<HTMLElement>) => void;
    onBlur?: (event: React.FocusEvent<HTMLElement>) => void;
    "aria-describedby"?: string;
  };

  const triggerChild = children as ReactElement<TriggerProps>;

  const child = cloneElement(triggerChild, {
    ref: mergeRefs(triggerRef, (triggerChild as ReactElement & { ref?: Ref<HTMLElement> }).ref),
    onMouseEnter: (event: React.MouseEvent<HTMLElement>) => {
      triggerChild.props.onMouseEnter?.(event);
      show();
    },
    onMouseLeave: (event: React.MouseEvent<HTMLElement>) => {
      triggerChild.props.onMouseLeave?.(event);
      hide();
    },
    onFocus: (event: React.FocusEvent<HTMLElement>) => {
      triggerChild.props.onFocus?.(event);
      show();
    },
    onBlur: (event: React.FocusEvent<HTMLElement>) => {
      triggerChild.props.onBlur?.(event);
      hide();
    },
    "aria-describedby": open ? id : undefined,
  });

  const tip =
    open && typeof document !== "undefined"
      ? createPortal(
          <span
            id={id}
            ref={tipRef}
            role="tooltip"
            style={style}
            className={cn(
              "z-[10000] pointer-events-none max-w-[260px] rounded-md px-2.5 py-1.5",
              "text-xs font-normal leading-snug whitespace-normal text-center",
              "bg-gemini-text dark:bg-gemini-dark-text text-gemini-bg dark:text-gemini-dark-bg",
              "shadow-lg border border-black/10 dark:border-white/10",
              className
            )}
          >
            {content}
          </span>,
          document.body
        )
      : null;

  return (
    <>
      {child}
      {tip}
    </>
  );
}
