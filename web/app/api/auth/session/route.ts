import { AUTH_COOKIE_NAME } from "@/lib/auth";
import { verifySparkJwt } from "@/lib/jwt";
import { NextResponse } from "next/server";

const MAX_AGE_SEC = 8 * 3600;

/** Secure cookies only on HTTPS (Cloudflare) — LAN http://spark.lan must still persist sessions. */
function sessionCookieSecure(request: Request): boolean {
  if (process.env.COOKIE_SECURE === "true") return true;
  if (process.env.COOKIE_SECURE === "false") return false;
  const proto = request.headers.get("x-forwarded-proto")?.split(",")[0]?.trim().toLowerCase();
  if (proto === "https") return true;
  if (proto === "http") return false;
  try {
    return new URL(request.url).protocol === "https:";
  } catch {
    return false;
  }
}

export async function POST(request: Request) {
  let body: { token?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid body" }, { status: 400 });
  }

  const token = body.token;
  if (!token || typeof token !== "string") {
    return NextResponse.json({ error: "missing token" }, { status: 400 });
  }

  const claims = await verifySparkJwt(token);
  if (!claims) {
    return NextResponse.json({ error: "invalid token" }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  const secure = sessionCookieSecure(request);
  res.cookies.set(AUTH_COOKIE_NAME, token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: MAX_AGE_SEC,
    secure,
  });
  return res;
}

export async function DELETE(request: Request) {
  const res = NextResponse.json({ ok: true });
  const secure = sessionCookieSecure(request);
  res.cookies.set(AUTH_COOKIE_NAME, "", {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
    secure,
  });
  return res;
}
