import type { RepairRow } from "@/lib/api";
import { formatRepairDate } from "@/lib/analytics";

/** Thai prompt template for RAG Chat pre-fill from a repair history row. */
export function buildRepairAskPrompt(row: RepairRow): string {
  const symptom = row.symptom?.trim() || "ไม่ระบุอาการ";
  const date =
    row.repair_date != null
      ? new Date(row.repair_date).toLocaleDateString("th-TH", {
          day: "numeric",
          month: "long",
          year: "numeric",
        })
      : formatRepairDate(row.repair_date);

  return `เครื่อง ${row.machine_id} เกิดปัญหา '${symptom}' เมื่อ ${date} สาเหตุที่แท้จริงคืออะไร และควรแก้ไขอย่างไร?`;
}

/** Navigate to RAG Chat with machine scope and editable draft prompt. */
export function repairAskAiChatUrl(row: RepairRow): string {
  const params = new URLSearchParams();
  params.set("machine", row.machine_id);
  params.set("prompt", buildRepairAskPrompt(row));
  return `/chat?${params.toString()}`;
}
