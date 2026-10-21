import { PrivacyPolicyContent } from "@/components/privacy/PrivacyPolicyContent";
import { PRIVACY_POLICY_SECTIONS } from "@/lib/privacy-policy";
import Link from "next/link";

export const metadata = {
  title: "นโยบายความเป็นส่วนตัว — Neo",
};

function sectionAnchor(title: string): string {
  const match = title.match(/^(\d+)\./);
  return match ? `section-${match[1]}` : title.replace(/\s+/g, "-").toLowerCase();
}

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-gemini-sidebar dark:bg-gemini-dark-bg gemini-theme-transition">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-10">
        <nav
          aria-label="สารบัญนโยบาย"
          className="sticky top-0 z-10 -mx-1 mb-6 rounded-xl border border-gemini-border/70 dark:border-gemini-dark-border/70 bg-gemini-bg/95 dark:bg-gemini-dark-sidebar/95 backdrop-blur-md px-4 py-3 overflow-x-auto"
        >
          <p className="text-xs font-medium text-gemini-muted dark:text-gemini-dark-muted mb-2">
            สารบัญ
          </p>
          <ol className="flex gap-2 sm:flex-col sm:gap-1 text-sm min-w-max sm:min-w-0">
            {PRIVACY_POLICY_SECTIONS.map((section) => {
              const id = sectionAnchor(section.title);
              return (
                <li key={id}>
                  <a
                    href={`#${id}`}
                    className="text-gemini-blue dark:text-gemini-dark-blue hover:underline whitespace-nowrap sm:whitespace-normal"
                  >
                    {section.title.replace(/^\d+\.\s*/, "")}
                  </a>
                </li>
              );
            })}
          </ol>
        </nav>

        <div className="rounded-2xl border border-gemini-border/70 dark:border-gemini-dark-border/70 bg-gemini-bg dark:bg-gemini-dark-sidebar shadow-gemini-input dark:shadow-gemini-input-dark px-6 py-8 sm:px-8">
          <PrivacyPolicyContent />
        </div>
        <p className="mt-6 text-center text-sm text-gemini-muted dark:text-gemini-dark-muted">
          <Link
            href="/"
            className="text-gemini-blue dark:text-gemini-dark-blue hover:underline"
          >
            กลับหน้าแรก
          </Link>
          {" · "}
          <Link
            href="/login"
            className="text-gemini-blue dark:text-gemini-dark-blue hover:underline"
          >
            กลับไปหน้าเข้าสู่ระบบ
          </Link>
        </p>
      </div>
    </div>
  );
}
