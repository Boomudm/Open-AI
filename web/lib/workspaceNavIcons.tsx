"use client";

import type { WorkspaceNavIcon } from "@/lib/workspaceNav";
import {
  Activity,
  Building2,
  ClipboardList,
  Cog,
  FolderOpen,
  MessageSquare,
  MessageSquareWarning,
  SquarePen,
  Package,
  Shield,
  Upload,
  Wrench,
} from "lucide-react";
import type { ReactNode } from "react";

const ICON_CLASS = "h-4 w-4";

export function workspaceNavIcon(key: WorkspaceNavIcon): ReactNode {
  const props = { className: ICON_CLASS, strokeWidth: 1.75 as const };
  switch (key) {
    case "messageSquare":
      return <MessageSquare {...props} />;
    case "squarePen":
      return <SquarePen {...props} />;
    case "wrench":
      return <Wrench {...props} />;
    case "folderOpen":
      return <FolderOpen {...props} />;
    case "package":
      return <Package {...props} />;
    case "cog":
      return <Cog {...props} />;
    case "clipboardList":
      return <ClipboardList {...props} />;
    case "upload":
      return <Upload {...props} />;
    case "messageSquareWarning":
      return <MessageSquareWarning {...props} />;
    case "building2":
      return <Building2 {...props} />;
    case "shield":
      return <Shield {...props} />;
    case "activity":
      return <Activity {...props} />;
  }
}
