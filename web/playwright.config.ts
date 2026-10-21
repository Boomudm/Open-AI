import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.PLAYWRIGHT_PORT ?? 3000);
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? `http://localhost:${port}`;
const handoverLive = process.env.HANDOVER_E2E === "1";
const e2eJwtSecret = process.env.JWT_SECRET ?? "dev-secret-change-me";

export default defineConfig({
  testDir: "./e2e",
  retries: 1,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  webServer: handoverLive
    ? undefined
    : {
        command: `npm run dev -- -H localhost -p ${port}`,
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        env: {
          JWT_SECRET: e2eJwtSecret,
        },
      },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
      grepInvert: handoverLive ? /@live/ : undefined,
    },
    ...(handoverLive
      ? [
          {
            name: "live-handover",
            use: { ...devices["Desktop Chrome"] },
            grep: /@live/,
          },
        ]
      : []),
  ],
});
