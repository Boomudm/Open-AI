import type { DocumentCategoryId } from "@/lib/document-categories";
import { acceptedExtensionsForDocumentType } from "@/lib/ingest-upload";

/** Document types per hub category (mirrors configs/ingestion/*.yaml document_category). */
export const CATEGORY_DOC_TYPES: Record<DocumentCategoryId, readonly string[]> = {
  knowledge: [
    "machine_manual",
    "io_mapping",
    "sop",
    "drawing",
    "datasheet",
    "training_note",
    "knowledge_document",
  ],
  maintenance: ["repair_history", "work_order"],
  compliance: ["safety_certificate", "iso_certificate"],
  inspection: ["inspection_report", "near_miss", "incident_report"],
  inventory: ["spare_part_catalog", "purchase_order", "stock_movement_history"],
  enterprise: ["company_policy", "hr_handbook", "internal_guideline"],
};

export const CATEGORY_DEFAULT_DOC_TYPE: Record<DocumentCategoryId, string> = {
  knowledge: "sop",
  maintenance: "repair_history",
  compliance: "safety_certificate",
  inspection: "inspection_report",
  inventory: "spare_part_catalog",
  enterprise: "company_policy",
};

/** Filename hints — keep in sync with spark.ingestion.document_type_resolver.FILENAME_HINTS */
const FILENAME_HINTS: ReadonlyArray<[string, string]> = [
  ["mapping", "io_mapping"],
  ["io_map", "io_mapping"],
  ["symlink", "io_mapping"],
  ["manual", "machine_manual"],
  ["ma001", "machine_manual"],
  ["repair", "repair_history"],
  ["history", "repair_history"],
  ["sop", "sop"],
  ["drawing", "drawing"],
  ["p&id", "drawing"],
  ["pid", "drawing"],
  ["spec", "datasheet"],
  ["datasheet", "datasheet"],
  ["iso", "iso_certificate"],
  ["cert", "safety_certificate"],
  ["wiring", "drawing"],
  ["diagram", "drawing"],
  ["schematic", "drawing"],
  ["inspection", "inspection_report"],
  ["incident", "incident_report"],
  ["nearmiss", "near_miss"],
  ["work_order", "work_order"],
  ["po_", "purchase_order"],
  ["purchase", "purchase_order"],
  ["spare", "spare_part_catalog"],
  ["training", "training_note"],
  ["policy", "company_policy"],
  ["handbook", "hr_handbook"],
  ["guideline", "internal_guideline"],
];

export function guessDocumentTypeFromFilename(
  filename: string,
  availableTypes: readonly string[]
): string | null {
  const lower = filename.toLowerCase();
  const allowed = new Set(availableTypes);
  for (const [hint, docType] of FILENAME_HINTS) {
    if (lower.includes(hint) && allowed.has(docType)) {
      return docType;
    }
  }
  if (allowed.has("knowledge_document")) {
    const ext = extensionOf(filename);
    if (acceptedExtensionsForDocumentType("knowledge_document").includes(ext)) {
      return "knowledge_document";
    }
  }
  return null;
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

export type ResolveDefaultDocumentTypeArgs = {
  category?: DocumentCategoryId;
  defaultMachineId?: string;
  pipeline?: "machinery" | "enterprise";
  availableTypes: readonly string[];
};

export function resolveDefaultDocumentType({
  category,
  defaultMachineId,
  pipeline,
  availableTypes,
}: ResolveDefaultDocumentTypeArgs): string {
  if (availableTypes.length === 0) return "";

  const pick = (preferred: string) =>
    availableTypes.includes(preferred) ? preferred : availableTypes[0];

  if (category) {
    return pick(CATEGORY_DEFAULT_DOC_TYPE[category]);
  }
  if (pipeline === "enterprise") {
    return pick("company_policy");
  }
  if (defaultMachineId) {
    return pick("machine_manual");
  }
  if (pipeline === "machinery") {
    return pick("machine_manual");
  }
  return availableTypes[0];
}

export function filterTypesForCategory(
  allTypes: readonly string[],
  category: DocumentCategoryId
): string[] {
  const pool = CATEGORY_DOC_TYPES[category];
  return allTypes.filter((t) => pool.includes(t));
}

export function filterTypesForPipeline(
  allTypes: readonly string[],
  pipeline: "machinery" | "enterprise"
): string[] {
  const pool =
    pipeline === "enterprise"
      ? CATEGORY_DOC_TYPES.enterprise
      : [
          ...CATEGORY_DOC_TYPES.knowledge,
          ...CATEGORY_DOC_TYPES.maintenance,
          ...CATEGORY_DOC_TYPES.compliance,
          ...CATEGORY_DOC_TYPES.inspection,
          ...CATEGORY_DOC_TYPES.inventory,
        ];
  return allTypes.filter((t) => pool.includes(t));
}
