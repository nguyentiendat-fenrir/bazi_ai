// T049: a person erases their data (and account) from settings; an admin erases someone else's.
import { expect, request, test, type Page } from '@playwright/test'

import { apiAs, signIn, tag } from './support'

const PASSWORD = 'mot mat khau du dai cho e2e'

async function person(baseURL: string) {
  const admin = await apiAs('admin', baseURL)
  const email = `rieng-${tag()}@example.test`
  await admin.post('/api/v1/users', { email, password: PASSWORD, role: 'reader' })
  const context = await request.newContext({ baseURL, extraHTTPHeaders: { Origin: baseURL } })
  const login = await context.post('/api/v1/auth/login', { data: { email, password: PASSWORD } })
  const csrf = (await login.json()).data.csrf_token as string
  const chart = await context.post('/api/v1/charts', { headers: { 'X-CSRF-Token': csrf }, data: {
    birth_input: { local_datetime: '1990-08-17T06:45', timezone: 'Asia/Ho_Chi_Minh', sex_for_luck: 'male' } } })
  expect(chart.status(), await chart.text()).toBe(201)
  return { email }
}

async function signInAs(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Mật khẩu').fill(PASSWORD)
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
  await expect(page.getByRole('button', { name: 'Đăng xuất' })).toBeVisible()
}

test('a person erases their data, then their account, from settings', async ({ page, baseURL }) => {
  const { email } = await person(baseURL!)
  await signInAs(page, email)
  await page.goto('/charts')
  await expect(page.getByRole('table', { name: 'Danh sách lá số' }).getByRole('row')).toHaveCount(2)

  await page.goto('/settings')
  await page.getByRole('button', { name: 'Xóa dữ liệu của tôi…' }).click()
  const dialog = page.getByRole('dialog', { name: 'Xóa dữ liệu của tôi?' })
  const submit = dialog.getByRole('button', { name: 'Xóa dữ liệu' })
  await dialog.getByLabel(/Gõ email/).fill('sai@example.test')
  await dialog.getByLabel('Mật khẩu của bạn').fill(PASSWORD)
  await expect(submit).toBeDisabled()
  await dialog.getByLabel(/Gõ email/).fill(email)
  await dialog.getByLabel('Mật khẩu của bạn').fill('sai mat khau')
  await submit.click()
  await expect(dialog.getByText('Mật khẩu không đúng.')).toBeVisible()
  await dialog.getByLabel('Mật khẩu của bạn').fill(PASSWORD)
  await submit.click()
  await expect(page.getByText('Đã xóa 1 lá số, 0 hồ sơ, 0 hội thoại, 0 ca mẫu.')).toBeVisible()
  await page.goto('/charts')
  await expect(page.getByRole('heading', { name: 'Chưa có lá số nào' })).toBeVisible()

  await page.goto('/settings')
  await page.getByRole('button', { name: 'Xóa dữ liệu của tôi…' }).click()
  await dialog.getByLabel('Xóa cả tài khoản').check()
  await dialog.getByLabel(/Gõ email/).fill(email)
  await dialog.getByLabel('Mật khẩu của bạn').fill(PASSWORD)
  await dialog.getByRole('button', { name: 'Xóa dữ liệu và tài khoản' }).click()
  await expect(page).toHaveURL(/\/login/)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Mật khẩu').fill(PASSWORD)
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
  await expect(page.locator('form').getByRole('alert')).toBeVisible()
})

test('an admin erases another person\'s data and account', async ({ page, baseURL }) => {
  const { email } = await person(baseURL!)
  await signIn(page, 'admin', '/settings/users')
  const row = page.getByRole('row', { name: new RegExp(email) })
  await row.getByRole('button', { name: `Xóa dữ liệu của ${email}` }).click()
  const dialog = page.getByRole('dialog', { name: `Xóa dữ liệu của ${email}?` })
  await expect(dialog.getByLabel('Mật khẩu của bạn')).toHaveCount(0)
  await dialog.getByLabel('Xóa cả tài khoản').check()
  await dialog.getByLabel(/Gõ email/).fill(email)
  await dialog.getByRole('button', { name: 'Xóa dữ liệu và tài khoản' }).click()
  await expect(page.getByRole('row', { name: new RegExp(email) })).toHaveCount(0)
  await expect(page.getByRole('row', { name: /deleted-.*@invalid/ }).first()).toContainText('Đã khóa')
})
