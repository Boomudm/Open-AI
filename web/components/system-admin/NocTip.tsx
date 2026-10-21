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
import { createPortal } from "react-dom";

export type NocTipContent = {
  title: string;
  lines?: string[];
};

type NocTipProps = {
  content: NocTipContent | null | undefined;
  children: ReactElement;
  side?: "top" | "bottom" | "left" | "right";
  className?: string;
  disabled?: boolean;
};

function assignRef<T>(ref: Ref<T> | undefined, value: T | null) {
  if (!ref) return;
  if (typeof ref === "function") ref(value);
  else (ref as { current: T | null }).current = value;
}

function mergeRefs<T>(...refs: Array<Ref<T> | undefined | null>) {
  return (value: T | null) => {
    for (const ref of refs) assignRef(ref, value);
  };
}

const GAP = 10;
const SHOW_MS = 180;

function computeCoords(rect: DOMRect, side: NocTipProps["side"], tipRect: DOMRect): CSSProperties {
  switch (side) {
    case "bottom":
      return { top: rect.bottom + GAP, left: rect.left + rect.width / 2 - tipRect.width / 2 };
    case "left":
      return { top: rect.top + rect.height / 2 - tipRect.height / 2, left: rect.left - tipRect.width - GAP };
    case "right":
      return { top: rect.top + rect.height / 2 - tipRect.height / 2, left: rect.right + GAP };
    default:
      return { top: rect.top - tipRect.height - GAP, left: rect.left + rect.width / 2 - tipRect.width / 2 };
  }
}

export function NocTip({ content, children, side = "top", className, disabled }: NocTipProps) {
  const id = useId();
  const triggerRef = useRef<HTMLElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const showTimer = useRef<number | null>(null);
  const [open, setOpen] = useState(false);
  const [style, setStyle] = useState<CSSProperties>({});

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    const tip = tipRef.current;
    if (!trigger || !tip) return;
    const rect = trigger.getBoundingClientRect();
    const tipRect = tip.getBoundingClientRect();
    const coords = computeCoords(rect, side, tipRect);
    const left = typeof coords.left === "number"
      ? Math.min(Math.max(coords.left, 8), window.innerWidth - tipRect.width - 8)
      : coords.left;
    setStyle({ ...coords, left, position: "fixed" });
  }, [side]);

  useLayoutEffect(() => {
    if (open) updatePosition();
  }, [open, content, side, updatePosition]);

  useEffect(() => {
    if (!open) return;
    const fn = () => updatePosition();
    window.addEventListener("scroll", fn, true);
    window.addEventListener("resize", fn);
    return () => {
      window.removeEventListener("scroll", fn, true);
      window.removeEventListener("resize", fn);
    };
  }, [open, updatePosition]);

  const clearTimer = () => {
    if (showTimer.current) window.clearTimeout(showTimer.current);
    showTimer.current = null;
  };

  const show = () => {
    if (disabled || !content?.title) return;
    clearTimer();
    showTimer.current = window.setTimeout(() => setOpen(true), SHOW_MS);
  };

  const hide = () => {
    clearTimer();
    setOpen(false);
  };

  useEffect(() => () => clearTimer(), []);

  if (!isValidElement(children)) return children;

  type TriggerProps = {
    ref?: Ref<HTMLElement>;
    onMouseEnter?: (e: React.MouseEvent<HTMLElement>) => void;
    onMouseLeave?: (e: React.MouseEvent<HTMLElement>) => void;
    className?: string;
  };

  const child = children as ReactElement<TriggerProps>;
  const childRef = (child as ReactElement & { ref?: Ref<HTMLElement> }).ref;
  const wrapped = cloneElement(child, {
    ref: mergeRefs(triggerRef, childRef),
    className: cn("noc-hover-target", child.props.className, className),
    onMouseEnter: (e: React.MouseEvent<HTMLElement>) => {
      child.props.onMouseEnter?.(e);
      show();
    },
    onMouseLeave: (e: React.MouseEvent<HTMLElement>) => {
      child.props.onMouseLeave?.(e);
      hide();
    },
  });

  const tipBody: ReactNode = content ? (
    <div className="noc-tip-card">
      <p className="noc-tip-title">{content.title}</p>
      {content.lines?.map((line) => (
        <p key={line} className="noc-tip-line">
          {line}
        </p>
      ))}
    </div>
  ) : null;

  const portal =
    open && tipBody && typeof document !== "undefined"
      ? createPortal(
          <div id={id} ref={tipRef} role="tooltip" style={style} className="noc-tip-portal">
            {tipBody}
          </div>,
          document.body
        )
      : null;

  return (
    <>
      {wrapped}
      {portal}
    </>
  );
}
