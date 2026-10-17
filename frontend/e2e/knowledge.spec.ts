// T047: concept/term review, assertion and rule approval with their checklists, ruleset
// build + activation, revoke with impact, cases screen; readers have no access.
import { expect, test, type Page } from '@playwright/test'

import { apiAs, signIn, stack, tag, uploadViaApi, waitForJob, type Api } from './support'

test.describe.configure({ mode: 'serial' })

interface Seed { api: Api, school: { id: string, key: string, label: string }, methodKey: string, methodId: string,
  assertionId: string, ruleId: string, ruleKey: string }
let seed: Seed

const FIXTURES = [
  { name: 'wood', facts: { pillars: { day: { stem_element: 'wood' } } }, expect: 'fired' },
  { name: 'fire', facts: { pillars: { day: { stem_element: 'fire' } } }, expect: 'not_matched' },
  { name: 'no-day', facts: { pillars: { day: null } }, expect: 'pending' },
]

async function review(api: Api, kind: string, id: string, base = 1) {
  return api.post('/api/v1/reviews', { entity_kind: kind, entity_id: id, decision: 'approve', base_revision: base, reason: 'seed' },
    { 'Idempotency-Key': `seed-${tag()}-${tag()}` })
}

test.beforeAll(async ({ baseURL }) => {
  const api = await apiAs('reviewer', baseURL!)
  const upload = await uploadViaApi(api, stack().fixtures.knowledge, `Sách tri thức ${tag()}`)
  expect(await waitForJob(api, upload.job_id)).toBe('succeeded')
  const pages = (await api.get(`/api/v1/book-versions/${upload.version_id}/pages`)).data
  const revision = (await api.get(`/api/v1/page-revisions/${pages[0].revision_id}`)).data
  const block = revision.blocks.find((b: { kind: string }) => b.kind === 'paragraph')
  const evidence = (await api.post('/api/v1/evidence', {
    page_revision_id: revision.id, start_offset: block.start_offset, end_offset: block.end_offset })).data
  const school = (await api.get('/api/v1/schools')).data.find((s: { key: string }) => s.key === 'manh_phai')
  const methodKey = `m_${tag()}`
  const method = (await api.post('/api/v1/methods', { school_id: school.id, key: methodKey, description: 'Phép xét thử E2E' })).data
  await review(api, 'method', method.id)
  const assertion = (await api.post('/api/v1/assertions', {
    school_id: school.id, statement: `Thực thần sinh tài thì giàu ${tag()}.`, origin: 'source_explicit', evidence_ids: [evidence.id] })).data
  const ruleKey = `e2e.r${tag()}`
  const rule = (await api.post('/api/v1/rules', { dsl: {
    $schema_version: 'bazi-rule/1', rule_key: ruleKey, school_id: 'manh_phai', method_id: methodKey,
    fact_schema_version: 'chart-facts/1',
    when: { op: 'eq', left: { fact: 'pillars.day.stem_element' }, right: { literal: 'wood' } },
    requires: [], evidence_ids: [evidence.id],
    emits: [{ claim_key: 'test.day_element', value: 'wood', kind: 'structural' }],
    explanation_template: 'Nhật can thuộc Mộc.' } })).data
  await api.post(`/api/v1/rules/${rule.id}/validate`, { fixtures: FIXTURES })
  seed = { api, school, methodKey, methodId: method.id, assertionId: assertion.id, ruleId: rule.id, ruleKey }
})

async function decide(page: Page, button: string, reason: string, checks = 0) {
  await page.getByRole('button', { name: button, exact: true }).click()
  const dialog = page.getByRole('dialog')
  const confirm = dialog.getByRole('button', { name: 'Xác nhận' })
  await dialog.getByLabel('Lý do').fill(reason)
  if (checks) {
    await expect(confirm).toBeDisabled()
    const boxes = dialog.getByRole('checkbox')
    await expect(boxes).toHaveCount(checks)
    for (let i = 0; i < checks; i++) await boxes.nth(i).check()
  }
  await confirm.click()
  await expect(dialog).toBeHidden()
}

