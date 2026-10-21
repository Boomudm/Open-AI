"use client";

import { useEffect, useState } from "react";

type LandingHeroRotatingWordProps = {
  words: string[];
};

export function LandingHeroRotatingWord({ words }: LandingHeroRotatingWordProps) {
  const [index, setIndex] = useState(0);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    setIndex(0);
    setVisible(true);
  }, [words]);

  useEffect(() => {
    if (words.length === 0) return;
    let fadeTimeout: ReturnType<typeof setTimeout> | undefined;
    const interval = setInterval(() => {
      setVisible(false);
      fadeTimeout = setTimeout(() => {
        setIndex((i) => (i + 1) % words.length);
        setVisible(true);
      }, 280);
    }, 3200);
    return () => {
      clearInterval(interval);
      if (fadeTimeout !== undefined) clearTimeout(fadeTimeout);
    };
  }, [words]);

  return (
    <span
      className="landing-gradient-text transition-all duration-300"
      style={{ opacity: visible ? 1 : 0, transform: visible ? "translateY(0)" : "translateY(4px)" }}
    >
      {words[index] ?? ""}
    </span>
  );
}
