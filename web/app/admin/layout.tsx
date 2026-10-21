import { WorkspaceLayout } from "@/components/workspace/WorkspaceLayout";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <WorkspaceLayout>{children}</WorkspaceLayout>;
}
