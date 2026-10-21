import { SuperAdminGuard } from "@/components/auth/SuperAdminGuard";
import type { ReactNode } from "react";
import "./noc.css";

export default function SystemAdminLayout({ children }: { children: ReactNode }) {
  return <SuperAdminGuard>{children}</SuperAdminGuard>;
}
