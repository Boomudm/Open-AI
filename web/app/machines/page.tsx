"use client";

import dynamic from "next/dynamic";

const MachinesPageInner = dynamic(
  () => import("@/components/machines/MachinesPageInner").then(m => m.MachinesPageInner),
);

export default function MachinesPage() {
  return <MachinesPageInner />;
}
