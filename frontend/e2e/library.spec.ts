// T046.1: upload → job → review → publish, conflicts (412), failed jobs and permissions.
import { expect, test } from '@playwright/test'

import { apiAs, signIn, stack, tag, uploadViaApi, waitForJob } from './support'

test('a reviewer uploads, follows the job and publishes into the search corpus', async ({ page }) => {
  const title = `Sách mẫu A ${tag()}`
  await signIn(page, 'reviewer')
  await page.getByRole('navigation').getByRole('link', { name: 'Tải sách lên' }).click()
  await expect(page.getByLabel('Cách xử lý')).toHaveValue(stack().pipeline_profile_id)
  await page.getByLabel('Quyền sử dụng').selectOption('private_reference')
  await page.locator('input[type="file"]').setInputFiles([stack().fixtures.clean_a, stack().fixtures.not_pdf])
  await page.getByLabel('Tên sách cho sach-mau-a.pdf').fill(title)
  await page.getByRole('button', { name: 'Bắt đầu tải lên' }).click()

  const bad = page.locator('tr[data-file="khong-phai-pdf.pdf"]')
  await expect(bad).toContainText('Bị từ chối')
  await expect(bad).toContainText('UNSUPPORTED_TYPE')
  await expect(bad.getByRole('button', { name: 'Thử lại tệp này' })).toBeVisible()
  const good = page.locator('tr[data-file="sach-mau-a.pdf"]')
  await expect(good).toContainText('Đã nhận')
  await expect(page.getByText(/1 nhận, 0 trùng, 1 bị từ chối/)).toBeVisible()

  await good.getByRole('link', { name: 'Theo dõi job' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Hoàn tất', { timeout: 60_000 })
  await expect(page.getByRole('cell', { name: 'Niêm phong' })).toBeVisible()
  await expect(page.getByText('Job hoàn tất')).toBeVisible()

  await page.getByRole('link', { name: /phiên bản v1/ }).click()
  await expect(page.getByText('Sẵn sàng publish')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Xem trang 3' })).toBeVisible()
  await page.getByRole('button', { name: 'Publish…' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('3/3 trang đạt')
  await dialog.getByRole('button', { name: 'Publish' }).click()
  await expect(page.getByText(/Đã publish: release .* đang được dùng/)).toBeVisible()
  await expect(page.getByText('Đã publish', { exact: true })).toBeVisible()

  await page.getByRole('link', { name: 'Thư viện sách' }).click()
  await page.getByLabel('Tìm sách').fill(title)
  await expect(page.getByRole('row').filter({ hasText: title })).toContainText('3/3 trang')

  // The same bytes again are a duplicate of the version just published, not a new book.
  await page.goto('/books/upload')
  await page.locator('input[type="file"]').setInputFiles([stack().fixtures.clean_a])
  await page.getByRole('button', { name: 'Bắt đầu tải lên' }).click()
  const again = page.locator('tr[data-file="sach-mau-a.pdf"]')
  await expect(again).toContainText('Trùng tệp đã có')
  await again.getByRole('link', { name: 'Mở phiên bản đã có' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toContainText(title)
})

test('a scanned page is reviewed against its image, excluded, then published partially', async ({ page, baseURL }) => {
  const api = await apiAs('reviewer', baseURL!)
  const title = `Sách có trang quét ${tag()}`
  const upload = await uploadViaApi(api, stack().fixtures.scan, title)
  expect(await waitForJob(api, upload.job_id)).toBe('succeeded')

  await signIn(page, 'reviewer')
  await page.getByRole('link', { name: 'Duyệt nguồn' }).click()
  const row = page.getByRole('row').filter({ hasText: title }).filter({ hasText: 'Chưa có OCR' })
  await row.getByRole('link', { name: 'Duyệt trang 3' }).click()

  const image = page.getByRole('img', { name: 'Ảnh trang 3' })
  await expect(image).toBeVisible()
  await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0)
  await expect(page.getByText('Trang không có chữ')).toBeVisible()
  await page.getByRole('button', { name: 'Loại trừ trang' }).click()
  await page.getByRole('dialog').getByLabel('Lý do').fill('trang ảnh minh họa, không có chữ')
  await page.getByRole('dialog').getByRole('button', { name: 'Xác nhận' }).click()
  await expect(page.getByText('Đã ghi quyết định.')).toBeVisible()
  const jobLink = page.getByRole('link', { name: /^job / })
  const rebuild = (await jobLink.getAttribute('href'))!.split('/').pop()!
  expect(await waitForJob(api, rebuild)).toBe('succeeded')

  await page.goto(`/versions/${upload.version_id}`)
  await expect(page.getByText('2 đạt · 0 cần duyệt · 1 loại trừ')).toBeVisible()
  await page.getByRole('button', { name: 'Publish…' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('không có trong tra cứu: 3')
  const publish = dialog.getByRole('button', { name: 'Publish' })
  await expect(publish).toBeDisabled()
  await dialog.getByLabel(/chấp nhận publish thiếu các trang 3/).check()
  await publish.click()
  await expect(page.getByText(/Đã publish/).first()).toBeVisible()
})

test('a correction that loses a race keeps the reviewer’s edits and saves on the new revision', async ({ page, baseURL }) => {
  const api = await apiAs('reviewer', baseURL!)
  const other = await apiAs('admin', baseURL!)
  const upload = await uploadViaApi(api, stack().fixtures.clean_b, `Sách sửa lỗi ${tag()}`)
  expect(await waitForJob(api, upload.job_id)).toBe('succeeded')
  const pages = (await api.get(`/api/v1/book-versions/${upload.version_id}/pages`)).data
  const first = pages.find((p: { physical_page_number: number }) => p.physical_page_number === 1)
  const revision = (await other.get(`/api/v1/page-revisions/${first.revision_id}`)).data
  const ordinalOf = (text: string) =>
    revision.blocks.find((b: { text: string }) => b.text.includes(text)).ordinal as number
  const mine = ordinalOf('Sách mẫu B')
  const theirsAt = ordinalOf('Giáp Tý')
  expect(mine).not.toBe(theirsAt)

  await signIn(page, 'reviewer')
  await page.goto(`/pages/${first.revision_id}`)
  const block = page.getByLabel(`Nội dung khối ${mine}`)
  await block.fill('Sách mẫu B trang 1: thực thần sinh tài, thương quan kiến quan (đã đối chiếu).')
  await page.getByLabel('Lý do sửa').fill('đối chiếu với ảnh gốc')

  // Meanwhile another reviewer corrects another block of the page and its rebuild finishes.
  const theirs = await other.post(`/api/v1/pages/${revision.page_id}/corrections`, {
    base_revision_id: revision.id, reason: 'sửa can chi',
    changes: [{ ordinal: theirsAt, text: 'Giáp Tý, Bính Dần, Mậu Thìn là ví dụ mẫu B 1 (đã sửa).' }],
  }, { 'If-Match': `"${revision.id}"`, 'Idempotency-Key': `e2e-${tag()}` })
  expect(await waitForJob(other, theirs.data.job_id)).toBe('succeeded')

  await page.getByRole('button', { name: 'Lưu bản sửa' }).click()
  const next = revision.revision_no + 1
  await expect(page.getByText(`Trang vừa được lưu bản sửa khác (bản ${next})`, { exact: false })).toBeVisible()
  await expect(block).toHaveValue(/đã đối chiếu/)                                  // my edit survived
  await expect(page.getByLabel(`Nội dung khối ${theirsAt}`)).toHaveValue(/đã sửa/)  // theirs is the base now
  await page.getByRole('button', { name: 'Lưu bản sửa' }).click()
  await expect(page.getByText(`Đã lưu bản ${next + 1}.`, { exact: false })).toBeVisible()
  await expect(page.getByLabel(`Nội dung khối ${mine}`)).toHaveValue(/đã đối chiếu/)
  await expect(page.getByLabel(`Nội dung khối ${theirsAt}`)).toHaveValue(/đã sửa/)
})

test('book details keep the draft when someone else saved first', async ({ page, baseURL }) => {
  const api = await apiAs('reviewer', baseURL!)
  const t = tag()
  const book = (await api.post('/api/v1/books', { title: `Trích Thiên Tủy ${t}`, language: 'vi', authors: [] })).data
  await signIn(page, 'reviewer')
  await page.goto(`/books/${book.id}`)
  await page.getByRole('button', { name: 'Sửa thông tin' }).click()
  await page.getByLabel('Mô tả').fill('Bản của tôi')
  await api.context.patch(`/api/v1/books/${book.id}`, {
    data: { title: `Trích Thiên Tủy (bản khác) ${t}` },
    headers: { 'X-CSRF-Token': api.csrf, 'If-Match': `"${book.revision}"` },
  })
  await page.getByRole('button', { name: 'Lưu' }).click()
  await expect(page.getByText(/Người khác vừa lưu bản 2/)).toBeVisible()
  await expect(page.getByLabel('Mô tả')).toHaveValue('Bản của tôi')
  await page.getByRole('button', { name: 'Lưu' }).click()
  await expect(page.getByText('Đã lưu thông tin sách.')).toBeVisible()
  await expect(page.getByText('Bản của tôi')).toBeVisible()
})

test('a failed job shows its error and can be retried once', async ({ page, baseURL }) => {
  const api = await apiAs('reviewer', baseURL!)
  const batch = (await api.post('/api/v1/ingestion-batches', {
    name: 'e2e hỏng', pipeline_profile_id: stack().pipeline_profile_id, auto_publish: false })).data
  const { readFileSync } = await import('node:fs')
  const upload = await api.context.post('/api/v1/uploads', {
    headers: { 'X-CSRF-Token': api.csrf, 'Idempotency-Key': `e2e-${tag()}` },
    multipart: { file: { name: 'hong.pdf', mimeType: 'application/pdf', buffer: readFileSync(stack().fixtures.corrupt) },
                 batch_id: batch.id, rights_status: 'unknown', title: `Sách hỏng ${tag()}` },
  })
  const job = (await upload.json()).data.job_id as string
  expect(await waitForJob(api, job)).toBe('failed')

  await signIn(page, 'reviewer')
  await page.goto(`/jobs/${job}`)
  await expect(page.getByText('PDF_CORRUPT').first()).toBeVisible()
  await expect(page.getByText(/lỗi vĩnh viễn/)).toBeVisible()
  await page.getByRole('button', { name: 'Thử lại' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Tạo job thử lại' }).click()
  await expect(page).not.toHaveURL(new RegExp(job))
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Thất bại', { timeout: 60_000 })
  await page.goto(`/jobs/${job}`)
  await expect(page.getByText(/Đã thử lại bằng/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Thử lại' })).toHaveCount(0)
})

test('readers cannot reach upload, jobs or review', async ({ page, baseURL }) => {
  await signIn(page, 'reader')
  const nav = page.getByRole('navigation', { name: 'Điều hướng chính' })
  for (const name of ['Tải sách lên', 'Jobs xử lý', 'Duyệt nguồn']) {
    await expect(nav.getByRole('link', { name })).toHaveCount(0)
  }
  for (const path of ['/books/upload', '/jobs', '/review']) {
    await page.goto(path)
    await expect(page.getByRole('heading', { name: 'Không đủ quyền' })).toBeVisible()
  }
  const reader = await apiAs('reader', baseURL!)
  const refused = await reader.context.post('/api/v1/ingestion-batches', {
    data: { name: 'x' }, headers: { 'X-CSRF-Token': reader.csrf } })
  expect(refused.status()).toBe(403)
})
