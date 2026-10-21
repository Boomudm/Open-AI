/** Lightweight backdrop: no client hydration or continuously animated SVG filters. */
export function AuthBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden bg-[var(--auth-bg)]" aria-hidden>
      <div className="absolute -left-[12rem] top-[8%] h-[34rem] w-[34rem] rounded-full bg-sky-500/10 blur-3xl" />
      <div className="absolute -right-[10rem] bottom-[-8rem] h-[30rem] w-[30rem] rounded-full bg-emerald-500/10 blur-3xl" />
      <div className="absolute inset-0 opacity-[0.06] [background-image:linear-gradient(rgba(125,211,252,.5)_1px,transparent_1px),linear-gradient(90deg,rgba(125,211,252,.5)_1px,transparent_1px)] [background-size:48px_48px]" />
      <div className="auth-readability-overlay absolute inset-0" />
    </div>
  );
}
