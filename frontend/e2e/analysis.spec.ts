// Chart analysis by published rules: run, read claims with their sources and the trace,
// see it turn stale when the ruleset is replaced, re-evaluate.
import { expect, test, type Page } from '@playwright/test'

import { apiAs, stack, tag, uploadViaApi, waitForJob, type Api } from './support'

const PASSWORD = 'mot mat khau rieng cho luan la so'

/** A reader of its own, so this spec leaves the shared reader untouched. */
async function newReader(admin: Api): Promise<{ id: string, email: string }> {
  const email = `luan-${tag()}@example.test`
  const user = (await admin.post('/api/v1/users', { email, password: PASSWORD, role: 'reader' })).data
  return { id: user.id, email }
}

async function signInAs(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Mật khẩu').fill(PASSWORD)
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
  await expect(page.getByRole('button', { name: 'Đăng xuất' })).toBeVisible()
}

async function review(api: Api, kind: string, id: string) {
  return api.post('/api/v1/reviews', { entity_kind: kind, entity_id: id, decision: 'approve', base_revision: 1, reason: 'seed' },
    { 'Idempotency-Key': `seed-${tag()}-${tag()}` })
}

async function rule(api: Api, methodKey: string, evidence: string, claim: string, value: string) {
  const made = (await api.post('/api/v1/rules', { dsl: {
    $schema_version: 'bazi-rule/1', rule_key: `e2e.a${tag()}`, school_id: 'manh_phai', method_id: methodKey,
    fact_schema_version: 'chart-facts/1',
    when: { op: 'eq', left: { fact: 'pillars.day.stem_element' }, right: { literal: 'wood' } },
    requires: [], evidence_ids: [evidence],
    emits: [{ claim_key: claim, value, kind: 'structural' }],
    explanation_template: `Nhật chủ hành Mộc nên ${value}.` } })).data
  await api.post(`/api/v1/rules/${made.id}/validate`, { fixtures: [
    { name: 'wood', facts: { pillars: { day: { stem_element: 'wood' } } }, expect: 'fired' },
    { name: 'fire', facts: { pillars: { day: { stem_element: 'fire' } } }, expect: 'not_matched' },
    { name: 'none', facts: { pillars: { day: null } }, expect: 'pending' }] })
  await review(api, 'rule', made.id)
  return made
}

