export const CHAT_ATTACHMENT_MAX_BYTES = 10_485_760;
export const CHAT_ATTACHMENT_MAX_FILES = 3;

export const CHAT_ATTACHMENT_ACCEPT =
  "image/jpeg,image/png,image/webp,application/pdf,.jpg,.jpeg,.png,.webp,.pdf";

export const CHAT_ASK_FIELD_QUESTION = "question";
export const CHAT_ASK_FIELD_FILTER_JSON = "filter_json";
export const CHAT_ASK_FIELD_TOP_K = "top_k";
export const CHAT_ASK_FIELD_FILES = "files";

const ALLOWED_MIME = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "application/pdf",
]);

export function validateChatAttachmentFiles(files: File[]): string | null {
  if (files.length === 0) return null;
  if (files.length > CHAT_ATTACHMENT_MAX_FILES) {
    return `แนบได้สูงสุด ${CHAT_ATTACHMENT_MAX_FILES} ไฟล์`;
  }
  for (const file of files) {
    const mime = file.type || guessMimeFromName(file.name);
    if (!mime || !ALLOWED_MIME.has(mime)) {
      return `ไฟล์ไม่รองรับ: ${file.name} (JPEG, PNG, WebP, PDF เท่านั้น)`;
    }
    if (file.size > CHAT_ATTACHMENT_MAX_BYTES) {
      return `ไฟล์ใหญ่เกินไป: ${file.name} (สูงสุด 10 MB)`;
    }
    if (file.size === 0) {
      return `ไฟล์ว่าง: ${file.name}`;
    }
  }
  return null;
}

function guessMimeFromName(name: string): string | null {
  const lower = name.toLowerCase();
  if (lower.endsWith(".pdf")) return "application/pdf";
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".webp")) return "image/webp";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  return null;
}
