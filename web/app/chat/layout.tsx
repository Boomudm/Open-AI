import { ReadWorkspaceLayout } from "@/components/workspace/WorkspaceLayout";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return <ReadWorkspaceLayout>{children}</ReadWorkspaceLayout>;
}
