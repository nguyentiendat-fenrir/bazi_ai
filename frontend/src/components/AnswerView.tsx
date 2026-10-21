'use client'
// A validated answer (docs/09 · Answer contract): summary, claims with their support and
// sources, disagreements, limitations, follow-up questions. Book text renders as text only.
import { Badge } from '@/components/ui'
import { withBase } from '@/lib/base'
import type { Tone } from '@/lib/format'

export interface AnswerCitation {
  handle: string
  book_title: string
  edition_label?: string
  section_title?: string | null
  speaker_layer?: string
  pages: number[]
  printed_pages?: string[]
  quote: string
  viewer?: { page_revision_id: string, start_offset?: number, end_offset?: number }[]
}

export interface AnswerClaim {
  id: string
  text: string
  kind: string
  school_key?: string | null
  fact_paths?: string[]
  citations?: AnswerCitation[]
  support_status: string
  inference_level: string
  unresolved_exceptions?: string[]
}

export interface AnswerData {
  status: string
  mode: string
  summary: string
  claims: AnswerClaim[]
  disagreements?: { topic: string, positions: { school_key: string | null, claim_ids: string[] }[] }[]
  limitations?: string[]
  follow_up_questions?: string[]
  rejected_claims?: number
}

const STATUS: Record<string, [string, Tone]> = {
  supported: ['Có nguồn', 'ok'],
  partial: ['Một phần có nguồn', 'warning'],
  insufficient_evidence: ['Thiếu nguồn', 'danger'],
  empty_corpus: ['Kho tra cứu trống', 'neutral'],
  provider_not_configured: ['Chưa có mô hình AI', 'neutral'],
}
const KINDS: Record<string, string> = {
  calculation: 'Tính toán', rule_result: 'Quy tắc', source_statement: 'Nguồn sách',
  interpretation: 'Diễn giải', limitation: 'Giới hạn',
}
const SUPPORT: Record<string, [string, Tone]> = {
  validated: ['đã kiểm', 'ok'], needs_review: ['cần xem lại', 'warning'],
  insufficient: ['thiếu nguồn', 'danger'],
}
const SPEAKERS: Record<string, string> = {
  original_author: 'nguyên tác', commentator: 'bình chú', translator: 'người dịch',
  editor: 'biên tập', unknown: 'chưa rõ lớp',
}

export function AnswerView({ answer, onFollowUp }: { answer: AnswerData, onFollowUp?: (q: string) => void }) {
  const [label, tone] = STATUS[answer.status] ?? [answer.status, 'neutral']
  return (
    <div className="answer">
      <p><Badge tone={tone}>{label}</Badge></p>
      <p className="answer-summary">{answer.summary}</p>
      {answer.claims.length > 0 && (
        <ol className="claims">
          {answer.claims.map((claim) => {
            const [support, supportTone] = SUPPORT[claim.support_status] ?? [claim.support_status, 'neutral']
            return (
              <li key={claim.id} className="claim">
                <div className="claim-head">
                  <Badge>{KINDS[claim.kind] ?? claim.kind}</Badge>
                  <Badge tone={supportTone}>{support}</Badge>
                  {claim.school_key && <span className="muted small">{claim.school_key}</span>}
                  {claim.inference_level !== 'direct' && <span className="muted small">suy luận {claim.inference_level === 'conditional' ? 'có điều kiện' : 'diễn giải'}</span>}
                </div>
                <p>{claim.text}</p>
                {claim.citations && claim.citations.length > 0 && (
                  <ul className="citations">
                    {claim.citations.map((c) => (
                      <li key={c.handle}>
                        <span className="muted small">«{c.book_title}»{c.section_title ? ` · ${c.section_title}` : ''} · trang {c.pages.join(', ')}
                          {c.speaker_layer ? ` · ${SPEAKERS[c.speaker_layer] ?? c.speaker_layer}` : ''}</span>
                        <blockquote>{c.quote}</blockquote>
                        {c.viewer?.[0] && <a className="small" href={withBase(`/pages/${c.viewer[0].page_revision_id}?from=${c.viewer[0].start_offset ?? ''}&to=${c.viewer[0].end_offset ?? ''}`)}>Mở trang nguồn</a>}
                      </li>
                    ))}
                  </ul>
                )}
                {claim.fact_paths && claim.fact_paths.length > 0 && (
                  <p className="muted small">Dữ kiện: <code>{claim.fact_paths.join(', ')}</code></p>
                )}
              </li>
            )
          })}
        </ol>
      )}
      {answer.disagreements && answer.disagreements.length > 0 && (
        <div className="notice notice-info">
          <strong>Quan điểm khác nhau</strong>
          <ul>{answer.disagreements.map((d) => (
            <li key={d.topic}>{d.topic}: {d.positions.map((p) => `${p.school_key ?? 'nguồn khác'} (${p.claim_ids.join(', ')})`).join(' / ')}</li>
          ))}</ul>
        </div>
      )}
      {answer.limitations && answer.limitations.length > 0 && (
        <div className="notice notice-warning">
          <strong>Giới hạn</strong>
          <ul>{answer.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
        </div>
      )}
      {answer.follow_up_questions && answer.follow_up_questions.length > 0 && onFollowUp && (
        <div className="actions">
          {answer.follow_up_questions.map((q) => (
            <button key={q} type="button" className="button button-secondary button-small" onClick={() => onFollowUp(q)}>{q}</button>
          ))}
        </div>
      )}
    </div>
  )
}