test('a reviewer creates a concept, adds a term and approves both', async ({ page }) => {
  const key = `e2e.concept_${tag()}`
  await signIn(page, 'reviewer')
  await page.getByRole('navigation').getByRole('link', { name: 'Tri thức' }).click()
  await page.getByRole('button', { name: 'Khái niệm mới' }).first().click()
  const form = page.getByRole('dialog', { name: 'Khái niệm mới' })
  await form.getByLabel('Trường phái').selectOption({ label: seed.school.label })
  await form.getByLabel('Tên hiển thị').fill(`Thất Sát ${key}`)
  await form.getByLabel('Khóa chuẩn').fill(key)
  await form.getByRole('button', { name: 'Tạo bản nháp' }).click()
  await expect(page).toHaveURL(/\/knowledge\/concepts\/[0-9a-f-]{36}$/)
  await expect(page.getByText('Bản nháp').first()).toBeVisible()

  await page.getByLabel('Thêm cách gọi').fill(`Thiên Quan ${key}`)
  await page.getByRole('button', { name: 'Thêm', exact: true }).click()
  await expect(page.getByRole('table', { name: 'Thuật ngữ của khái niệm' })).toContainText(`Thiên Quan ${key}`)

  await decide(page, 'Duyệt', 'đúng nghĩa trong sách')
  await expect(page.getByText(/Trạng thái mới: Đã duyệt/)).toBeVisible()
  await page.getByRole("button", { name: `Duyệt “Thiên Quan ${key}”`, exact: true }).click()
  await page.getByRole('dialog').getByLabel('Lý do').fill('cùng nghĩa')
  await page.getByRole('dialog').getByRole('button', { name: 'Xác nhận' }).click()
  await expect(page.getByRole('table', { name: 'Thuật ngữ của khái niệm' }).getByText('Đã duyệt')).toHaveCount(2)

  await page.goto('/knowledge/terms')
  await page.getByLabel('Tìm khái niệm hoặc thuật ngữ').fill(`thien quan ${key}`)
  await expect(page.getByText(`Thiên Quan ${key}`)).toBeVisible()
})

