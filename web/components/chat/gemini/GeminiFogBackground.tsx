"use client";

/** Misty glow — empty new-chat welcome only (parent unmounts after first message). */
export function GeminiFogBackground() {
  return (
    <div
      className="pointer-events-none absolute inset-0 overflow-hidden"
      aria-hidden
    >
      <div className="gemini-fog-blob gemini-fog-blob-primary opacity-100" />
      <div className="gemini-fog-blob gemini-fog-blob-secondary opacity-90" />
      <div className="gemini-fog-blob gemini-fog-blob-accent opacity-80" />
      <div className="gemini-fog-vignette absolute inset-0" />
    </div>
  );
}
