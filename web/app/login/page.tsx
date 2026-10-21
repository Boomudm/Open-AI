import { GuestGuard } from "@/components/auth/GuestGuard";
import { AuthForm } from "@/components/auth/AuthForm";

export default function LoginPage() {
  return (
    <GuestGuard>
      <AuthForm initialMode="signin" />
    </GuestGuard>
  );
}
