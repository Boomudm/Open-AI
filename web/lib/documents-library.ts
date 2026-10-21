import type { IndexedDocument, Machine } from "@/lib/api";
import type { DocumentCategoryId } from "@/lib/document-categories";
import { documentTypeLabel, MACHINE_DOC_TYPE_ORDER } from "@/lib/document-categories";

export function docDisplayLabel(doc: IndexedDocument): string {
  return doc.title ?? doc.original_filename ?? doc.source_file ?? doc.doc_id;
}

export function countByCategory(
  documents: IndexedDocument[],
  category: DocumentCategoryId,
  factoryWideOnly = true
): number {
  return documents.filter((d) => {
    if (d.document_category !== category) return false;
    if (factoryWideOnly && d.machine_id) return false;
    return true;
  }).length;
}

export function filterCategoryDocuments(
  documents: IndexedDocument[],
  category: DocumentCategoryId,
  factoryWideOnly = true
): IndexedDocument[] {
  return documents.filter((d) => {
    if (d.document_category !== category) return false;
    if (factoryWideOnly && d.machine_id) return false;
    return true;
  });
}

export function countDocsPerMachine(
  documents: IndexedDocument[]
): Map<string, number> {
  const map = new Map<string, number>();
  for (const d of documents) {
    if (!d.machine_id) continue;
    map.set(d.machine_id, (map.get(d.machine_id) ?? 0) + 1);
  }
  return map;
}

export function filterMachineDocuments(
  documents: IndexedDocument[],
  machineId: string
): IndexedDocument[] {
  return documents.filter((d) => d.machine_id === machineId);
}

export function groupByDocumentType(
  documents: IndexedDocument[]
): { type: string; label: string; docs: IndexedDocument[] }[] {
  const groups = new Map<string, IndexedDocument[]>();
  for (const d of documents) {
    const list = groups.get(d.document_type) ?? [];
    list.push(d);
    groups.set(d.document_type, list);
  }

  const ordered: { type: string; label: string; docs: IndexedDocument[] }[] = [];
  const seen = new Set<string>();

  for (const type of MACHINE_DOC_TYPE_ORDER) {
    const docs = groups.get(type);
    if (docs?.length) {
      ordered.push({
        type,
        label: documentTypeLabel(type),
        docs: docs.sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
      });
      seen.add(type);
    }
  }

  for (const [type, docs] of groups) {
    if (seen.has(type)) continue;
    ordered.push({
      type,
      label: documentTypeLabel(type),
      docs: docs.sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    });
  }

  return ordered;
}

export function searchDocumentsAndMachines(
  documents: IndexedDocument[],
  machines: Machine[],
  query: string
): { documents: IndexedDocument[]; machines: Machine[] } {
  const q = query.trim().toLowerCase();
  if (!q) return { documents: [], machines: [] };

  const matchedDocs = documents.filter((d) =>
    docDisplayLabel(d).toLowerCase().includes(q)
  );

  const matchedMachines = machines.filter(
    (m) =>
      m.machine_id.toLowerCase().includes(q) ||
      m.machine_name.toLowerCase().includes(q) ||
      (m.machine_type?.toLowerCase().includes(q) ?? false)
  );

  return { documents: matchedDocs.slice(0, 8), machines: matchedMachines.slice(0, 8) };
}

export function recentDocuments(
  documents: IndexedDocument[],
  limit = 5
): IndexedDocument[] {
  return [...documents]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, limit);
}

export type DocumentsRoute =
  | { view: "hub" }
  | { view: "category"; category: DocumentCategoryId }
  | { view: "machines" }
  | { view: "machine"; machineId: string }
  | { view: "ingest_jobs" }
  | { view: "all" };

export function routeBreadcrumb(route: DocumentsRoute): string[] {
  switch (route.view) {
    case "hub":
      return ["เอกสาร"];
    case "machines":
      return ["เอกสาร", "เครื่องจักร"];
    case "machine":
      return ["เอกสาร", "เครื่องจักร", route.machineId];
    case "category": {
      const labels: Record<DocumentCategoryId, string> = {
        knowledge: "ความรู้และคู่มือ",
        maintenance: "การบำรุงรักษา",
        compliance: "ความปลอดภัยและมาตรฐาน",
        inspection: "การตรวจสอบและรายงาน",
        inventory: "คลังอะไหล่และจัดซื้อ",
        enterprise: "องค์กรและบุคคล",
      };
      return ["เอกสาร", labels[route.category]];
    }
    case "all":
      return ["เอกสาร", "ทั้งหมด"];
    case "ingest_jobs":
      return ["เอกสาร", "อัปโหลด / งานนำเข้า"];
  }
}
