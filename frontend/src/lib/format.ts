// Display helpers and Vietnamese labels. States always render as text, never colour alone.

export type Tone = 'neutral' | 'info' | 'ok' | 'warning' | 'danger'

const number = new Intl.NumberFormat('vi-VN')
const decimal = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 })
const dateTime = new Intl.DateTimeFormat('vi-VN', {
  day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  hour12: false,
})

export function formatNumber(value: number): string {
  return number.format(value)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${number.format(bytes)} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${decimal.format(value)} ${units[unit]}`
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '—' : dateTime.format(date)
}

export function shortId(value: string | null | undefined, length = 8): string {
  return value ? value.replaceAll('-', '').slice(0, length) : '—'
}

export function percent(part: number, total: number): string {
  if (total <= 0) return '—'
  return `${decimal.format((part / total) * 100)}%`
}

/** Only same-origin paths survive a ?next= redirect (no //host or scheme). */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.includes('\\')) return '/'
  return next
}

type Labels = Record<string, [string, Tone]>

export const JOB_STATES: Labels = {
  queued: ['Đang chờ', 'neutral'],
  running: ['Đang chạy', 'info'],
  retry_wait: ['Chờ thử lại', 'warning'],
  waiting_review: ['Chờ duyệt', 'warning'],
  cancel_requested: ['Đang hủy', 'warning'],
  succeeded: ['Hoàn tất', 'ok'],
  partial: ['Xong một phần', 'warning'],
  failed: ['Thất bại', 'danger'],
  cancelled: ['Đã hủy', 'neutral'],
}

export const ACTIVE_JOB_STATES = ['queued', 'running', 'retry_wait', 'cancel_requested'] as const

export const VERSION_STATUS: Labels = {
  active: ['Đang dùng', 'ok'],
  withdrawn: ['Đã thu hồi', 'danger'],
}

export const GENERATION_STATES: Labels = {
  building: ['Đang dựng', 'info'],
  ready: ['Sẵn sàng publish', 'warning'],
  published: ['Đã publish', 'ok'],
  superseded: ['Bị thay thế', 'neutral'],
  withdrawn: ['Đã thu hồi', 'danger'],
}

export const PAGE_STATES: Labels = {
  accepted: ['Đạt', 'ok'],
  review_required: ['Cần duyệt', 'warning'],
  excluded: ['Loại trừ', 'neutral'],
}

export const REVIEW_STATES: Labels = {
  open: ['Đang mở', 'warning'],
  in_progress: ['Đang xử lý', 'info'],
  resolved: ['Đã xử lý', 'ok'],
  dismissed: ['Bỏ qua', 'neutral'],
}

export const SEVERITIES: Labels = {
  info: ['Thông tin', 'neutral'],
  low: ['Thấp', 'neutral'],
  medium: ['Trung bình', 'warning'],
  high: ['Cao', 'danger'],
  critical: ['Nghiêm trọng', 'danger'],
}

export const RIGHTS: Record<string, string> = {
  unknown: 'Chưa rõ quyền',
  private_reference: 'Tham khảo riêng',
  licensed: 'Có giấy phép',
  public_domain: 'Phạm vi công cộng',
  restricted: 'Hạn chế',
}

export const ROLES: Record<string, string> = {
  admin: 'Quản trị',
  reviewer: 'Người duyệt',
  reader: 'Người đọc',
}

export const STAGES: Record<string, string> = {
  validate: 'Kiểm tra tệp',
  extract: 'Trích văn bản',
  ocr: 'OCR',
  structure: 'Cấu trúc',
  quality: 'Chất lượng',
  chunk: 'Chia đoạn',
  summarize: 'Tóm tắt mục (Qwen)',
  embed: 'Vector hóa',
  extract_candidates: 'Ứng viên tri thức',
  publish: 'Niêm phong',
}

export const REVIEW_REASONS: Record<string, string> = {
  OCR_LOW_CONFIDENCE: 'OCR độ tin cậy thấp',
  OCR_TIMEOUT: 'OCR quá thời gian',
  OCR_UNAVAILABLE: 'Chưa có OCR',
  OCR_EMPTY: 'OCR không nhận được chữ',
  OCR_GARBLED: 'OCR nhiều ký tự lỗi',
  JUDGE_SUGGESTED_RULE: 'Người chấm đề xuất quy tắc',
  DOCX_RENDER_FAILED: 'Không dựng được bản PDF từ DOCX',
  DOCX_LOCATE_PARTIAL: 'DOCX định vị thiếu',
  SOURCE_CHANGED: 'Nguồn đã sửa',
  CANDIDATE_ASSERTION: 'Ứng viên mệnh đề',
  CANDIDATE_CASE: 'Ứng viên ví dụ lá số',
  HEADING_SPLIT: 'Tiêu đề bị tách',
  PILLAR_ROW_MISMATCH: 'Hàng Can/Chi lệch',
  PRINTED_LABEL_MISMATCH: 'Số trang in không khớp',
  READING_ORDER: 'Thứ tự đọc nghi sai',
  REPLACEMENT_CHARS: 'Ký tự thay thế (mất chữ)',
  SPEAKER_LAYERS_INCOMPLETE: 'Thiếu lớp tác giả/bình chú',
  UNMAPPED_GLYPHS: 'Glyph không ánh xạ được chữ',
}

export function label(labels: Labels, value: string | null | undefined): [string, Tone] {
  if (!value) return ['—', 'neutral']
  return labels[value] ?? [value, 'neutral']
}
