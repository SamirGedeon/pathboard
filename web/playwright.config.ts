import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5180",
    headless: true,
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined,
    },
  },
  webServer: [
    {
      command:
        "APP_ORIGIN=http://localhost:5180 DB_PATH=../var/e2e.sqlite WEB_DIR=dist ../backend/.venv/bin/uvicorn --app-dir ../backend pathboard.main:create_app --factory --no-proxy-headers --host 0.0.0.0 --port 8000",
      url: "http://localhost:8000/api/health",
      reuseExistingServer: false,
    },
    {
      command: "npm run dev",
      url: "http://localhost:5180",
      reuseExistingServer: false,
    },
  ],
});
