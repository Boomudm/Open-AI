import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import {
  canWriteFromClaims,
  isAdminFromClaims,
  verifySparkJwt,
} from "@/lib/jwt";

const AUTH_COOKIE_NAME = "spark_token";

const PUBLIC_PREFIXES = ["/login", "/signup", "/auth/callback", "/api/auth/", "/privacy"];

/** Client-side AuthGuard owns these routes; cookie may be absent in installed PWA. */
const CLIENT_AUTH_PREFIXES = ["/chat", "/account"];

const PWA_PUBLIC_EXACT = ["/manifest.json", "/sw.js"];

function isPwaPublicAsset(pathname: string): boolean {
  if (PWA_PUBLIC_EXACT.includes(pathname)) return true;
  if (pathname.startsWith("/icons/")) return true;
  if (pathname.startsWith("/neo/")) return true;
  if (pathname.includes("pdf.worker")) return true;
  return false;
}

function isPublicPath(pathname: string): boolean {
  if (pathname.startsWith("/api/")) return true;
  if (isPwaPublicAsset(pathname)) return true;
  if (PUBLIC_PREFIXES.some((p) => pathname === p || pathname.startsWith(p))) {
    return true;
  }
  return false;
}

function isClientAuthPath(pathname: string): boolean {
  return CLIENT_AUTH_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`)
  );
}

function homePathForClaims(_canWrite: boolean): string {
  return "/chat";
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname.endsWith(".ico") ||
    isPwaPublicAsset(pathname)
  ) {
    return NextResponse.next();
  }

  const rawToken = request.cookies.get(AUTH_COOKIE_NAME)?.value;
  const claims = rawToken ? await verifySparkJwt(rawToken) : null;
  const tokenValid = claims != null;
  const canWrite = claims ? canWriteFromClaims(claims) : false;
  const home = tokenValid ? homePathForClaims(canWrite) : "/login";

  const switchingAccount = request.nextUrl.searchParams.get("switch") === "1";
  const privacyOnboarding = request.nextUrl.searchParams.get("onboard") === "privacy";
  if (
    tokenValid &&
    (pathname === "/login" || pathname === "/signup") &&
    !switchingAccount &&
    !privacyOnboarding
  ) {
    return NextResponse.redirect(new URL(home, request.url));
  }

  if (pathname === "/") {
    return NextResponse.redirect(new URL(home, request.url));
  }

  const READ_WORKSPACE_PREFIXES = ["/documents"];
  const WRITE_WORKSPACE_PREFIXES = [
    "/upload",
    "/feedback",
    "/machines",
  ];

  const isReadWorkspacePath = READ_WORKSPACE_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`)
  );
  const isWriteWorkspacePath = WRITE_WORKSPACE_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`)
  );

  if (tokenValid && isWriteWorkspacePath && !canWrite) {
    return NextResponse.redirect(new URL("/chat", request.url));
  }

  if (tokenValid && pathname.startsWith("/chat") && canWrite) {
    const view = request.nextUrl.searchParams.get("view");
    if (view === "documents") {
      return NextResponse.redirect(new URL("/documents", request.url));
    }
    if (view === "feedback") {
      return NextResponse.redirect(new URL("/feedback", request.url));
    }
  }

  if (pathname.startsWith("/admin") && !pathname.startsWith("/system-admin")) {
    if (!tokenValid || !isAdminFromClaims(claims)) {
      return NextResponse.redirect(new URL(tokenValid ? "/chat" : "/login", request.url));
    }
  }

  if (pathname.startsWith("/system-admin")) {
    if (!tokenValid || !isAdminFromClaims(claims!)) {
      return NextResponse.redirect(new URL(tokenValid ? "/chat" : "/login", request.url));
    }
  }

  if (!tokenValid && !isPublicPath(pathname) && !isClientAuthPath(pathname)) {
    const loginUrl = new URL("/login", request.url);
    if (pathname !== "/") {
      loginUrl.searchParams.set("from", pathname + request.nextUrl.search);
    }
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
