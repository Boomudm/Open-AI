"use client";

import { useEffect } from "react";

export function WebVitalsReporter() {
  useEffect(() => {
    import("@/lib/web-vitals").then(({ reportWebVitals }) => reportWebVitals());
  }, []);
  return null;
}
