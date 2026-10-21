"use client";

import {
  PRIVACY_POLICY_EFFECTIVE_DATE,
  PRIVACY_POLICY_SECTIONS,
  PRIVACY_POLICY_TITLE,
  PRIVACY_POLICY_VERSION,
} from "@/lib/privacy-policy";

export type PrivacyPolicyContentProps = {
  showHeader?: boolean;
  className?: string;
};

function sectionAnchor(title: string): string {
  const match = title.match(/^(\d+)\./);
  return match ? `section-${match[1]}` : title.replace(/\s+/g, "-").toLowerCase();
}

export function PrivacyPolicyContent({
  showHeader = true,
  className,
}: PrivacyPolicyContentProps) {
  return (
    <article className={className}>
      {showHeader && (
        <header className="mb-4 pb-3 border-b border-gemini-border/60 dark:border-gemini-dark-border/60">
          <h2 className="text-base font-medium text-gemini-text dark:text-gemini-dark-text">
            {PRIVACY_POLICY_TITLE}
          </h2>
          <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted mt-1">
            มีผลบังคับใช้ {PRIVACY_POLICY_EFFECTIVE_DATE} · เวอร์ชัน v{PRIVACY_POLICY_VERSION}
          </p>
        </header>
      )}

      <div className="space-y-4 text-sm text-gemini-text dark:text-gemini-dark-text leading-relaxed">
        {PRIVACY_POLICY_SECTIONS.map((section) => (
          <section key={section.title} id={sectionAnchor(section.title)} className="scroll-mt-24">
            <h3 className="font-medium text-gemini-text dark:text-gemini-dark-text mb-1.5">
              {section.title}
            </h3>
            {section.paragraphs.map((p) => (
              <p
                key={p.slice(0, 40)}
                className="text-gemini-muted dark:text-gemini-dark-muted mb-2 last:mb-0"
              >
                {p}
              </p>
            ))}
            {section.bullets && (
              <ul className="list-disc list-inside text-gemini-muted dark:text-gemini-dark-muted space-y-1 mt-1">
                {section.bullets.map((b) => (
                  <li key={b.slice(0, 40)}>{b}</li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
    </article>
  );
}
