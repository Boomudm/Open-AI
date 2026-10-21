"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function GlobalError({
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
    <html lang="th">
      <body className="min-h-screen bg-gemini-sidebar flex flex-col items-center justify-center p-6 text-center font-sans text-gemini-text">
        <h1 className="text-lg font-medium">เกิดข้อผิดพลาดร้ายแรง</h1>
        <p className="text-sm text-gemini-muted mt-2 max-w-sm">
          แอปไม่สามารถโหลดได้ ลองรีเฟรชหรือกลับไปหน้าแรก
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => reset()}
            className="min-h-[44px] px-5 py-2 rounded-full bg-gemini-blue text-white text-sm font-medium"
          >
            ลองใหม่
          </button>
          <Link href="/" className="text-sm text-gemini-blue hover:underline min-h-[44px] inline-flex items-center">
            หน้าแรก
          </Link>
        </div>
      </body>
    </html>
  );
}
