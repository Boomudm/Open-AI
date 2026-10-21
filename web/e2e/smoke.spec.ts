import { createHmac } from "node:crypto";
import { expect, type Page, type Request, type Route, test } from "@playwright/test";
import type { UserProfile } from "@/lib/api";

const E2E_JWT_SECRET = process.env.JWT_SECRET ?? "dev-secret-change-me";
const AUTH_COOKIE_NAME = "spark_token";
const E2E_BASE_URL =
  process.env.PLAYWRIGHT_BASE_URL ??
  `http://localhost:${process.env.PLAYWRIGHT_PORT ?? 3000}`;

/** Active signed JWT for cookie-auth mocks. */
let activeSessionToken: string | null = null;

const adminToken = tokenFor({
  username: "admin",
  roles: ["admin"],
  factory_access: { "F-01": "admin", "F-02": "admin" },
  job_position_ids: [],
  privacy_policy_version: "2026.06",
});

const operatorToken = tokenFor({
  username: "operator_f01",
  roles: ["employee"],
  factory_access: { "F-01": "read" },
  job_position_ids: ["jp-maint"],
  privacy_policy_version: "2026.06",
});

const machines = [
  {
    machine_id: "MC-001",
    factory_id: "F-01",
    machine_name: "Servo Motor Line 1",
    machine_type: "servo",
    manufacturer: "ACME",
    is_active: true,
  },
];

const documents = [
  {
    doc_id: "doc-1",
    factory_id: "F-01",
    machine_id: "MC-001",
    document_category: "machine",
    document_type: "machine_manual",
    title: "MC-001 Servo Manual",
    language: "en",
    revision: "A",
    source_file: "mc-001-manual.pdf",
    original_filename: "mc-001-manual.pdf",
    mime_type: "application/pdf",
    file_hash_sha256: "abc123",
    file_size_bytes: 1024,
    ingest_status: "completed",
    chunks_count: 4,
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
  },
];

test.beforeEach(async ({ page }) => {
  // Generous: the dev server (used by both local runs and CI) compiles heavy
  // routes like /chat lazily on first hit, which can take tens of seconds cold.
  test.setTimeout(90_000);
  await mockApi(page);
});

test("guest at root is redirected to login", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveURL(/\/login(?:\?.*)?$/);
  await expect(page.locator('input[name="username"]')).toBeVisible();
});

test("guest visiting a guarded route is redirected to login", async ({ page }) => {
  await page.goto("/documents");

  await expect(page).toHaveURL(/\/login\?.*from=%2Fdocuments/);
});

test("login page renders the credentials form", async ({ page }) => {
  await page.goto("/login");

  await expect(page.locator('input[name="username"]')).toBeVisible();
  await expect(page.locator('input[name="password"]')).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeVisible();
});

test("login empty credentials shows Thai error", async ({ page }) => {
  await page.goto("/login");
  await page.locator("#auth-credentials-form").evaluate((form) => {
    (form as HTMLFormElement).requestSubmit();
  });
  await expect(page.getByText("กรุณากรอกชื่อผู้ใช้และรหัสผ่าน")).toBeVisible();
});

test("admin login lands on chat", async ({ page }) => {
  await login(page, "admin", "changeme");

  await expect(page).toHaveURL(/\/chat(?:\?.*)?$/);
  await expect(page.getByLabel("ข้อความแชท")).toBeEditable({ timeout: 30_000 });
});

test("admin can send a message and see a grounded answer", async ({ page }) => {
  await login(page, "admin", "changeme");
  await expect(page).toHaveURL(/\/chat(?:\?.*)?$/);

  const composer = page.getByLabel("ข้อความแชท");
  await expect(composer).toBeEditable({ timeout: 30_000 });
  await composer.fill("สรุปคู่มือเครื่องจักรให้หน่อย");
  await page.getByRole("button", { name: "ส่งข้อความ" }).click();

  await expect(page.getByText("นี่คือคำตอบจากเอกสารทดสอบ")).toBeVisible({ timeout: 15_000 });
});

