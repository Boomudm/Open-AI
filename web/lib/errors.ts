import {
  ERR_OPERATOR_API_DOWN,
  ERR_OPERATOR_GENERIC,
  ERR_OPERATOR_SERVER,
} from "@/lib/messages.th";

const GENERIC_VALIDATION = "ข้อมูลไม่ถูกต้อง กรุณาตรวจสอบและลองใหม่";
const QUESTION_TOO_LONG =
  "ข้อความยาวเกิน 3,000 ตัวอักษร — ลองย่อคำถามหรืออัปโหลดเอกสารที่หน้า อัปโหลดเอกสาร แล้วถามสั้น ๆ เช่น \"สรุปรายงานนี้\"";
const GENERIC_ERROR = ERR_OPERATOR_GENERIC;

const STATUS_MESSAGES: Record<number, string> = {
  403: "คุณไม่มีสิทธิ์ทำรายการนี้",
  404: "ไม่พบข้อมูลที่ต้องการ",
  409: "ข้อมูลขัดแย้งกับที่มีอยู่แล้ว — ลองใหม่อีกครั้ง",
  422: GENERIC_VALIDATION,
  429: "คำขอมากเกินไป — รอสักครู่แล้วลองใหม่",
};

export function parseApiError(raw: unknown): string {
  if (raw instanceof Error) {
    const msg = raw.message;
    const statusMatch = msg.match(/^(\d{3})\s+/);
    const status = statusMatch ? Number(statusMatch[1]) : null;
    const jsonMatch = msg.match(/^\d{3}\s+(\{.*\})$/s);
    if (jsonMatch) {
      try {
        const body = JSON.parse(jsonMatch[1]) as { detail?: unknown };
        const formatted = formatDetail(body.detail);
        if (formatted) return formatted;
        if (status && STATUS_MESSAGES[status]) return STATUS_MESSAGES[status]!;
      } catch {
        if (status && STATUS_MESSAGES[status]) return STATUS_MESSAGES[status]!;
      }
    }
    if (status && STATUS_MESSAGES[status]) return STATUS_MESSAGES[status]!;
    if (msg === "401 unauthorized") return "เซสชันหมดอายุ — กรุณาเข้าสู่ระบบใหม่";
    if (/citation_validation_failed/i.test(msg)) {
      return "ไม่สามารถยืนยันแหล่งอ้างอิงได้ — ลองถามใหม่หรือย่อคำถาม";
    }
    if (/failed to fetch|networkerror|network error|load failed/i.test(msg)) {
      return ERR_OPERATOR_API_DOWN;
    }
    if (msg.includes("invalid credentials")) return "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง";
    if (msg === "500 Internal Server Error" || msg.startsWith("500 ")) {
      if (msg.includes("/auth/me") || msg.includes("auth/me")) {
        return "โหลดข้อมูลโปรไฟล์ไม่สำเร็จ — ลองรีเฟรชหรือเข้าสู่ระบบใหม่";
      }
      return ERR_OPERATOR_SERVER;
    }
    if (msg === "502 Bad Gateway" || msg === "503 Service Unavailable") {
      return ERR_OPERATOR_API_DOWN;
    }
    if (msg.startsWith("404 ") || msg.includes('"detail":"Not Found"')) {
      return STATUS_MESSAGES[404]!;
    }
    if (looksLikeInternalMessage(msg)) return GENERIC_ERROR;
    return msg;
  }
  return String(raw);
}

function looksLikeInternalMessage(msg: string): boolean {
  if (/^[a-z_]+ required$/i.test(msg)) return true;
  if (/^Field required/i.test(msg)) return true;
  if (/include_inactive requires/i.test(msg)) return true;
  if (/^[A-Za-z ]+ not found$/i.test(msg)) return true;
  return false;
}

function formatDetail(detail: unknown): string | null {
  if (typeof detail === "string") {
    const mapped = mapKnownDetail(detail);
    if (mapped) return mapped;
    if (looksLikeInternalMessage(detail)) return GENERIC_ERROR;
    return detail;
  }
  if (Array.isArray(detail)) {
    const hasLength = detail.some(
      (item) =>
        item &&
        typeof item === "object" &&
        "loc" in item &&
        Array.isArray((item as { loc?: unknown }).loc) &&
        (item as { loc: string[] }).loc.includes("question") &&
        String((item as { type?: string }).type || "").includes("string_too_long")
    );
    if (hasLength) return QUESTION_TOO_LONG;
    return GENERIC_VALIDATION;
  }
  if (detail && typeof detail === "object" && "msg" in detail) {
    return GENERIC_VALIDATION;
  }
  return null;
}

function mapKnownDetail(detail: string): string | null {
  const lower = detail.toLowerCase();
  if (lower.includes("not found")) return STATUS_MESSAGES[404]!;
  if (lower.includes("forbidden") || lower.includes("permission")) {
    return STATUS_MESSAGES[403]!;
  }
  if (lower.includes("already exists") || lower.includes("duplicate")) {
    return STATUS_MESSAGES[409]!;
  }
  if (lower.includes("invalid credentials")) return "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง";
  if (lower.includes("citation_validation_failed") || lower.includes("citation validation")) {
    return "ไม่สามารถยืนยันแหล่งอ้างอิงได้ — ลองถามใหม่หรือย่อคำถาม";
  }
  return null;
}
