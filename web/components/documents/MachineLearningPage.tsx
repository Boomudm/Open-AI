"use client";

import { DocumentRow } from "@/components/documents/DocumentRow";
import { DocumentUploadPanel } from "@/components/documents/DocumentUploadPanel";
import { MachineCoverImage } from "@/components/documents/MachineCoverImage";
import type { IndexedDocument, Machine } from "@/lib/api";
import { cn } from "@/lib/cn";
import { documentTypeLabel } from "@/lib/document-categories";
import {
  filterMachineDocuments,
  groupByDocumentType,
} from "@/lib/documents-library";
import { MessageCircle } from "lucide-react";
import { useMemo } from "react";

export type MachineLearningPageProps = {
  machine: Machine;
  documents: IndexedDocument[];
  onOpenDoc: (doc: IndexedDocument) => void;
  onAskAi?: (machineId: string) => void;
};

function formatLatestUpdate(docs: IndexedDocument[]): string | null {
  if (docs.length === 0) return null;
  const latest = docs.reduce((a, b) =>
    a.updated_at > b.updated_at ? a : b
  );
  try {
    return new Date(latest.updated_at).toLocaleDateString("th-TH", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return null;
  }
}

export function MachineLearningPage({
  machine,
  documents,
  onOpenDoc,
  onAskAi,
}: MachineLearningPageProps) {
  const machineDocs = useMemo(
    () => filterMachineDocuments(documents, machine.machine_id),
    [documents, machine.machine_id]
  );
  const groups = useMemo(() => groupByDocumentType(machineDocs), [machineDocs]);
  const latestUpdate = formatLatestUpdate(machineDocs);

  const summaryParts: string[] = [];
  const manualCount = machineDocs.filter((d) => d.document_type === "machine_manual").length;
  const repairCount = machineDocs.filter((d) => d.document_type === "repair_history").length;
  if (manualCount) summaryParts.push(`${manualCount} คู่มือ`);
  if (repairCount) summaryParts.push(`${repairCount} ประวัติซ่อม`);
  if (machineDocs.length && !manualCount && !repairCount) {
    summaryParts.push(`${machineDocs.length} เอกสาร`);
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <DocumentUploadPanel
        title="อัปโหลดเอกสารสำหรับเครื่องนี้"
        defaultMachineId={machine.machine_id}
        defaultOpen={machineDocs.length === 0}
        defaultDocumentType="machine_manual"
        filterDocumentTypes={[
          "machine_manual",
          "sop",
          "drawing",
          "datasheet",
          "repair_history",
          "training_note",
          "inspection_report",
          "knowledge_document",
        ]}
      />
      <div className="flex flex-col sm:flex-row gap-4">
        <MachineCoverImage
          machineId={machine.machine_id}
          machineName={machine.machine_name}
          machineType={machine.machine_type}
          imageUpdatedAt={machine.image_updated_at}
          showUpload
          aspectClass="aspect-square sm:aspect-[4/3]"
          className="w-full sm:w-40 shrink-0"
        />
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold text-gemini-text dark:text-gemini-dark-text font-mono">
            {machine.machine_id}
          </h2>
          <p className="text-sm text-gemini-text dark:text-gemini-dark-text">
            {machine.machine_name}
          </p>
          <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted mt-1">
            {machine.factory_id}
            {machine.manufacturer && ` · ${machine.manufacturer}`}
            {machine.machine_type && ` · ${machine.machine_type}`}
          </p>
          {(summaryParts.length > 0 || latestUpdate) && (
            <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted mt-2">
              {summaryParts.join(" · ")}
              {latestUpdate && ` · อัปเดต ${latestUpdate}`}
            </p>
          )}
          <div className="flex flex-wrap gap-2 mt-4">
            {onAskAi && (
              <button
                type="button"
                onClick={() => onAskAi(machine.machine_id)}
                className={cn(
                  "inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium",
                  "bg-gemini-blue dark:bg-gemini-dark-blue text-white",
                  "hover:opacity-90"
                )}
              >
                <MessageCircle className="h-4 w-4" />
                ถาม AI เกี่ยวกับเครื่องนี้
              </button>
            )}
          </div>
        </div>
      </div>

      {groups.length === 0 ? (
        <div className="text-center py-12 text-sm text-gemini-muted">
          ยังไม่มีเอกสารสำหรับเครื่องนี้
        </div>
      ) : (
        groups.map((group) => (
          <section key={group.type}>
            <h3 className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text mb-2">
              {documentTypeLabel(group.type)} ({group.docs.length})
            </h3>
            <div className="grid gap-2">
              {group.docs.map((doc) => (
                <DocumentRow key={doc.doc_id} doc={doc} onOpen={onOpenDoc} />
              ))}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