test("admin can open the documents hub", async ({ page }) => {
  await authenticateAs(page, "admin");

  await page.goto("/documents");

  await expect(page).toHaveURL(/\/documents(?:\?.*)?$/);
  await expect(page.getByTestId("documents-hub")).toBeVisible();
  await expect(page.getByText("MC-001 Servo Manual").first()).toBeVisible();
});

test("admin upload form renders", async ({ page }) => {
  await authenticateAs(page, "admin");

  await page.goto("/upload");

  await expect(page).toHaveURL(/\/upload(?:\?.*)?$/);
  await expect(page.getByTestId("upload-form")).toBeVisible();
  await expect(page.getByRole("button", { name: "อัปโหลด" })).toBeVisible();
});

test("read-only operator is redirected from upload to chat", async ({ page }) => {
  await authenticateAs(page, "operator_f01");

  await page.goto("/upload");

  await expect(page).toHaveURL(/\/chat(?:\?.*)?$/);
});

test("read-only operator can open the documents hub", async ({ page }) => {
  await authenticateAs(page, "operator_f01");

  await page.goto("/documents");

  await expect(page).toHaveURL(/\/documents(?:\?.*)?$/);
  await expect(page.getByTestId("documents-hub")).toBeVisible();
});

/**
 * Establish an authenticated session without driving the login UI. The
 * middleware verifies the `spark_token` cookie JWT directly, so setting the
 * cookie + seeding the UI store is a deterministic way to reach guarded routes
 * (avoids the login-flow cookie-timing races that only matter for the login
 * tests themselves). Use `login()` when the login flow itself is under test.
 */
async function authenticateAs(page: Page, username: "admin" | "operator_f01") {
  const token = username === "operator_f01" ? operatorToken : adminToken;
  activeSessionToken = token;
  await ensureSessionCookie(page, token);
  await page.addInitScript((fid) => {
    try {
      sessionStorage.removeItem("spark_session_redirect_guard");
      localStorage.setItem(
        "spark-ui",
        JSON.stringify({
          state: {
            sidebarExpanded: true,
            selectedFactoryId: fid,
            selectedFactoryIds: [fid],
            selectedMachineId: null,
          },
          version: 0,
        })
      );
    } catch {
      /* storage unavailable before first paint — seedUiStoreFactory retries */
    }
  }, "F-01");
}

async function login(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  const signInBtn = page.getByRole("button", { name: "Continue", exact: true });
  await expect(signInBtn).toBeEnabled({ timeout: 10_000 });

  const token = username === "operator_f01" ? operatorToken : adminToken;
  const waitSessionPost = page.waitForResponse(
    (res) => res.url().includes("/api/auth/session") && res.request().method() === "POST"
  );

  if (username === "admin") {
    // Admins skip the factory-select step (shouldShowFactoryStep === false).
    await Promise.all([waitSessionPost, signInBtn.click()]);
  } else {
    // Non-admins pick a factory before the session is created.
    await signInBtn.click();
    await expect(page.getByRole("heading", { name: "เลือกโรงงาน" })).toBeVisible();
    await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes("/api/auth/session") && res.request().method() === "POST"
      ),
      page.getByRole("button", { name: "Continue", exact: true }).click(),
    ]);
  }

  activeSessionToken = token;
  await ensureSessionCookie(page, token);

  // "commit" resolves as soon as the /chat navigation commits, rather than
  // waiting for a full "load" that background chat requests can delay. The
  // long timeout absorbs first-hit dev-server compilation of the /chat route.
  await page.waitForURL(/\/chat(?:\?.*)?$/, { timeout: 60_000, waitUntil: "commit" });
  await page
    .waitForResponse((res) => res.url().includes("/api/v1/auth/me") && res.ok(), {
      timeout: 10_000,
    })
    .catch(() => undefined);
  await ensureSessionCookie(page, token);
  await seedUiStoreFactory(page, "F-01");
}

