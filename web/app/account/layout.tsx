import { AuthGuard } from "@/components/auth/AuthGuard";
import { ToastProvider } from "@/components/ui/Toast";

export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <ToastProvider>
        <div className="min-h-[100dvh] bg-gemini-bg dark:bg-gemini-dark-bg gemini-theme-transition">
          {children}
        </div>
      </ToastProvider>
    </AuthGuard>
  );
}
