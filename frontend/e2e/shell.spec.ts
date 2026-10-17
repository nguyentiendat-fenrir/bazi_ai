// T043.1: sign-in, guarded shell, library navigation and the required screen states.
import { expect, test } from '@playwright/test'

import { apiAs, expectNoHorizontalOverflow, signIn, stack, tag } from './support'

test('every screen needs a session and sign-in returns to the requested page', async ({ page }) => {
  await page.goto('/books')
  await expect(page).toHaveURL(/\/login\?next=%2Fbooks$/)
  await page.getByLabel('Email').fill(stack().users.reviewer.email)
  await page.getByLabel('Mật khẩu').fill('not the password')
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
  await expect(page.locator('form').getByRole('alert')).toContainText('Email hoặc mật khẩu không đúng')
  await page.getByLabel('Mật khẩu').fill(stack().password)
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
  await expect(page).toHaveURL(/\/books$/)
  await expect(page.getByRole('heading', { name: 'Thư viện sách', level: 1 })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Thư viện sách' })).toHaveAttribute('aria-current', 'page')
})

test('a reader sees an empty library and no operations panels', async ({ page }) => {
  await signIn(page, 'reader')
  await expect(page.getByRole('heading', { name: 'Tổng quan', level: 1 })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Chưa có sách nào' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Jobs xử lý sách' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Kho tra cứu đang dùng' })).toHaveCount(0)
})

test('a reviewer sees real operations numbers on the dashboard', async ({ page }) => {
  await signIn(page, 'reviewer')
  await expect(page.getByRole('heading', { name: 'Jobs xử lý sách' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Mục cần duyệt' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Kho tra cứu đang dùng' })).toBeVisible()
  await expect(page.getByText(/đang chạy/)).toBeVisible()
})

test('books are found without diacritics and open on their own page', async ({ page, baseURL }) => {
  const t = tag()
  const api = await apiAs('reviewer', baseURL!)
  await api.post('/api/v1/books', {
    title: `Tử Bình Chân Thuyên ${t}`, language: 'vi',
    authors: [{ name: 'Thẩm Hiếu Chiêm', role: 'author' }, { name: 'Từ Lạc Ngô', role: 'commentator' }],
  })
  await signIn(page, 'reviewer')
  await page.getByRole('link', { name: 'Thư viện sách' }).click()
  await page.getByLabel('Tìm sách').fill(`tu binh chan thuyen ${t}`)
  const row = page.getByRole('row').filter({ hasText: t })
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('Thẩm Hiếu Chiêm, Từ Lạc Ngô (bình chú)')
  await expect(row).toContainText('Chưa publish')
  await row.getByRole('link').click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(`Tử Bình Chân Thuyên ${t}`)
  await expect(page.getByRole('heading', { name: 'Chưa có phiên bản' })).toBeVisible()

  await page.goto('/books')
  await page.getByLabel('Tìm sách').fill(`khong co sach nao ${t}`)
  await expect(page.getByRole('heading', { name: 'Không có sách khớp' })).toBeVisible()
})

test('a private book is reported as not found to a reader', async ({ page, baseURL }) => {
  const api = await apiAs('reviewer', baseURL!)
  const book = (await api.post('/api/v1/books', { title: `Riêng tư ${tag()}`, language: 'vi', authors: [] })).data
  await signIn(page, 'reader')
  await page.goto(`/books/${book.id}`)
  await expect(page.getByRole('heading', { name: 'Không tìm thấy' })).toBeVisible()
})

test('signing out ends the session for every screen', async ({ page }) => {
  await signIn(page, 'reviewer')
  await page.getByRole('button', { name: 'Đăng xuất' }).click()
  await expect(page).toHaveURL(/\/login/)
  await page.goto('/')
  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByRole('heading', { name: 'Đăng nhập' })).toBeVisible()
})

test('a session that expires sends the user back to sign in with a reason', async ({ page, context }) => {
  await signIn(page, 'reviewer')
  await context.clearCookies()
  await page.getByRole('link', { name: 'Thư viện sách' }).click()
  await expect(page).toHaveURL(/\/login\?next=%2Fbooks/)
  await expect(page.getByText('Phiên trước đã kết thúc')).toBeVisible()
})

test('an unreachable API is shown as an error with a retry, not a blank screen', async ({ page }) => {
  await signIn(page, 'admin')
  const books = (url: URL) => url.pathname === '/api/v1/books'
  await page.route(books, (route) => route.abort())
  await page.getByRole('link', { name: 'Thư viện sách' }).click()
  // Scoped to main: Next's route announcer is also role=alert.
  const alerts = page.getByRole('main').getByRole('alert')
  await expect(alerts).toContainText('Không kết nối được máy chủ API')
  await page.unroute(books)
  await page.getByRole('button', { name: 'Thử lại' }).click()
  await expect(page.getByRole('heading', { name: 'Thư viện sách', level: 1 })).toBeVisible()
  await expect(alerts).toHaveCount(0)
})

test('the top bar reports API health to admins', async ({ page }) => {
  await signIn(page, 'admin')
  await expect(page.getByRole('status').filter({ hasText: /API (hoạt động|suy giảm)/ })).toBeVisible()
  await page.route((url) => url.pathname === '/api/v1/health/ready', (route) => route.abort())
  await page.reload()
  await expect(page.getByText('Mất kết nối API')).toBeVisible({ timeout: 20_000 })
})

for (const [width, height] of [[1280, 720], [1920, 1080]]) {
  test(`no horizontal overflow at ${width}x${height}`, async ({ page, baseURL }) => {
    const api = await apiAs('reviewer', baseURL!)
    const long = 'Một nhan đề rất dài để kiểm tra bố cục '.repeat(6) + tag()
    const book = (await api.post('/api/v1/books', { title: long, language: 'vi', authors: [] })).data
    await page.setViewportSize({ width, height })
    await signIn(page, 'reviewer')
    await expectNoHorizontalOverflow(page)
    await page.goto('/books')
    await expect(page.getByRole('table')).toBeVisible()
    await expectNoHorizontalOverflow(page)
    await page.goto(`/books/${book.id}`)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expectNoHorizontalOverflow(page)
  })
}