async function mockApi(page: Page) {
  activeSessionToken = null;

  // Next.js cookie-session route (sets/clears the httpOnly auth cookie).
  await page.route("**/api/auth/session", async (route) => {
    const method = route.request().method();
    if (method === "POST") {
      const body = route.request().postDataJSON() as { token?: string };
      const token = body.token ?? "";
      activeSessionToken = token;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
        headers: {
          "Set-Cookie": `${AUTH_COOKIE_NAME}=${token}; Path=/; HttpOnly; SameSite=Lax`,
        },
      });
    }
    if (method === "DELETE") {
      activeSessionToken = null;
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
        headers: {
          "Set-Cookie": `${AUTH_COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax`,
        },
      });
    }
    return route.fallback();
  });

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/api/v1/auth/login" && method === "POST") {
      const body = request.postDataJSON() as { username?: string };
      const username = body.username ?? "";
      const isOperator = username === "operator_f01";
      const token = isOperator ? operatorToken : adminToken;
      activeSessionToken = token;
      return json(route, {
        token,
        token_type: "bearer",
        expires_in: 28800,
        username,
        factories: [
          { factory_id: "F-01", factory_name: "Factory 01" },
          ...(isOperator ? [] : [{ factory_id: "F-02", factory_name: "Factory 02" }]),
        ],
        job_position_ids: isOperator ? ["jp-maint"] : [],
        needs_job_position: false,
        needs_privacy_acceptance: false,
      });
    }

    if (path === "/api/v1/auth/me" && method === "GET") {
      // A guest (no session cookie) must look unauthenticated so GuestGuard
      // keeps them on the landing/login pages instead of bouncing to /chat.
      const token = sessionTokenFromRequest(request);
      if (!token) {
        return route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "unauthorized", code: "auth_required" }),
        });
      }
      return json(route, profileForToken(token));
    }

    if (path === "/api/v1/factories") {
      return json(route, [
        { factory_id: "F-01", factory_name: "Factory 01" },
        { factory_id: "F-02", factory_name: "Factory 02" },
      ]);
    }
    if (path === "/api/v1/machines") {
      return json(route, { items: machines, total: machines.length, page: 1, page_size: 50 });
    }
    if (path === "/api/v1/ingest/jobs") return json(route, []);
    if (path === "/api/v1/ingest/document-types") {
      return json(route, ["machine_manual", "sop", "knowledge_document"]);
    }
    if (path === "/api/v1/job-positions") {
      return json(route, [
        { position_id: "jp-maint", position_code: "MAINT", name_th: "ช่างซ่อมบำรุง" },
      ]);
    }
    if (path === "/api/v1/documents" || path.startsWith("/api/v1/documents/")) {
      if (path === "/api/v1/documents") {
        return json(route, {
          items: documents,
          total: documents.length,
          page: 1,
          page_size: 200,
        });
      }
      return json(route, documents[0]);
    }
    if (path === "/api/v1/chat/sessions") {
      if (method === "POST") {
        return json(route, { session_id: "session-1", title: "New chat", pinned: false });
      }
      return json(route, { items: [], total: 0, page: 1, page_size: 20 });
    }
    if (/\/api\/v1\/chat\/[^/]+\/messages$/.test(path)) {
      return json(route, { items: [], total: 0, page: 1, page_size: 50 });
    }
    if (path === "/api/v1/streams/ticket" && method === "POST") {
      return json(route, { ticket: "e2e-chat-ticket" });
    }
    if (/\/api\/v1\/chat\/[^/]+\/ask$/.test(path) && method === "POST") {
      const body = [
        "event: connected\ndata: {}",
        'event: meta\ndata: {"stream_phase":"searching","route":"rag","intent":"factual"}',
        'event: meta\ndata: {"stream_phase":"reading","route":"rag","intent":"factual"}',
        'event: token\ndata: {"delta":"นี่คือคำตอบจากเอกสารทดสอบ"}',
        'event: sources\ndata: {"sources":[{"doc_id":"doc-1","title":"MC-001 Servo Manual","source_file":"mc-001-manual.pdf","page":3,"chunk_id":"chunk-1","score":0.92,"can_view":true}]}',
        'event: done\ndata: {"assistant_message_id":"00000000-0000-4000-8000-000000000001","route":"rag","intent":"factual"}',
        "",
      ].join("\n\n");
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        headers: { "Cache-Control": "no-cache" },
        body,
      });
    }

    return json(route, {});
  });
}

