import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { verifySparkJwt } from "../jwt";

function b64url(data: Buffer | string): string {
  const buf = typeof data === "string" ? Buffer.from(data) : data;
  return buf.toString("base64url");
}

function signToken(secret: string, claims: Record<string, unknown>): string {
  const header = b64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = b64url(JSON.stringify(claims));
  const sig = createHmac("sha256", secret)
    .update(`${header}.${body}`)
    .digest("base64url");
  return `${header}.${body}.${sig}`;
}

async function main() {
  const prev = process.env.JWT_SECRET;
  process.env.JWT_SECRET = "test-jwt-secret";

  const valid = signToken("test-jwt-secret", {
    roles: ["admin"],
    exp: Math.floor(Date.now() / 1000) + 3600,
  });
  const claims = await verifySparkJwt(valid);
  assert.ok(claims);
  assert.equal(claims?.roles?.[0], "admin");

  const wrongSecret = signToken("wrong-secret", {
    roles: ["admin"],
    exp: Math.floor(Date.now() / 1000) + 3600,
  });
  assert.equal(await verifySparkJwt(wrongSecret), null);
  assert.equal(await verifySparkJwt("not.a.jwt"), null);

  process.env.JWT_SECRET = prev;
  console.log("jwt.test.ts ok");
}

void main();
