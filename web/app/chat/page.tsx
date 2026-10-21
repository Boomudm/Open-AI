"use client";

import { Suspense } from "react";
import { LoadingState } from "@/components/ui/State";
import ChatPageInner from "./ChatPageInner";

export default function ChatPage() {
  return (
    <Suspense fallback={<LoadingState message="Loading chat" />}>
      <ChatPageInner />
    </Suspense>
  );
}
