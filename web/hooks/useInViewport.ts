"use client";

import { useEffect, useState, type RefObject } from "react";

/** Flip true once `ref` enters (or nears) the viewport — for deferring below-fold fetches. */
export function useInViewport(
  ref: RefObject<Element | null>,
  rootMargin = "200px 0px"
): boolean {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el || visible) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setVisible(true);
      },
      { rootMargin }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, rootMargin, visible]);

  return visible;
}
