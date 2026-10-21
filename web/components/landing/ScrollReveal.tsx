"use client";

import { cn } from "@/lib/cn";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type CSSProperties,
  type ElementType,
  type ReactNode,
} from "react";

type ScrollRevealProps = {
  children: ReactNode;
  className?: string;
  /** Stagger delay in milliseconds */
  delay?: number;
  as?: ElementType;
};

/**
 * GitHub-style scroll reveal — fades and slides up when the element enters the viewport.
 */
export const ScrollReveal = forwardRef<HTMLElement, ScrollRevealProps>(function ScrollReveal(
  { children, className, delay = 0, as: Tag = "div" },
  forwardedRef
) {
  const innerRef = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);

  useImperativeHandle(forwardedRef, () => innerRef.current as HTMLElement);

  useEffect(() => {
    const el = innerRef.current;
    if (!el) return;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.12, rootMargin: "0px 0px -6% 0px" }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const Component = Tag as ElementType;

  return (
    <Component
      ref={innerRef}
      className={cn("landing-scroll-reveal", visible && "landing-scroll-reveal-visible", className)}
      style={{ "--reveal-delay": `${delay}ms` } as CSSProperties}
    >
      {children}
    </Component>
  );
});
