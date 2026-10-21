export type SparkJwtClaims = {
  roles?: string[];
  factory_access?: Record<string, "read" | "write" | "admin">;
  is_super_admin?: boolean;
  exp?: number;
  sub?: string;
  username?: string;
};

const DEV_JWT_SECRET = "dev-secret-change-me";

function b64urlDecode(input: string): Uint8Array {
  const pad = "=".repeat((4 - (input.length % 4)) % 4);
  const normalized = input.replace(/-/g, "+").replace(/_/g, "/") + pad;
  const binary = atob(normalized);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function jwtSecret(): string {
  const secret = (process.env.JWT_SECRET ?? "").trim();
  return secret || DEV_JWT_SECRET;
}

/** Verify HS256 Spark JWT signature and expiry (Edge + Node). */
export async function verifySparkJwt(token: string): Promise<SparkJwtClaims | null> {
  const parts = token.split(".");
  if (parts.length !== 3) return null;

  const [headerB64, bodyB64, sigB64] = parts;
  try {
    const header = JSON.parse(new TextDecoder().decode(b64urlDecode(headerB64))) as {
      alg?: string;
    };
    if (header.alg !== "HS256") return null;

    const signingInput = new TextEncoder().encode(`${headerB64}.${bodyB64}`);
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(jwtSecret()),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["verify"]
    );
    const valid = await crypto.subtle.verify("HMAC", key, b64urlDecode(sigB64), signingInput);
    if (!valid) return null;

    const claims = JSON.parse(new TextDecoder().decode(b64urlDecode(bodyB64))) as SparkJwtClaims;
    if (claims.exp != null && claims.exp < Math.floor(Date.now() / 1000)) {
      return null;
    }
    return claims;
  } catch {
    return null;
  }
}

export function canWriteFromClaims(claims: SparkJwtClaims): boolean {
  if (claims.is_super_admin) return true;
  if (claims.roles?.includes("admin")) return true;
  if (claims.roles?.includes("operator")) return true;
  const access = claims.factory_access ?? {};
  const order: Record<"read" | "write" | "admin", number> = {
    read: 0,
    write: 1,
    admin: 2,
  };
  return Object.values(access).some((level) => order[level] >= order.write);
}

export function isAdminFromClaims(claims: SparkJwtClaims): boolean {
  return Boolean(claims.roles?.includes("admin") || claims.is_super_admin);
}

export function isSuperAdminFromClaims(claims: SparkJwtClaims | null): boolean {
  return Boolean(claims?.is_super_admin);
}
