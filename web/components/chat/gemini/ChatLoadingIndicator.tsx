export function GeminiLoadingIndicator({ label }: { label: string }) {
  return (
    <div
      className="flex justify-start w-full max-w-3xl mx-auto px-4 sm:px-6"
      aria-live="polite"
      aria-busy="true"
      data-testid="chat-thinking"
    >
      <div className="w-full max-w-[min(100%,42rem)]">
        <p className="chat-system-body chat-system-meta gemini-theme-transition">
          {label}
          <span className="typing-dots" aria-hidden />
        </p>
      </div>
    </div>
  );
}