test('a reader runs a rule analysis, reads its sources, then re-evaluates a stale one', async ({ page, baseURL }) => {
  const api = await apiAs('reviewer', baseURL!)
  const upload = await uploadViaApi(api, stack().fixtures.clean_c, `Sách luận ${tag()}`)
  expect(await waitForJob(api, upload.job_id)).toBe('succeeded')
  // Readers see a book only when it is shared with them; the rule's source must be readable.
  const admin = await apiAs('admin', baseURL!)
  const reader = await newReader(admin)
  const book = (await admin.get(`/api/v1/books/${upload.book_id}`)).data
  const shared = await admin.context.patch(`/api/v1/books/${upload.book_id}/access`, {
    headers: { 'X-CSRF-Token': admin.csrf, 'If-Match': `"${book.revision}"` },
    data: { grants: [{ permission: 'read', user_id: reader.id }] } })
  expect(shared.ok(), await shared.text()).toBeTruthy()
  const pages = (await api.get(`/api/v1/book-versions/${upload.version_id}/pages`)).data
  const revision = (await api.get(`/api/v1/page-revisions/${pages[0].revision_id}`)).data
  const block = revision.blocks.find((b: { kind: string }) => b.kind === 'paragraph')
  const evidence = (await api.post('/api/v1/evidence', {
    page_revision_id: revision.id, start_offset: block.start_offset, end_offset: block.end_offset })).data.id
  const school = (await api.get('/api/v1/schools')).data.find((s: { key: string }) => s.key === 'manh_phai')
  const methodKey = `luan_${tag()}`
  const method = (await api.post('/api/v1/methods', { school_id: school.id, key: methodKey, description: 'Luận thử' })).data
  await review(api, 'method', method.id)
  const first = await rule(api, methodKey, evidence, 'test.day_element', 'vượng mộc')
  const second = await rule(api, methodKey, evidence, 'test.career', 'hợp nghề gỗ')
  const v1 = (await api.post('/api/v1/rulesets', { school_id: school.id, method_id: method.id, version: 'v1' })).data
  const current = (await api.get(`/api/v1/rulesets?method_id=${method.id}&state=published`)).data
  await api.post(`/api/v1/rulesets/${v1.id}/activate`, { expected_current_id: current[0]?.id ?? null })

  await signInAs(page, reader.email)
  await page.goto('/charts/new')
  await page.getByLabel('Ngày sinh (dương lịch)').fill('1990-08-17')
  await page.getByLabel('Giờ sinh', { exact: true }).fill('06:45')
  await page.getByRole('button', { name: 'Lập lá số' }).click()
  await expect(page).toHaveURL(/\/charts\/[0-9a-f-]{36}$/)

  const section = page.getByRole('region', { name: 'Luận theo quy tắc' })
  await section.getByLabel('Trường phái · phương pháp').selectOption({ label: `manh_phai · ${methodKey} (v1, 2 quy tắc)` })
  await section.getByRole('button', { name: 'Luận theo quy tắc' }).click()
  await expect(section.getByText('vượng mộc', { exact: true })).toBeVisible()
  await expect(section.getByText('hợp nghề gỗ', { exact: true })).toBeVisible()
  await section.getByRole('button', { name: 'Xem nguồn (1)' }).first().click()
  await expect(section.locator('.citations blockquote').first()).toContainText('mẫu C')
  await section.getByRole('group', { name: 'Đánh giá câu trả lời' }).getByRole('button', { name: 'Hữu ích' }).click()
  await expect(section.getByText('Bạn thấy hữu ích.')).toBeVisible()
  await section.getByText('Từng quy tắc đã xét (trace)').click()
  const trace = section.getByRole('table', { name: 'Từng quy tắc đã xét' })
  await expect(trace).toContainText('kích hoạt')
  await expect(trace).toContainText('pillars.day.stem_element = "wood"')

  // The source link opens the page with the quoted span marked.
  const chartUrl = page.url()
  await section.getByRole('link', { name: 'Mở trang nguồn' }).first().click()
  await expect(page).toHaveURL(/\/pages\/[0-9a-f-]{36}\?from=\d+&to=\d+/)
  await expect(page.locator('mark.quoted')).toContainText('mẫu C')
  await page.goto(chartUrl)

  // A newer ruleset without the second rule replaces v1: the analysis turns stale.
  const v2 = (await api.post('/api/v1/rulesets', { school_id: school.id, method_id: method.id, version: 'v2',
    rule_revision_ids: [first.id] })).data
  await api.post(`/api/v1/rulesets/${v2.id}/activate`, { expected_current_id: v1.id })
  expect(second.id).toBeTruthy()
  await page.reload()
  await expect(section.getByText(/Kết quả này đã cũ/)).toBeVisible()
  await section.getByRole('button', { name: 'Đánh giá lại' }).click()
  await expect(section.getByText(/Đã đánh giá lại/)).toContainText('bỏ 1 kết luận')
  await expect(section.getByText('vượng mộc', { exact: true })).toBeVisible()
  await expect(section.getByText('hợp nghề gỗ', { exact: true })).toHaveCount(0)
})

test('without a published ruleset the chart explains what is missing', async ({ page, baseURL }) => {
  await signInAs(page, (await newReader(await apiAs('admin', baseURL!))).email)
  await page.goto('/charts/new')
  await page.getByLabel('Ngày sinh (dương lịch)').fill('1975-01-02')
  await page.getByLabel('Giờ sinh', { exact: true }).fill('08:00')
  await page.getByRole('button', { name: 'Lập lá số' }).click()
  await expect(page).toHaveURL(/\/charts\/[0-9a-f-]{36}$/)
  // Other specs may have published rulesets in the shared stack; either state is explained.
  const section = page.getByRole('region', { name: 'Luận theo quy tắc' })
  await expect(section.getByRole('heading', { name: 'Chưa có bộ quy tắc nào được duyệt' })
    .or(section.getByRole('button', { name: 'Luận theo quy tắc' }))).toBeVisible()
})
