"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="min-h-screen bg-gemini-sidebar dark:bg-gemini-dark-bg flex flex-col items-center justify-center p-6 text-center gemini-theme-transition">
      <h1 className="text-lg font-medium text-gemini-text dark:text-gemini-dark-text">
        เกิดข้อผิดพลาด
      </h1>
      <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted mt-2 max-w-sm">
        ระบบไม่สามารถแสดงหน้านี้ได้ ลองโหลดใหม่หรือกลับไปหน้าหลัก
      </p>
      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <button
          type="button"
          onClick={() => reset()}
          className="min-h-[44px] px-5 py-2 rounded-full bg-gemini-blue text-white text-sm font-medium hover:opacity-90 gemini-focus-ring"
        >
          ลองใหม่
        </button>
        <Link
          href="/chat"
          className="min-h-[44px] px-5 py-2 rounded-full border border-gemini-border dark:border-gemini-dark-border text-sm text-gemini-text dark:text-gemini-dark-text hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover gemini-focus-ring inline-flex items-center"
        >
          ไปแชท
        </Link>
        <Link
          href="/"
          className="text-sm text-gemini-blue dark:text-gemini-dark-blue hover:underline min-h-[44px] inline-flex items-center"
        >
          หน้าแรก
        </Link>
      </div>
    </div>
  );
}
