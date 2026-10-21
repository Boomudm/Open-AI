import { cn } from "@/lib/cn";
import Link from "next/link";

export function AuthDivider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 my-6">
      <div className="auth-divider-line flex-1 h-px" />
      <span className="auth-divider-label">{label}</span>
      <div className="auth-divider-line flex-1 h-px" />
    </div>
  );
}

export function AuthTab({
  active,
  onClick,
  children,
  href,
}: {
  active: boolean;
  onClick?: () => void;
  href?: string;
  children: React.ReactNode;
}) {
  const className = cn(
    "auth-tab text-xl font-medium tracking-tighter text-center transition-colors",
    active ? "auth-tab-active" : "auth-tab-inactive"
  );

  if (href && !active) {
    return (
      <Link href={href} className={className}>
        {children}
      </Link>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={className}
      aria-current={active ? "page" : undefined}
    >
      {children}
    </button>
  );
}
