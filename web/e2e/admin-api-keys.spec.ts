import { createHmac } from "node:crypto";
import { expect, type Page, type Route, test } from "@playwright/test";

const E2E_JWT_SECRET = process.env.JWT_SECRET ?? "dev-secret-change-me";
const AUTH_COOKIE_NAME = "spark_token";
const E2E_BASE_URL =
  process.env.PLAYWRIGHT_BASE_URL ??
  `http://localhost:${process.env.PLAYWRIGHT_PORT ?? 3000}`;

const adminToken = tokenFor({
  username: "admin",
  roles: ["admin"],
  factory_access: { "F-01": "admin" },
  job_position_ids: [],
  privacy_policy_version: "2026.06",
});

type MockKey = {
  key_id: string;
  name: string;
  key_prefix: string;
  user_id: string;
  username: string;
  is_active: boolean;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

test("admin issues, reveals once, revokes, and deletes an API key", async ({ page }) => {
  test.setTimeout(60_000);
  const keys: MockKey[] = [];

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();

    if (path === "/api/v1/auth/me") return json(route, adminProfile());
    if (path === "/api/v1/factories" || path === "/api/v1/admin/factories") {
      return json(route, [{ factory_id: "F-01", factory_name: "Factory 01" }]);
    }
    if (path === "/api/v1/job-positions" || path === "/api/v1/admin/job-positions") {
      return json(route, []);
    }
    if (path === "/api/v1/alerts") {
      return json(route, { items: [], total: 0, page: 1, page_size: 50 });
    }
    if (path === "/api/v1/admin/users") {
      return json(route, {
        items: [
          {
            user_id: "user-svc-1",
            username: "svc_partner_x",
            full_name: "Partner X Service Account",
            email: null,
            is_active: true,
            roles: ["employee"],
            factory_access: [{ factory_id: "F-01", access_level: "read" }],
            job_position_ids: [],
            token_version: 0,
          },
        ],
        total: 1,
        page: 1,
        page_size: 100,
      });
    }
    if (path === "/api/v1/admin/api-keys" && method === "GET") {
      return json(route, keys);
    }
    if (path === "/api/v1/admin/api-keys" && method === "POST") {
      const body = request.postDataJSON() as { name: string; user_id: string };
      const created: MockKey = {
        key_id: "key-1",
        name: body.name,
        key_prefix: "nk_e2etest0",
        user_id: body.user_id,
        username: "svc_partner_x",
        is_active: true,
        expires_at: null,
        last_used_at: null,
        revoked_at: null,
        created_at: new Date().toISOString(),
      };
      keys.push(created);
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ ...created, api_key: "nk_e2etest0secret" }),
      });
    }
    if (/\/api\/v1\/admin\/api-keys\/[^/]+\/revoke$/.test(path) && method === "POST") {
      const revoked = keys[0];
      revoked.is_active = false;
      revoked.revoked_at = new Date().toISOString();
      return json(route, revoked);
    }
    if (/\/api\/v1\/admin\/api-keys\/[^/]+$/.test(path) && method === "DELETE") {
      keys.length = 0;
      return route.fulfill({ status: 204, body: "" });
    }
    return json(route, {});
  });

  await ensureSessionCookie(page, adminToken);
  await page.goto("/admin");
  await page.getByRole("button", { name: "API keys" }).click();

  await expect(page.getByText("ยังไม่มี API key")).toBeVisible();

  await page.getByLabel("ชื่อ (สื่อว่าให้ใครใช้)").fill("partner-x-website");
  await page
    .locator("select")
    .first()
    .selectOption({ label: "svc_partner_x (Partner X Service Account)" });
  await page.getByRole("button", { name: "ออก API key", exact: true }).click();

  // reveal-once modal
  await expect(page.getByText("nk_e2etest0secret")).toBeVisible();
  await expect(page.getByText(/จะไม่แสดง key เต็มอีก/)).toBeVisible();
  await page.keyboard.press("Escape");

  // row in table
  await expect(page.getByRole("cell", { name: "partner-x-website" })).toBeVisible();
  await expect(page.getByText("nk_e2etest0…")).toBeVisible();
  await expect(page.getByText("ใช้งาน", { exact: true })).toBeVisible();

  // revoke
  await page.getByRole("button", { name: "เพิกถอน", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "เพิกถอน" }).click();
  await expect(page.getByText("เพิกถอนแล้ว")).toBeVisible();

  // delete
  await page.getByRole("button", { name: "ลบ", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "ลบถาวร" }).click();
  await expect(page.getByText("ยังไม่มี API key")).toBeVisible();
});

function json(route: Route, value: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(value),
  });
}

async function ensureSessionCookie(page: Page, token: string): Promise<void> {
  const base = new URL(E2E_BASE_URL);
  const port = base.port || "3000";
  const origins = new Set<string>([E2E_BASE_URL]);
  if (base.hostname === "localhost") origins.add(`http://127.0.0.1:${port}`);
  if (base.hostname === "127.0.0.1") origins.add(`http://localhost:${port}`);
  await page.context().addCookies(
    [...origins].map((url) => ({
      name: AUTH_COOKIE_NAME,
      value: token,
      url,
      httpOnly: true,
      secure: false,
      sameSite: "Lax" as const,
    }))
  );
}

function adminProfile() {
  return {
    user_id: "user-admin",
    username: "admin",
    full_name: "Test Admin",
    email: null,
    picture_url: null,
    roles: ["admin"],
    factories: [{ factory_id: "F-01", factory_name: "Factory 01" }],
    factory_access: [{ factory_id: "F-01", access_level: "admin" }],
    job_positions: [],
    has_password: true,
    privacy_policy_version: "2026.06",
    created_at: "2026-06-01T00:00:00Z",
  };
}

function tokenFor(payload: Record<string, unknown>) {
  const now = Math.floor(Date.now() / 1000);
  const body = { ...payload, iat: now, exp: now + 8 * 3600 };
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const bodyB64 = Buffer.from(JSON.stringify(body)).toString("base64url");
  const sig = createHmac("sha256", E2E_JWT_SECRET).update(`${header}.${bodyB64}`).digest("base64url");
  return `${header}.${bodyB64}.${sig}`;
}
