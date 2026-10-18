// Library search: passages with book, page and author layer; accent-free queries; links
// open the page at the passage; the query stays in the URL; chat can be limited to books.
import { expect, test } from '@playwright/test'

import { apiAs, signIn, stack, tag, uploadViaApi, waitForJob } from './support'

test('a reviewer finds a passage without diacritics and opens it on its page', async ({ page, baseURL }) => {
  const api = await apiAs('reviewer', baseURL!)
  const title = `Sách tra cứu ${tag()}`
  const upload = await uploadViaApi(api, stack().fixtures.search, title)
  expect(await waitForJob(api, upload.job_id)).toBe('succeeded')
  const job = (await api.get(`/api/v1/jobs/${upload.job_id}`)).data
  await api.post(`/api/v1/generations/${job.generation_id}/publish`, { activate: true },
    { 'Idempotency-Key': `pub-${tag()}` })

  await signIn(page, 'reviewer')
  await page.getByRole('navigation').getByRole('link', { name: 'Tra cứu' }).click()
  await expect(page.getByRole('heading', { name: 'Nhập nội dung để tìm' })).toBeVisible()
  await page.getByLabel('Nội dung cần tìm').fill('sach tra cuu trang 2')
  await page.getByLabel('Sách').selectOption({ label: title })
  await page.getByRole('button', { name: 'Tìm', exact: true }).click()
  await expect(page).toHaveURL(/\/search\?q=sach\+tra\+cuu/)
  const first = page.locator('.passage').first()
  await expect(first).toContainText(title)
  await expect(first).toContainText('trang 2')
  await expect(first).toContainText('chưa rõ lớp')               // author layer shown

  await page.reload()                                          // the search is in the URL
  await expect(page.getByLabel('Nội dung cần tìm')).toHaveValue('sach tra cuu trang 2')
  await page.locator('.passage').first().getByRole('link', { name: 'Mở trang sách' }).click()
  await expect(page).toHaveURL(/\/pages\/[0-9a-f-]{36}\?from=\d+&to=\d+/)
  await expect(page.locator('.block-selected')).toBeVisible()

  await page.goto(`/search?q=${encodeURIComponent('zzqqxx khong ton tai')}`)
  await expect(page.getByRole('heading', { name: 'Không có kết quả' })).toBeVisible()
})

test('a conversation can be limited to chosen books', async ({ page }) => {
  await signIn(page, 'reviewer')
  await page.goto('/chat')
  await page.getByRole('button', { name: 'Hội thoại mới' }).click()
  await expect(page).toHaveURL(/\/chat\?c=/)
  await page.getByText('Mọi sách được xem').click()
  const box = page.locator('.book-limit').getByRole('checkbox').first()
  await box.check()
  await page.getByRole('button', { name: 'Áp dụng ngữ cảnh' }).click()
  await expect(page.getByRole('button', { name: 'Áp dụng ngữ cảnh' })).toHaveCount(0)
  await page.reload()
  await expect(page.getByText('Chỉ trong 1 sách')).toBeVisible()
})
