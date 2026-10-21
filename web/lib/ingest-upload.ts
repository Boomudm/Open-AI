/** File formats accepted per document type (mirrors configs/ingestion/*.yaml parsers). */

export const DOCUMENT_TYPE_ACCEPT: Record<string, readonly string[]> = {
  datasheet: [".pdf"],
  drawing: [".pdf"],
  incident_report: [".docx"],
  inspection_report: [".pdf"],
  iso_certificate: [".pdf"],
  // parser: auto in configs/ingestion/io_mapping.yaml routes by extension;
  // real uploads are PLC symlink sheets (.xlsx) and mapping_diagram.pdf.
  io_mapping: [".xlsx", ".xls", ".pdf"],
  // parser: auto in configs/ingestion/knowledge_document.yaml routes by
  // extension (see detect_parser_for_path) — this allowlist only had pdf/docx,
  // silently rejecting xlsx uploads the backend already supports.
  knowledge_document: [".pdf", ".docx", ".xlsx", ".xls", ".csv"],
  machine_manual: [".pdf"],
  near_miss: [".docx"],
  purchase_order: [".xlsx"],
  repair_history: [".xlsx"],
  safety_certificate: [".pdf"],
  sop: [".pdf"],
  spare_part_catalog: [".xlsx"],
  training_note: [".docx"],
  work_order: [".xlsx"],
  stock_movement_history: [".xlsx"],
  company_policy: [".pdf"],
  hr_handbook: [".pdf"],
  internal_guideline: [".pdf"],
};

export function acceptedExtensionsForDocumentType(documentType: string): readonly string[] {
  return DOCUMENT_TYPE_ACCEPT[documentType] ?? [".pdf", ".xlsx", ".docx"];
}

export function fileFormatHintForDocumentType(documentType: string): string {
  const exts = acceptedExtensionsForDocumentType(documentType);
  const labels = exts.map((ext) => {
    if (ext === ".pdf") return "PDF";
    if (ext === ".xlsx") return "Excel (.xlsx)";
    if (ext === ".docx") return "Word (.docx)";
    return ext.slice(1).toUpperCase();
  });
  return labels.join(" · ");
}

export function isFileAcceptedForDocumentType(file: File, documentType: string): boolean {
  const dot = file.name.lastIndexOf(".");
  const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  return acceptedExtensionsForDocumentType(documentType).includes(ext);
}
