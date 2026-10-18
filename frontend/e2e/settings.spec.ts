// T048: personal settings, model profiles (fixture provider, test + activate), system settings
// and budgets, users, corpus/ontology releases, retrieval evaluation runs.
import { expect, test } from '@playwright/test'

import { apiAs, signIn, tag } from './support'

test('a reader changes a personal setting; admin-only tabs and screens stay closed', async ({ page }) => {
  await signIn(page, 'reader')
  await page.getByRole('navigation').getByRole('link', { name: 'Cài đặt' }).click()
  const tabs = page.getByRole('navigation', { name: 'Mục cài đặt' })
  await expect(tabs.getByRole('link')).toHaveCount(1)
  await page.getByLabel('Chế độ hỏi đáp mặc định').selectOption('comparison')
  await expect(page.getByText('Đã lưu.')).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Chế độ hỏi đáp mặc định')).toHaveValue('comparison')
  await expect(page.getByRole('navigation').getByRole('link', { name: 'Đánh giá' })).toHaveCount(0)
  for (const path of ['/settings/users', '/settings/models', '/settings/system', '/evaluation']) {
    await page.goto(path)
    await expect(page.getByRole('heading', { name: 'Không đủ quyền' })).toBeVisible()
  }
})

test('an admin adds fixture model profiles, tests one and switches back to the first', async ({ page }) => {
  const first = `scripted-${tag()}`
  const second = `scripted-${tag()}`
  await signIn(page, 'admin')
  await page.goto('/settings/models')
  for (const model of [first, second]) {
    await page.getByRole('button', { name: 'Profile mới' }).first().click()
    const form = page.getByRole('dialog', { name: 'Profile mô hình mới' })
    await form.getByLabel('Nhà cung cấp').selectOption('fixture-scripted')
    await form.getByLabel('Tên mô hình').fill(model)
    await form.getByLabel('Phiên bản / checksum').fill('e2e-1')
    await form.getByRole('button', { name: 'Tạo profile' }).click()
    await expect(form).toBeHidden()
  }
  const one = page.getByRole('row', { name: new RegExp(first) })
  const two = page.getByRole('row', { name: new RegExp(second) })
  await expect(two).toContainText('Đang dùng')
  await expect(one).toContainText('fixture kiểm thử')
  await two.getByRole('button', { name: `Thử ${second}` }).click()
  await expect(two).toContainText(/\d+ ms/)
  await one.getByRole('button', { name: `Dùng ${first}` }).click()
  await expect(one).toContainText('Đang dùng')
  await expect(two).not.toContainText('Đang dùng')
})

test('an admin edits a system setting and manages users', async ({ page }) => {
  const email = `nguoi-${tag()}@example.test`
  await signIn(page, 'admin')
  await page.goto('/settings/system')
  await expect(page.getByText('Cấu hình chạy')).toBeVisible()
  await expect(page.getByRole('list', { name: 'Cảnh báo vận hành' })).toContainText('BACKUP_MISSING')
  await expect(page.getByText(/Ổ lưu tệp/)).toBeVisible()
  await expect(page.getByText(/Đánh giá 7 ngày/)).toBeVisible()
  const days = page.getByRole('spinbutton', { name: 'Giữ nhật ký (ngày)' })
  await days.fill('45')
  await page.getByRole('button', { name: 'Lưu Giữ nhật ký (ngày)' }).click()
  await expect(page.getByText('Đã lưu.')).toBeVisible()
  await page.reload()
  await expect(page.getByRole('spinbutton', { name: 'Giữ nhật ký (ngày)' })).toHaveValue('45')

  await page.getByRole('link', { name: 'Người dùng' }).click()
  await page.getByRole('button', { name: 'Người dùng mới' }).first().click()
  const form = page.getByRole('dialog', { name: 'Người dùng mới' })
  await form.getByLabel('Email').fill(email)
  await form.getByLabel('Mật khẩu tạm').fill('mot mat khau du dai 123')
  await form.getByRole('button', { name: 'Tạo tài khoản' }).click()
  const row = page.getByRole('row', { name: new RegExp(email) })
  await expect(row).toBeVisible()
  await row.getByLabel(`Vai trò của ${email}`).selectOption('reviewer')
  await expect(row.getByLabel(`Vai trò của ${email}`)).toHaveValue('reviewer')
  await row.getByRole('checkbox').click()
  await expect(row).toContainText('Đã khóa')
  const mine = page.getByRole('row', { name: /bạn/ })
  await expect(mine.getByRole('combobox')).toBeDisabled()
})

test('a reviewer runs an evaluation and sees failed questions and the comparison', async ({ page, baseURL }) => {
  const api = await apiAs('reviewer', baseURL!)
  const name = `e2e-gold-${tag()}`
  await api.post('/api/v1/evaluation-datasets', { name, version: '1', items: [
    { key: 'q1', kind: 'retrieval', input: { query: 'thực thần sinh tài' },
      expected: { relevant: [{ book_version_id: crypto.randomUUID(), grade: 2, pages: [1] }] } },
    { key: 'q2', kind: 'no_answer', input: { query: 'tử vi đẩu số cung mệnh' }, expected: { no_answer: true } },
  ] })
  await signIn(page, 'reviewer')
  await page.getByRole('navigation').getByRole('link', { name: 'Đánh giá' }).click()
  await page.getByRole('button', { name, exact: true }).click()
  await page.getByText('Câu hỏi trong bộ').click()
  await expect(page.getByRole('table', { name: `Câu hỏi của bộ ${name}` })).toContainText('thực thần sinh tài')
  await page.getByRole('button', { name: 'Chạy đánh giá' }).click()
  await expect(page.getByRole('heading', { name: /Câu trượt/ })).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('listitem').filter({ hasText: 'q1' })).toBeVisible()
  const runs = page.getByRole('table', { name: 'So sánh lần chạy đánh giá' })
  await expect(runs.getByRole('row')).toHaveCount(2)
  await expect(runs).toContainText('recall@20 >= 0.9 · trượt')        // the gold page does not exist
  await page.reload()
  await expect(runs.getByRole('row')).toHaveCount(2)                  // runs come from the API

  await page.getByRole('button', { name, exact: true }).click()
  await page.getByLabel('Cách tìm').selectOption('lexical')
  await page.getByLabel('So với lần chạy').selectOption({ index: 1 })
  await page.getByRole('button', { name: 'Chạy đánh giá' }).click()
  await expect(page.getByRole('table', { name: 'So với baseline' })).toBeVisible({ timeout: 30_000 })
  await expect(runs.getByRole('row')).toHaveCount(3)
  await expect(runs).toContainText('Chỉ từ khóa')

  await page.getByRole('button', { name: 'Duyệt bộ…' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Duyệt bộ' }).click()
  await expect(page.getByRole('table', { name: 'Bộ đánh giá' }).getByRole('row', { name: new RegExp(name) })).toContainText('Đã duyệt')
})

test('a reviewer sees corpus and ontology releases', async ({ page }) => {
  await signIn(page, 'reviewer')
  await page.goto('/settings/releases')
  await expect(page.getByRole('heading', { name: 'Kho tra cứu' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Ontology' })).toBeVisible()
  await expect(page.getByText(/Không có thay đổi đã duyệt|So với/)).toBeVisible()
})
