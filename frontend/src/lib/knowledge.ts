// Labels for the reviewed knowledge model (docs/06): lifecycle states, origins, aliases.
import type { Tone } from '@/lib/format'

type Labels = Record<string, [string, Tone]>

export const KNOWLEDGE_STATES: Labels = {
  draft: ['Bản nháp', 'neutral'],
  in_review: ['Chờ duyệt', 'warning'],
  approved: ['Đã duyệt', 'ok'],
  rejected: ['Bị từ chối', 'danger'],
  revoked: ['Đã thu hồi', 'danger'],
}

export const STATE_OPTIONS = Object.entries(KNOWLEDGE_STATES).map(([value, [text]]) => ({ value, text }))

export const ASSERTION_ORIGINS: Record<string, string> = {
  source_explicit: 'Sách nói rõ', editor_interpretation: 'Biên tập diễn giải', ai_inferred: 'AI suy ra',
}

export const CASE_ORIGINS: Record<string, string> = {
  book_case: 'Ca trong sách', user_case: 'Ca người dùng', synthetic_test: 'Ca kiểm thử',
}

export const ALIAS_KINDS: Record<string, string> = {
  canonical: 'Tên chuẩn', same_concept: 'Cùng khái niệm', translation_variant: 'Biến thể dịch',
  related: 'Liên quan', contrasts_with: 'Đối lập',
}

export const RULESET_STATES: Labels = {
  building: ['Đang dựng', 'info'], published: ['Đang dùng', 'ok'], retired: ['Ngưng', 'neutral'],
}

export const RULE_STATUS: Labels = {
  true: ['Đúng', 'ok'], false: ['Sai', 'neutral'], unknown: ['Thiếu dữ kiện', 'warning'],
  conflict: ['Xung đột', 'danger'], skipped: ['Bỏ qua', 'neutral'],
}

export const IMPACT_KINDS: Record<string, string> = {
  concepts: 'khái niệm', terms: 'thuật ngữ', assertions: 'luận điểm', rules: 'quy tắc',
  rulesets: 'bộ quy tắc', cases: 'ca mẫu', analyses: 'phân tích', answers: 'câu trả lời',
  claims: 'nhận định', chunks: 'đoạn', corpus_releases: 'bản kho',
}