function json(route: Route, value: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(value),
  });
}

async function ensureSessionCookie(page: Page, token: string): Promise<void> {
  const origins = new Set(e2eOrigins());
  if (page.url().startsWith("http")) {
    origins.add(new URL(page.url()).origin);
  }
  const cookies = [...origins].map((url) => ({
    name: AUTH_COOKIE_NAME,
    value: token,
    url,
    httpOnly: true,
    secure: false,
    sameSite: "Lax" as const,
  }));
  await page.context().addCookies(cookies);
}

async function seedUiStoreFactory(page: Page, factoryId: string): Promise<void> {
  await page.waitForLoadState("domcontentloaded");
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      await page.evaluate((fid) => {
        sessionStorage.removeItem("spark_session_redirect_guard");
        localStorage.setItem(
          "spark-ui",
          JSON.stringify({
            state: {
              sidebarExpanded: true,
              selectedFactoryId: fid,
              selectedFactoryIds: [fid],
              selectedMachineId: null,
            },
            version: 0,
          })
        );
      }, factoryId);
      return;
    } catch (err) {
      if (attempt === 2) throw err;
      await page.waitForTimeout(250);
    }
  }
}

function e2eOrigins(): string[] {
  const base = new URL(E2E_BASE_URL);
  const port = base.port || "3000";
  const origins = new Set<string>([E2E_BASE_URL]);
  if (base.hostname === "127.0.0.1") origins.add(`http://localhost:${port}`);
  if (base.hostname === "localhost") origins.add(`http://127.0.0.1:${port}`);
  return [...origins];
}

function sessionTokenFromRequest(request: Request): string | null {
  const cookieHeader = request.headers()["cookie"] ?? "";
  const match = cookieHeader.match(new RegExp(`${AUTH_COOKIE_NAME}=([^;]+)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function decodeJwtPayload(token: string): Record<string, unknown> {
  const bodyB64 = token.split(".")[1];
  if (!bodyB64) return {};
  return JSON.parse(Buffer.from(bodyB64, "base64url").toString()) as Record<string, unknown>;
}

function adminProfile(): UserProfile {
  return {
    user_id: "user-admin",
    username: "admin",
    full_name: "Test Admin",
    email: null,
    picture_url: null,
    roles: ["admin"],
    factories: [{ factory_id: "F-01", factory_name: "Factory 01" }],
    factory_access: [
      { factory_id: "F-01", access_level: "admin" },
      { factory_id: "F-02", access_level: "admin" },
    ],
    job_positions: [],
    has_password: true,
    privacy_policy_version: "2026.06",
    created_at: "2026-06-01T00:00:00Z",
  };
}

function operatorProfile(): UserProfile {
  return {
    user_id: "user-operator",
    username: "operator_f01",
    full_name: "Test Op",
    email: null,
    picture_url: null,
    roles: ["employee"],
    factories: [{ factory_id: "F-01", factory_name: "Factory 01" }],
    factory_access: [{ factory_id: "F-01", access_level: "read" }],
    job_positions: [
      { position_id: "jp-maint", position_code: "MAINT", name_th: "ช่างซ่อมบำรุง" },
    ],
    has_password: true,
    privacy_policy_version: "2026.06",
    created_at: "2026-06-01T00:00:00Z",
  };
}

function profileForToken(token: string): UserProfile {
  const payload = decodeJwtPayload(token);
  if (payload.username === "operator_f01") return operatorProfile();
  return adminProfile();
}

function tokenFor(payload: Record<string, unknown>) {
  const secret = E2E_JWT_SECRET;
  const now = Math.floor(Date.now() / 1000);
  const body = { ...payload, iat: now, exp: now + 8 * 3600 };
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const bodyB64 = Buffer.from(JSON.stringify(body)).toString("base64url");
  const sig = createHmac("sha256", secret).update(`${header}.${bodyB64}`).digest("base64url");
  return `${header}.${bodyB64}.${sig}`;
}
