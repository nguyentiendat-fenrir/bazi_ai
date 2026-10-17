// T044: making, reading and removing charts; engine errors on the right field.
import { expect, test, type Page } from '@playwright/test'

import { expectNoHorizontalOverflow, signIn, tag } from './support'

async function fillBirth(page: Page, date: string, time: string, zone = 'Asia/Ho_Chi_Minh') {
  await page.goto('/charts/new')
  await page.getByLabel('Ngày sinh (dương lịch)').fill(date)
  await page.getByLabel('Giờ sinh', { exact: true }).fill(time)
  await page.getByLabel('Múi giờ nơi sinh').selectOption(zone)
}

test('a reader makes a chart and reads its pillars, luck and computation', async ({ page }) => {
  await signIn(page, 'reader')
  await page.getByRole('link', { name: 'Lá số' }).click()
  await expect(page.getByRole('heading', { name: 'Chưa có lá số nào' })).toBeVisible()
  await fillBirth(page, '1990-08-17', '06:45')
  await page.getByLabel('Nam', { exact: true }).check()
  await page.getByRole('button', { name: 'Lập lá số' }).click()
  await expect(page).toHaveURL(/\/charts\/[0-9a-f-]{36}$/)
  const pillars = page.getByRole('table', { name: 'Tứ trụ' })
  await expect(pillars.getByRole('row', { name: /Thiên can/ })).toContainText('Canh')
  await expect(pillars.getByRole('row', { name: /Thiên can/ })).toContainText('Mộc')     // element label
  await expect(pillars.getByRole('row', { name: /Thập thần/ })).toContainText('Nhật chủ')
  await expect(pillars.getByRole('row', { name: /Địa chi/ })).toContainText('Ngọ')
  await expect(page.getByRole('table', { name: 'Đại vận' }).getByRole('row')).toHaveCount(11)
  await expect(page.getByText('Thuận', { exact: true })).toBeVisible()
  await expect(page.getByText(/Lập Thu ·/)).toBeVisible()
  await expectNoHorizontalOverflow(page)
})

test('an unknown hour leaves the hour pillar empty and says why', async ({ page }) => {
  await signIn(page, 'reader')
  await page.goto('/charts/new')
  await page.getByLabel('Ngày sinh (dương lịch)').fill('1990-08-17')
  await page.getByLabel('Độ chính xác giờ sinh').selectOption('unknown')
  await expect(page.getByText('Không giả định giờ 12:00')).toBeVisible()
  await page.getByRole('button', { name: 'Lập lá số' }).click()
  await expect(page.getByText('Không biết giờ sinh: không lập trụ giờ')).toBeVisible()
  await expect(page.getByRole('table', { name: 'Tứ trụ' })).toContainText('Chưa biết')
})

test('clock changes are refused or must be disambiguated on the form', async ({ page }) => {
  await signIn(page, 'reader')
  await fillBirth(page, '2021-03-14', '02:30', 'America/New_York')
  await page.getByRole('button', { name: 'Lập lá số' }).click()
  await expect(page.getByText(/Giờ này không tồn tại ở múi giờ đã chọn/)).toBeVisible()
  await fillBirth(page, '2021-11-07', '01:30', 'America/New_York')
  await page.getByRole('button', { name: 'Lập lá số' }).click()
  await expect(page.getByText(/xảy ra hai lần/).first()).toBeVisible()
  const submit = page.getByRole('button', { name: 'Lập lá số' })
  await expect(submit).toBeDisabled()
  await page.getByLabel('Lần thứ hai (sau khi lùi đồng hồ)').check()
  await submit.click()
  await expect(page.getByText('2021-11-07T06:30:00Z')).toBeVisible()
})

test('a lunar date, a saved profile, search and deletion', async ({ page }) => {
  const label = `Con gái ${tag()}`
  await signIn(page, 'reader')
  await page.goto('/charts/new')
  await page.getByLabel('Âm lịch Việt Nam').check()
  await page.getByLabel('Năm âm lịch').fill('1985')
  await page.getByLabel('Giờ sinh', { exact: true }).fill('08:00')
  await page.getByLabel('Lưu thành hồ sơ').check()
  await page.getByLabel('Tên hồ sơ').fill(label)
  await page.getByRole('button', { name: 'Lập lá số' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(label)
  await expect(page.getByText('1985-01-21 08:00:00').first()).toBeVisible()   // Tết 1985 in Vietnam
  await page.getByRole('link', { name: 'Lá số', exact: true }).first().click()
  await page.getByLabel('Tìm theo tên hồ sơ').fill(label)
  await expect(page.getByRole('row').filter({ hasText: label })).toContainText('Giáp Tý')
  await page.getByRole('link', { name: label }).click()
  await page.getByRole('button', { name: 'Xóa…' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Xóa lá số' }).click()
  await expect(page).toHaveURL(/\/charts$/)
  await page.getByLabel('Tìm theo tên hồ sơ').fill(label)
  await expect(page.getByRole('heading', { name: 'Không có lá số khớp' })).toBeVisible()
})
