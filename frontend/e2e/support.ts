// Shared E2E helpers: stack details written by scripts/e2e_stack.py, sign-in through the
// real form, and an API client (same origin as the browser) for seeding data.
import { readFileSync } from 'node:fs'
import { expect, request, type APIRequestContext, type Page } from '@playwright/test'

export type Role = 'admin' | 'reviewer' | 'reader'

interface Stack {
  users: Record<Role, { id: string, email: string }>
  password: string
  pipeline_profile_id: string
  fixtures: { clean: string, scan: string }
  api: string
}

let cached: Stack | null = null

export function stack(): Stack {
  cached ??= JSON.parse(readFileSync(new URL('../../.cache/e2e/stack.json', import.meta.url), 'utf8'))
  return cached!
}

export async function signIn(page: Page, role: Role, next = '/') {
  await page.goto(next === '/' ? '/login' : `/login?next=${encodeURIComponent(next)}`)
  await page.getByLabel('Email').fill(stack().users[role].email)
  await page.getByLabel('Mật khẩu').fill(stack().password)
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
  await expect(page.getByRole('button', { name: 'Đăng xuất' })).toBeVisible()
}

export interface Api {
  context: APIRequestContext
  csrf: string
  post(path: string, data: unknown, headers?: Record<string, string>): Promise<any>
  get(path: string): Promise<any>
}

/** A signed-in API client for seeding; requests go through the Next origin like the UI. */
export async function apiAs(role: Role, baseURL: string): Promise<Api> {
  const context = await request.newContext({ baseURL, extraHTTPHeaders: { Origin: baseURL } })
  const login = await context.post('/api/v1/auth/login', {
    data: { email: stack().users[role].email, password: stack().password },
  })
  expect(login.status()).toBe(200)
  const csrf = (await login.json()).data.csrf_token as string
  return {
    context,
    csrf,
    async post(path, data, headers = {}) {
      const response = await context.post(path, {
        data, headers: { 'X-CSRF-Token': csrf, ...headers },
      })
      expect(response.ok(), `${path}: ${response.status()} ${await response.text()}`).toBeTruthy()
      return response.status() === 204 ? null : response.json()
    },
    async get(path) {
      const response = await context.get(path)
      expect(response.ok(), `${path}: ${response.status()}`).toBeTruthy()
      return response.json()
    },
  }
}

/** A short unique tag so every test sees only its own rows in the shared database. */
export function tag(): string {
  return Math.random().toString(36).slice(2, 8)
}

/** No horizontal page scroll at the current viewport (docs/11). */
export async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(0)
}
