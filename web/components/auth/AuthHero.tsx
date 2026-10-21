"use client";

const TRUSTED_LABELS = [
  "Hybrid RAG",
  "Qdrant",
  "Factory RBAC",
  "Celery",
  "Text-to-SQL",
  "On-prem",
  "15 doc types",
  "Cross-encoder",
];

/** LangSmith-style left marketing column on /login. */
export function AuthHero() {
  return (
    <div className="pointer-events-none max-w-[520px] flex flex-col lg:grid lg:grid-rows-[1fr_auto] lg:gap-[95px] lg:self-stretch select-none">
      <div className="hidden lg:block space-y-4">
        <p className="text-base font-semibold tracking-[0.18em] text-[var(--auth-text)]">SPARK OPS</p>
        <h1 className="tracking-tighter font-normal max-w-[520px] text-balance text-[42px] leading-[1.1] text-[var(--auth-headline)] xl:text-[57px]">
          The platform for plant operations
        </h1>
        <p className="text-balance font-mono text-base text-[var(--auth-sub)] pb-2 lg:text-left">
          ค้นหาคู่มือ ถาม AI และติดตามองค์ความรู้หน้างาน จากข้อมูลในเครือข่ายของคุณ
        </p>
      </div>

      <div className="hidden lg:flex flex-col gap-6 items-stretch">
        <p className="text-sm text-[var(--auth-muted)]">Trusted by</p>
        <div className="grid grid-cols-4 gap-x-5 gap-y-5">
          {TRUSTED_LABELS.map((label) => (
            <span
              key={label}
              className="text-sm font-semibold tracking-wide text-[var(--auth-muted)] uppercase"
            >
              {label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
