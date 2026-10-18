// T045: conversations, context, a streamed answer (no model configured in E2E, so the
// orchestrator's deterministic fallback answers), opening chat from a chart, deletion.
import { expect, test } from '@playwright/test'

import { expectNoHorizontalOverflow, signIn, tag } from './support'

test('a user asks a question and gets a checked answer over the event stream', async ({ page }) => {
  await signIn(page, 'reviewer')
  await page.getByRole('link', { name: 'Hỏi đáp' }).click()
  await page.getByRole('button', { name: 'Hội thoại mới' }).click()
  await expect(page).toHaveURL(/\/chat\?c=[0-9a-f-]{36}$/)
  const question = `Thất sát là gì ${tag()}`
  await page.getByLabel('Câu hỏi').fill(question)
  await page.getByRole('button', { name: 'Gửi' }).click()
  await expect(page.locator('.message-user').last()).toHaveText(question)
  await expect(page.locator('.message-assistant .answer').last()).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('button', { name: 'Gửi' })).toBeVisible()
  await expectNoHorizontalOverflow(page)

  // Rate the answer: private, kept after a reload.
  const rating = page.getByRole('group', { name: 'Đánh giá câu trả lời' }).last()
  await rating.getByRole('button', { name: 'Chưa đúng…' }).click()
  await rating.getByLabel('Thiếu nguồn').check()
  await rating.getByRole('button', { name: 'Gửi đánh giá' }).click()
  await expect(rating.getByText('Bạn đã báo chưa đúng.')).toBeVisible()
  await page.reload()
  await expect(page.getByRole('group', { name: 'Đánh giá câu trả lời' }).last().getByText('Bạn đã báo chưa đúng.')).toBeVisible()
})

test('context changes are saved and survive a reload', async ({ page }) => {
  await signIn(page, 'reviewer')
  await page.goto('/chat')
  await page.getByRole('button', { name: 'Hội thoại mới' }).click()
  await expect(page).toHaveURL(/\/chat\?c=/)
  await page.getByLabel('Chế độ').selectOption('comparison')
  await page.getByRole('button', { name: 'Áp dụng ngữ cảnh' }).click()
  await expect(page.getByRole('button', { name: 'Áp dụng ngữ cảnh' })).toHaveCount(0)
  await page.reload()
  await expect(page.getByLabel('Chế độ')).toHaveValue('comparison')
})

test('asking about a chart opens a chart conversation; deleting one asks first', async ({ page }) => {
  await signIn(page, 'reviewer')
  await page.goto('/charts/new')
  await page.getByLabel('Ngày sinh (dương lịch)').fill('1985-02-10')
  await page.getByLabel('Giờ sinh', { exact: true }).fill('10:15')
  await page.getByRole('button', { name: 'Lập lá số' }).click()
  await expect(page).toHaveURL(/\/charts\/[0-9a-f-]{36}$/)
  await page.getByRole('link', { name: 'Hỏi về lá số này' }).click()
  await expect(page).toHaveURL(/\/chat\?c=/)
  await expect(page.getByLabel('Chế độ')).toHaveValue('chart_analysis')
  await expect(page.getByLabel('Lá số')).not.toHaveValue('')

  const items = page.getByRole('complementary', { name: 'Hội thoại' }).getByRole('listitem')
  const before = await items.count()
  await items.first().getByRole('button').click()
  const dialog = page.getByRole('dialog', { name: 'Xóa hội thoại?' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Xóa hội thoại' }).click()
  await expect(items).toHaveCount(before - 1)
})
