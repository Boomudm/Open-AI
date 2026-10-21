/**
 * Live factory handover E2E — requires running API (:8000) and web (:3000).
 *
 *   HANDOVER_E2E=1 npx playwright test e2e/handover-flow.spec.ts --project=live-handover
 */
import { execSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { expect, test } from "@playwright/test";

const API_BASE = process.env.HANDOVER_API_BASE ?? "http://127.0.0.1:8000";
const repoRoot = path.resolve(__dirname, "../..");

const qaId = `SPARK-UI-HANDOVER-${new Date().toISOString().replace(/[-:]/g, "").slice(0, 15)}Z`;
const docxPath = path.join(os.tmpdir(), `${qaId}.docx`);

test.describe("@live Factory handover flow", () => {
  test.skip(
    process.env.HANDOVER_E2E !== "1",
    "Set HANDOVER_E2E=1 with API + web already running"
  );

  test.beforeAll(() => {
    const pyScript = path.join(os.tmpdir(), `handover-docx-${qaId}.py`);
    fs.writeFileSync(
      pyScript,
      `from docx import Document
doc = Document()
doc.add_heading("Factory handover UI proof ${qaId}", level=1)
doc.add_paragraph("The torque audit reserve for ${qaId} is exactly 64 newton meters.")
doc.add_paragraph("When someone asks how much torque audit reserve is required for ${qaId}, answer 64 newton meters.")
doc.add_paragraph("คำถามภาษาไทย: torque audit reserve สำหรับ ${qaId} เท่าไหร่ คำตอบคือ 64 newton meters.")
doc.add_paragraph("This uploaded DOCX is the authoritative source for ${qaId}.")
doc.save(${JSON.stringify(docxPath)})
`,
      "utf-8"
    );
    execSync(`${path.join(repoRoot, ".venv/bin/python")} ${JSON.stringify(pyScript)}`, {
      cwd: repoRoot,
      stdio: "pipe",
    });
    expect(fs.existsSync(docxPath)).toBeTruthy();
  });

  test("admin uploads docx then employee gets cited chat answer", async ({ page, request }) => {
    test.setTimeout(240_000);

    await page.goto("/login");
    await page.locator('input[name="username"]').fill("admin");
    await page.locator('input[name="password"]').fill("changeme");
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await page.waitForURL(/\/chat(?:\?.*)?$/, { timeout: 30_000 });

    await page.goto("/upload");
    await expect(page.getByTestId("upload-form")).toBeVisible({ timeout: 30_000 });
    await page.locator("#ingest-file").setInputFiles(docxPath);
    await page.getByLabel("ประเภทเอกสาร").selectOption("knowledge_document");
    const factorySelect = page.getByLabel("โรงงาน");
    if (await factorySelect.count()) {
      await factorySelect.selectOption("F-01");
    }
    await page.getByLabel("ชื่อเอกสาร").fill(`${qaId} UI handover proof`);
    await page.getByRole("button", { name: "อัปโหลด" }).click();
    await expect(page.getByText("อัปโหลดสำเร็จ")).toBeVisible({ timeout: 30_000 });

    const formText = await page.getByTestId("upload-form").innerText();
    const jobId = formText.match(
      /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i
    )?.[0];
    expect(jobId, formText).toBeTruthy();

    let job: { status?: string; chunks_count?: number } = {};
    await expect
      .poll(
        async () => {
          const res = await request.get(`${API_BASE}/api/v1/ingest/jobs/${jobId}`);
          if (!res.ok()) return null;
          job = (await res.json()) as { status?: string; chunks_count?: number };
          return job.status;
        },
        { timeout: 120_000, intervals: [2_000] }
      )
      .toBe("completed");
    expect((job.chunks_count ?? 0) > 0).toBeTruthy();

    await page.goto("/login?switch=1");
    await page.locator('input[name="username"]').fill("employee_f01");
    await page.locator('input[name="password"]').fill("changeme");
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await expect(page.getByRole("heading", { name: "เลือกโรงงาน" })).toBeVisible({
      timeout: 30_000,
    });
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await page.waitForURL(/\/chat(?:\?.*)?$/, { timeout: 30_000 });

    await page.getByLabel("Chat message").fill(
      `According to ${qaId}, what torque audit reserve is required?`
    );
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.getByTestId("chat-thinking")).toBeVisible({ timeout: 10_000 });

    await expect
      .poll(
        async () => page.getByText(/64 newton meters/i).count(),
        { timeout: 180_000, intervals: [3_000] }
      )
      .toBeGreaterThan(0);

    await page.getByLabel("Chat message").fill(
      `torque audit reserve สำหรับ ${qaId} เท่าไหร่ จากเอกสารที่อัปโหลด?`
    );
    await page.getByRole("button", { name: "Send message" }).click();

    await expect
      .poll(
        async () => page.getByText(/64 newton meters/i).count(),
        { timeout: 180_000, intervals: [3_000] }
      )
      .toBeGreaterThan(1);

    const sourcesBtn = page.getByRole("button", { name: /sources|แหล่งอ้างอิง/i });
    if (await sourcesBtn.count()) {
      await sourcesBtn.first().click();
    }
    await expect(page.getByText(`${qaId}.docx`)).toBeVisible({ timeout: 30_000 });
  });
});
