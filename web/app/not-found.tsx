import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-gemini-sidebar dark:bg-gemini-dark-bg flex flex-col items-center justify-center p-6 text-center gemini-theme-transition">
      <p className="text-6xl font-normal text-gemini-muted dark:text-gemini-dark-muted tabular-nums">
        404
      </p>
      <h1 className="text-lg font-medium text-gemini-text dark:text-gemini-dark-text mt-4">
        ไม่พบหน้านี้
      </h1>
      <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted mt-2 max-w-sm">
        ลิงก์อาจไม่ถูกต้องหรือหน้านี้ถูกย้ายแล้ว
      </p>
      <div className="mt-6 flex flex-wrap items-center justify-center gap-4">
        <Link
          href="/"
          className="min-h-[44px] px-5 py-2 rounded-full bg-gemini-blue text-white text-sm font-medium hover:opacity-90 gemini-focus-ring inline-flex items-center"
        >
          หน้าแรก
        </Link>
        <Link
          href="/chat"
          className="text-sm text-gemini-blue dark:text-gemini-dark-blue hover:underline min-h-[44px] inline-flex items-center"
        >
          ไปแชท
        </Link>
      </div>
    </div>
  );
}
