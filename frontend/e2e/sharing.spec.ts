// Sharing a book with a reader, and assigning a school to a book version.
import { expect, test, type Page } from '@playwright/test'

import { apiAs, signIn, stack, tag, uploadViaApi, waitForJob } from './support'

const PASSWORD = 'mot mat khau cho nguoi doc rieng'

async function signInAs(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Mật khẩu').fill(PASSWORD)
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
  await expect(page.getByRole('button', { name: 'Đăng xuất' })).toBeVisible()
}

test('an admin shares a book with one reader; a reviewer assigns and approves its school', async ({ page, baseURL }) => {
  const reviewerApi = await apiAs('reviewer', baseURL!)
  const admin = await apiAs('admin', baseURL!)
  const title = `Sách chia sẻ ${tag()}`
  const upload = await uploadViaApi(reviewerApi, stack().fixtures.shared, title)
  expect(await waitForJob(reviewerApi, upload.job_id)).toBe('succeeded')
  const email = `doc-${tag()}@example.test`
  await admin.post('/api/v1/users', { email, password: PASSWORD, role: 'reader' })

  await signInAs(page, email)
  await page.goto('/books')
  await expect(page.getByRole('link', { name: title })).toHaveCount(0)        // not shared yet
  await page.getByRole('button', { name: 'Đăng xuất' }).click()

  await signIn(page, 'admin', `/books/${upload.book_id}`)
  const access = page.getByRole('region', { name: 'Ai được xem' })
  await access.getByLabel('Chia sẻ riêng với').selectOption({ label: email })
  await access.getByRole('button', { name: 'Chia sẻ', exact: true }).click()
  await expect(access.getByText('Đã lưu quyền xem')).toBeVisible()
  await expect(access.getByRole('list', { name: 'Người được chia sẻ riêng' })).toContainText(email)
  await page.getByRole('button', { name: 'Đăng xuất' }).click()

  await signInAs(page, email)
  await page.goto('/books')
  await expect(page.getByRole('link', { name: title })).toBeVisible()
  await page.getByRole('button', { name: 'Đăng xuất' }).click()

  await signIn(page, 'reviewer', `/versions/${upload.version_id}`)
  const schools = page.getByRole('region', { name: 'Trường phái' })
  await expect(schools.getByText('Chưa gán trường phái')).toBeVisible()
  await schools.getByLabel('Trường phái').selectOption({ index: 1 })
  await schools.getByLabel('Từ trang').fill('1')
  await schools.getByLabel('Đến trang').fill('2')
  await schools.getByLabel('Căn cứ').fill('lời tựa ghi rõ trường phái')
  await schools.getByRole('button', { name: 'Đề xuất' }).click()
  await expect(schools.getByText('trang 1–2')).toBeVisible()
  await schools.getByRole('button', { name: /^Duyệt trường phái/ }).click()
  await page.getByRole('dialog').getByLabel('Lý do').fill('đã đọc lời tựa')
  await page.getByRole('dialog').getByRole('button', { name: 'Xác nhận' }).click()
  await expect(schools.getByText('Đã duyệt')).toBeVisible()
  await schools.getByRole('link', { name: 'Theo dõi job' }).click()
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]{36}$/)
})
