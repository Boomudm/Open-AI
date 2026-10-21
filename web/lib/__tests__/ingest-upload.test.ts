import assert from "node:assert/strict";
import {
  acceptedExtensionsForDocumentType,
  fileFormatHintForDocumentType,
  isFileAcceptedForDocumentType,
} from "../ingest-upload";
import {
  documentTypeLabel,
  documentTypeRecommendsMachine,
  documentTypeRequiresMachine,
  documentTypeShowsMachineField,
} from "../document-categories";
import {
  filterTypesForPipeline,
  guessDocumentTypeFromFilename,
} from "../ingest-defaults";

assert.deepEqual(acceptedExtensionsForDocumentType("purchase_order"), [".xlsx"]);
assert.equal(fileFormatHintForDocumentType("purchase_order"), "Excel (.xlsx)");
assert.deepEqual(acceptedExtensionsForDocumentType("incident_report"), [".docx"]);

const pdf = new File(["%PDF"], "note.pdf", { type: "application/pdf" });
const xlsx = new File(["x"], "po.xlsx", {
  type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
});
assert.equal(isFileAcceptedForDocumentType(pdf, "iso_certificate"), true);
assert.equal(isFileAcceptedForDocumentType(xlsx, "iso_certificate"), false);
assert.equal(isFileAcceptedForDocumentType(xlsx, "purchase_order"), true);

const backendTypes = [
  "company_policy",
  "drawing",
  "hr_handbook",
  "internal_guideline",
  "io_mapping",
  "machine_manual",
  "sop",
];

assert.equal(documentTypeLabel("io_mapping"), "I/O mapping");
assert.equal(documentTypeRequiresMachine("machine_manual"), false);
assert.equal(documentTypeRequiresMachine("drawing"), false);
assert.equal(documentTypeShowsMachineField("io_mapping"), true);
assert.equal(documentTypeRecommendsMachine("io_mapping"), true);
assert.equal(documentTypeRecommendsMachine("machine_manual"), true);
assert.equal(documentTypeRecommendsMachine("sop"), false);
assert.deepEqual(filterTypesForPipeline(backendTypes, "enterprise"), [
  "company_policy",
  "hr_handbook",
  "internal_guideline",
]);
assert.deepEqual(filterTypesForPipeline(backendTypes, "machinery"), [
  "drawing",
  "io_mapping",
  "machine_manual",
  "sop",
]);
assert.equal(
  guessDocumentTypeFromFilename("mapping_diagram.pdf", backendTypes),
  "io_mapping"
);

console.log("ingest-upload.test.ts ok");
