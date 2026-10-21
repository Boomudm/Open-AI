"use client";

import { NeoLogo } from "@/components/chat/gemini/NeoLogo";

export function ChatWelcomeState() {
  return (
    <div className="relative flex w-full flex-col items-center gap-4 text-center font-sans">
      <NeoLogo heightClass="h-14 sm:h-16" priority />
      <p className="max-w-md text-sm text-gemini-text-secondary dark:text-gemini-dark-text-secondary">
        ผู้ช่วยความรู้สำหรับงานโรงงาน เอกสาร และการบำรุงรักษา
      </p>
    </div>
  );
}
