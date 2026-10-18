// Frontend E2E against the real API and PostgreSQL (docs/11 · Frontend verification).
//
//   set -a; . ./.env; set +a
//   export BAZI_TEST_DATABASE_URL="host=127.0.0.1 port=55432 dbname=postgres user=... password=..."
//   cd frontend && npx playwright test
//
// The browser is the installed Edge on Windows (E2E_BROWSER_CHANNEL=chrome or "" for the
// Playwright build on Linux after `npx playwright install chromium`).
import { defineConfig } from '@playwright/test'

const API_PORT = Number(process.env.E2E_API_PORT ?? 18765)
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 3100)
const WEB = `http://127.0.0.1:${WEB_PORT}`
const python = process.env.E2E_PYTHON
  ?? (process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python')
const channel = process.env.E2E_BROWSER_CHANNEL ?? (process.platform === 'win32' ? 'msedge' : '')

export default defineConfig({
  testDir: './e2e',
  // One shared database: tests create their own data and never assume a global count.
  workers: 1,
  fullyParallel: false,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [['list']],
  outputDir: '../.cache/e2e/results',
  use: {
    baseURL: WEB,
    ...(channel ? { channel } : {}),
    locale: 'vi-VN',
    viewport: { width: 1280, height: 720 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `"${python}" -B -X utf8 ../scripts/e2e_stack.py --port ${API_PORT} --origin ${WEB}`,
      url: `http://127.0.0.1:${API_PORT}/api/v1/health/live`,
      timeout: 180_000,
      reuseExistingServer: false,
      stdout: 'pipe',
    },
    {
      command: `npm run build && npx next start -H 127.0.0.1 -p ${WEB_PORT}`,
      url: `${WEB}/login`,
      timeout: 300_000,
      reuseExistingServer: false,
      env: { BAZI_API_ORIGIN: `http://127.0.0.1:${API_PORT}`, NEXT_TELEMETRY_DISABLED: '1' },
    },
  ],
})