test('approving an assertion and a rule needs the checklist; rulesets activate; revoke shows impact', async ({ page }) => {
  await signIn(page, 'reviewer')
  await page.goto(`/knowledge/assertions/${seed.assertionId}`)
  await expect(page.locator('.citations blockquote')).toContainText('thực thần sinh tài')
  await decide(page, 'Duyệt', 'nguồn nói rõ', 2)
  await expect(page.getByText(/Trạng thái mới: Đã duyệt/)).toBeVisible()

  await page.goto(`/knowledge/rules/${seed.ruleId}`)
  await page.getByRole('button', { name: 'Kiểm tra' }).click()
  await expect(page.getByText('DSL hợp lệ.')).toBeVisible()
  await expect(page.getByRole('table', { name: 'Fixture của quy tắc' }).getByText('đạt', { exact: true })).toHaveCount(3)
  await decide(page, 'Duyệt', 'đã đối chiếu nguồn và fixture', 3)
  await expect(page.getByText(/Trạng thái mới: Đã duyệt/)).toBeVisible()

  await page.getByRole('link', { name: 'Bộ quy tắc' }).click()
  await page.getByLabel('Trường phái').selectOption({ label: seed.school.label })
  await page.getByLabel('Phương pháp đã duyệt').selectOption({ label: `manh_phai · ${seed.methodKey}` })
  await page.getByLabel('Phiên bản bộ mới').fill('e2e.1')
  await page.getByRole('button', { name: 'Dựng bộ từ quy tắc đã duyệt' }).click()
  await expect(page.getByText(/Đã dựng bộ e2e.1 với 1 quy tắc/)).toBeVisible()
  await page.getByRole('button', { name: 'Kích hoạt…' }).click()
  await expect(page.getByRole('dialog')).toContainText('chưa có bộ đang dùng')
  await page.getByRole('dialog').getByRole('button', { name: 'Kích hoạt' }).click()
  await expect(page.getByText(/Đang dùng bộ e2e.1/)).toBeVisible()
  await page.getByRole('button', { name: 'e2e.1' }).click()
  await expect(page.getByRole('link', { name: seed.ruleKey })).toBeVisible()

  await page.goto(`/knowledge/rules/${seed.ruleId}`)
  await page.getByRole('button', { name: 'Thu hồi…' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.locator('.notice')).toBeVisible()
  await dialog.getByLabel('Lý do').fill('sai điều kiện')
  await dialog.getByRole('button', { name: 'Xác nhận' }).click()
  await expect(page.getByText(/Trạng thái mới: Đã thu hồi/)).toBeVisible()
})

test('a draft rule revision is made from edited JSON; invalid JSON blocks saving', async ({ page }) => {
  await signIn(page, 'reviewer')
  await page.goto(`/knowledge/rules/${seed.ruleId}`)
  await page.getByRole('button', { name: 'Sửa thành bản mới' }).click()
  const editor = page.getByLabel('DSL (JSON)')
  const original = await editor.inputValue()
  await editor.fill(`${original},`)
  await expect(page.getByText(/JSON không hợp lệ/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Lưu bản nháp' })).toBeDisabled()
  await editor.fill(original.replace('Nhật can thuộc Mộc.', 'Nhật chủ hành Mộc.'))
  await page.getByLabel('Lý do sửa').fill('rõ câu chữ')
  await page.getByRole('button', { name: 'Lưu bản nháp' }).click()
  await expect(page).not.toHaveURL(new RegExp(seed.ruleId))
  await expect(page.getByText(/bản 2/)).toBeVisible()
  await expect(page.getByText('Nhật chủ hành Mộc.').first()).toBeVisible()
})

test('cases and knowledge screens are closed to readers', async ({ page }) => {
  await signIn(page, 'reader')
  await expect(page.getByRole('navigation').getByRole('link', { name: 'Tri thức' })).toHaveCount(0)
  for (const path of ['/knowledge/terms', '/knowledge/rules', '/cases']) {
    await page.goto(path)
    await expect(page.getByRole('heading', { name: "Không đủ quyền" })).toBeVisible()
  }
})

test('the cases screen lists with filters and explains an empty result', async ({ page }) => {
  await signIn(page, 'reviewer')
  await page.goto('/cases')
  await page.getByLabel('Nguồn gốc').selectOption('synthetic_test')
  await expect(page.getByRole('heading', { name: /Không có ca khớp|Chưa có ca mẫu/ })).toBeVisible()
})

test('a case with no hour pillar gets one in a new draft revision, then is deleted', async ({ page }) => {
  const made = (await seed.api.post('/api/v1/cases', {
    origin: 'synthetic_test', school_id: seed.school.id, narrative: 'Ca thử: người này làm quan.',
    claimed_events: ['Đỗ đạt năm 30 tuổi'],
    chart_payload: { schema: 'book-case/1', sex_for_luck: 'male', luck_pillars: [], luck_start_ages: null, source_text: '',
      pillars: { year: { stem: 'jia', branch: 'zi' }, month: { stem: 'bing', branch: 'yin' }, day: { stem: 'wu', branch: 'chen' }, hour: null } },
  })).data
  await signIn(page, 'reviewer')
  await page.goto(`/cases/${made.id}`)
  const pillars = page.getByRole('table', { name: 'Tứ trụ của ca' })
  await expect(pillars).toContainText('Giáp Tý')
  await expect(pillars).toContainText('Nguồn không ghi')
  await expect(page.getByText('Đỗ đạt năm 30 tuổi')).toBeVisible()
  await page.getByRole('button', { name: 'Sửa thành bản mới' }).click()
  await page.getByLabel('Can trụ giờ').selectOption('ren')
  await page.getByLabel('Chi trụ giờ').selectOption('zi')
  await page.getByLabel('Lý do sửa').fill('bổ sung giờ theo bản in khác')
  await page.getByRole('button', { name: 'Lưu bản nháp' }).click()
  await expect(page.getByText(/Đã lưu bản nháp mới/)).toBeVisible()
  await expect(pillars).toContainText('Nhâm Tý')
  await expect(page.getByText(/bản 2/)).toBeVisible()
  await page.getByRole('button', { name: 'Xóa ca' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Xóa ca' }).click()
  await expect(page).toHaveURL(/\/cases$/)
})
