import type { LucideIcon } from "lucide-react";
import {
  BookOpen,
  ClipboardCheck,
  Factory,
  Package,
  ShieldCheck,
  Upload,
  Users,
  Wrench,
} from "lucide-react";

export type DocumentCategoryId =
  | "knowledge"
  | "maintenance"
  | "compliance"
  | "inspection"
  | "inventory"
  | "enterprise";

export type HubCategoryId = DocumentCategoryId | "machines";

export const DOCUMENT_CATEGORY_META: Record<
  DocumentCategoryId,
  { label: string; description: string; icon: LucideIcon }
> = {
  knowledge: {
    label: "ความรู้และคู่มือ",
    description: "SOP, แบบแปลน, datasheet ทั่วไป",
    icon: BookOpen,
  },
  maintenance: {
    label: "การบำรุงรักษา",
    description: "ประวัติซ่อมและงานบำรุงรักษา",
    icon: Wrench,
  },
  compliance: {
    label: "ความปลอดภัยและมาตรฐาน",
    description: "ใบรับรอง ISO, ความปลอดภัย",
    icon: ShieldCheck,
  },
  inspection: {
    label: "การตรวจสอบและรายงาน",
    description: "รายงานตรวจสอบ, near miss, incident",
    icon: ClipboardCheck,
  },
  inventory: {
    label: "คลังอะไหล่และจัดซื้อ",
    description: "แคตตาล็อกอะไหล่, PO",
    icon: Package,
  },
  enterprise: {
    label: "องค์กรและบุคคล",
    description: "นโยบายบริษัท, คู่มือพนักงาน, แนวปฏิบัติภายใน",
    icon: Users,
  },
};

export const MACHINES_HUB_META = {
  label: "เครื่องจักร",
  description: "คู่มือและเอกสารตามเครื่อง",
  icon: Factory,
};

export const INGEST_JOBS_HUB_META = {
  label: "อัปโหลด / งานนำเข้า",
  description: "อัปโหลดเอกสารและติดตามสถานะประมวลผล",
  icon: Upload,
};

export const HUB_CATEGORY_ORDER: HubCategoryId[] = [
  "machines",
  "knowledge",
  "maintenance",
  "compliance",
  "inspection",
  "inventory",
  "enterprise",
];

export const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  machine_manual: "คู่มือเครื่องจักร",
  io_mapping: "I/O mapping",
  repair_history: "ประวัติการซ่อม",
  training_note: "บันทึกการอบรม",
  sop: "ขั้นตอนการทำงาน (SOP)",
  drawing: "แบบแปลน",
  datasheet: "Datasheet",
  inspection_report: "รายงานตรวจสอบ",
  near_miss: "Near miss",
  incident_report: "รายงานเหตุการณ์",
  safety_certificate: "ใบรับรองความปลอดภัย",
  iso_certificate: "ใบรับรอง ISO",
  spare_part_catalog: "แคตตาล็อกอะไหล่",
  purchase_order: "ใบสั่งซื้อ",
  work_order: "ใบงานซ่อม",
  stock_movement_history: "ประวัติเคลื่อนย้ายอะไหล่",
  knowledge_document: "เอกสารความรู้ทั่วไป",
  company_policy: "นโยบายบริษัท",
  hr_handbook: "คู่มือพนักงาน / HR",
  internal_guideline: "แนวปฏิบัติภายใน",
};

export function documentTypeLabel(type: string): string {
  return DOCUMENT_TYPE_LABELS[type] ?? type.replace(/_/g, " ");
}

/** Ingest configs that require machine_id in required_metadata. */
export const MACHINE_REQUIRED_DOC_TYPES = new Set<string>();

/** Document types where linking a machine is meaningful in the upload UI. */
export const MACHINE_LINKED_DOC_TYPES = new Set([
  "machine_manual",
  "io_mapping",
  "drawing",
  "repair_history",
  "sop",
  "datasheet",
  "training_note",
  "knowledge_document",
  "incident_report",
  "inspection_report",
  "near_miss",
  "safety_certificate",
]);

/** Optional machine links that are easy to forget but usually matter. */
export const MACHINE_RECOMMENDED_DOC_TYPES = new Set([
  "machine_manual",
  "io_mapping",
  "drawing",
]);

export function documentTypeShowsMachineField(documentType: string): boolean {
  return MACHINE_LINKED_DOC_TYPES.has(documentType);
}

export function documentTypeRequiresMachine(documentType: string): boolean {
  return MACHINE_REQUIRED_DOC_TYPES.has(documentType);
}

export function documentTypeRecommendsMachine(documentType: string): boolean {
  return MACHINE_RECOMMENDED_DOC_TYPES.has(documentType);
}

export const ENTERPRISE_DOC_TYPES = new Set([
  "company_policy",
  "hr_handbook",
  "internal_guideline",
]);

export function isEnterpriseDocType(documentType: string): boolean {
  return ENTERPRISE_DOC_TYPES.has(documentType);
}

export const MACHINE_DOC_TYPE_ORDER = [
  "machine_manual",
  "io_mapping",
  "sop",
  "drawing",
  "datasheet",
  "repair_history",
  "training_note",
  "inspection_report",
  "near_miss",
  "incident_report",
  "safety_certificate",
  "iso_certificate",
  "spare_part_catalog",
  "purchase_order",
] as const;
