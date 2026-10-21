import { redirect } from "next/navigation";

/** Root URL is handled by middleware; fallback redirect for edge cases. */
export default function RootPage() {
  redirect("/login");
}
