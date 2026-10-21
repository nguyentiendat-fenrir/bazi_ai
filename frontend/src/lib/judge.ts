// Judging of RAG answers: the score rubric and helpers for the /judge page.
//
// The rubric is the one place to change what judges score; the server accepts any
// field name with a 1–5 integer, true/false or null, so editing it needs no API change.
import type { Schemas } from '@/api/client'

export type AskOut = Schemas['AskOut']
export type ParentOut = Schemas['ParentOut']
export type ChildOut = Schemas['ChildOut']

export interface ScaleCriterion {
  key: string
  label: string
  help: string
  kind: 'scale'
  low: string
  high: string
}

export interface YesNoCriterion {
  key: string
  label: string
  help: string
  kind: 'yesno'
}

export type Criterion = ScaleCriterion | YesNoCriterion

export const RUBRIC: Criterion[] = [
  { key: 'correct', kind: 'scale', label: 'Đúng theo sách',
    help: 'Nội dung trả lời có đúng với những gì sách nói không?', low: 'Sai', high: 'Hoàn toàn đúng' },
  { key: 'grounded', kind: 'scale', label: 'Bám nguồn',
    help: 'Mọi ý đều có trong đoạn nguồn được trích [P#], không thêm kiến thức ngoài?',
    low: 'Bịa / ngoài nguồn', high: 'Hoàn toàn từ nguồn' },
  { key: 'complete', kind: 'scale', label: 'Đầy đủ',
    help: 'Trả lời hết các ý câu hỏi đặt ra (trong phạm vi nguồn có)?', low: 'Thiếu nhiều', high: 'Đủ ý' },
  { key: 'retrieval', kind: 'scale', label: 'Đoạn truy xuất phù hợp',
    help: 'Các đoạn sách tìm được có đúng chỗ để trả lời không (kể cả khi câu trả lời kém)?',
    low: 'Không liên quan', high: 'Đúng chỗ' },
  { key: 'should_refuse', kind: 'yesno', label: 'Lẽ ra phải từ chối / nói không đủ nguồn?',
    help: 'Ví dụ câu hỏi đòi khẳng định chắc chắn chuyện sống chết, hoặc sách không có thông tin.' },
]

export const RELEVANCE = [
  { value: 'relevant', label: 'Liên quan' },
  { value: 'partial', label: 'Một phần' },
  { value: 'irrelevant', label: 'Không liên quan' },
] as const

export type Relevance = (typeof RELEVANCE)[number]['value']

export interface ChunkLabel {
  relevance: Relevance | null
  suggest_rule: boolean
}

export const STATUS_LABELS: Record<string, string> = {
  ok: 'Có câu trả lời',
  insufficient_evidence: 'Không đủ nguồn',
  empty_corpus: 'Kho trống',
  no_match: 'Không tìm thấy',
  provider_not_configured: 'Chưa có mô hình',
  provider_error: 'Lỗi mô hình',
  request_failed: 'Lỗi gọi API',
}

export const SPEAKER_LABELS: Record<string, string> = {
  original_author: 'Nguyên văn',
  commentator: 'Bình chú',
  translator: 'Dịch giả',
  editor: 'Biên tập',
  unknown: '—',
}

export function pages(start?: number | null, end?: number | null): string {
  if (!start) return ''
  return end && end !== start ? `tr. ${start}–${end}` : `tr. ${start}`
}

export function score(value?: number | null, digits = 3): string {
  return typeof value === 'number' ? value.toFixed(digits) : '—'
}

/** Answer text split into plain runs and [P#] citation markers. */
export function answerParts(text: string): { text: string, handle?: string }[] {
  const parts: { text: string, handle?: string }[] = []
  const pattern = /\[(P\d+)\]/g
  let last = 0
  for (const match of text.matchAll(pattern)) {
    if (match.index! > last) parts.push({ text: text.slice(last, match.index) })
    parts.push({ text: match[0], handle: match[1] })
    last = match.index! + match[0].length
  }
  if (last < text.length) parts.push({ text: text.slice(last) })
  return parts
}

const NAME_KEY = 'bazi.judge.name'

export const judgeName = {
  get(): string {
    try { return window.localStorage.getItem(NAME_KEY) ?? '' } catch { return '' }
  },
  set(name: string): void {
    try { window.localStorage.setItem(NAME_KEY, name) } catch { /* private mode: not needed */ }
  },
}
