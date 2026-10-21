export type WorkspaceNavIcon =
  | "messageSquare"
  | "squarePen"
  | "wrench"
  | "folderOpen"
  | "package"
  | "cog"
  | "clipboardList"
  | "upload"
  | "messageSquareWarning"
  | "building2"
  | "shield"
  | "activity";

export type WorkspaceNavItemConfig = {
  href: string;
  label: string;
  icon: WorkspaceNavIcon;
  /** Hidden unless user is admin. */
  adminOnly?: boolean;
  /** Hidden unless user is super admin (God Mode / system-admin). */
  superAdminOnly?: boolean;
  /** Hidden for read-only employees (requires write factory access). */
  writeOnly?: boolean;
  /** Visible to read-only employees in the workspace shell. */
  readAllowed?: boolean;
  /** Shown only when canUploadDocuments for selected factory. */
  uploadGated?: boolean;
};

/** Single source of truth for workspace sidebar + mobile header titles. */
export const WORKSPACE_NAV_ITEMS: WorkspaceNavItemConfig[] = [
  {
    href: "/chat",
    label: "แชท AI",
    icon: "messageSquare",
    readAllowed: true,
  },
  {
    href: "/documents",
    label: "คลังเอกสาร",
    icon: "folderOpen",
    readAllowed: true,
  },
  {
    href: "/upload",
    label: "อัปโหลดเอกสาร",
    icon: "upload",
    writeOnly: true,
    uploadGated: true,
  },
  {
    href: "/feedback",
    label: "แจ้งกลับความรู้",
    icon: "messageSquareWarning",
    writeOnly: true,
  },
  {
    href: "/machines",
    label: "เครื่องจักร",
    icon: "cog",
    writeOnly: true,
  },
  {
    href: "/admin/factories",
    label: "จัดการโรงงาน",
    icon: "building2",
    adminOnly: true,
    writeOnly: true,
  },
  {
    href: "/admin",
    label: "ผู้ดูแลระบบ",
    icon: "shield",
    adminOnly: true,
    writeOnly: true,
  },
  {
    href: "/system-admin",
    label: "ศูนย์ควบคุมระบบ",
    icon: "activity",
    adminOnly: true,
    writeOnly: true,
  },
];

/** @deprecated Use WORKSPACE_NAV_ITEMS */
export type WorkspaceNavRoute = {
  href: string;
  label: string;
};

/** @deprecated Use WORKSPACE_NAV_ITEMS */
export const WORKSPACE_NAV_ROUTES: WorkspaceNavRoute[] = WORKSPACE_NAV_ITEMS.map(
  ({ href, label }) => ({ href, label })
);

export function isWorkspaceNavActive(pathname: string, href: string): boolean {
  if (href === "/chat") return pathname === "/chat";
  if (href === "/admin") return pathname === "/admin";
  if (href === "/system-admin") return pathname.startsWith("/system-admin");
  return pathname.startsWith(href);
}

export function matchWorkspaceNavRoute(pathname: string): WorkspaceNavItemConfig | undefined {
  return WORKSPACE_NAV_ITEMS.find((item) => isWorkspaceNavActive(pathname, item.href));
}

export function getWorkspacePageTitle(pathname: string): string {
  return matchWorkspaceNavRoute(pathname)?.label ?? "Spark Ops";
}

export function filterWorkspaceNavItems(
  items: WorkspaceNavItemConfig[],
  opts: {
    isAdmin: boolean;
    isSuperAdmin: boolean;
    canWrite: boolean;
    canUpload: boolean;
  }
): WorkspaceNavItemConfig[] {
  return items.filter((item) => {
    if (item.superAdminOnly && !opts.isSuperAdmin) return false;
    if (item.adminOnly && !opts.isAdmin) return false;
    if (!opts.canWrite && !item.readAllowed) return false;
    if (item.uploadGated && !opts.canUpload) return false;
    return true;
  });
}
