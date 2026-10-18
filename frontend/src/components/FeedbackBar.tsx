'use client'
// Rating one of your answers or rule analyses (private to you; admins see counts only).
// "Chưa đúng" asks what was wrong so the counts point at a cause.
import { useState } from 'react'

import { api, call, type Schemas } from '@/api/client'
import { FormError } from '@/components/ui'

type Feedback = Schemas['FeedbackDTO']
type Category = Schemas['FeedbackInput']['categories'][number]

const CATEGORIES: [Category, string][] = [
  ['wrong_source', 'Trích sai nguồn'], ['missing_source', 'Thiếu nguồn'], ['wrong_school', 'Lẫn trường phái'],
  ['calculation', 'Sai lá số / tính toán'], ['too_certain', 'Khẳng định quá mức'], ['unclear', 'Khó hiểu'],
  ['other', 'Khác'],
]

export function FeedbackBar({ target, initial }: {
  target: { kind: 'message' | 'analysis', id: string }, initial?: Feedback | null,
}) {
  const [saved, setSaved] = useState<Feedback | null>(initial ?? null)
  const [asking, setAsking] = useState(false)
  const [categories, setCategories] = useState<Category[]>(initial?.categories ?? [])
  const [comment, setComment] = useState(initial?.comment ?? '')
  const [error, setError] = useState<unknown>(null)

  const send = async (rating: -1 | 0 | 1) => {
    setError(null)
    const body = { rating, categories: rating === -1 ? categories : [], comment: rating === -1 ? comment.trim() || null : null }
    try {
      const done = target.kind === 'message'
        ? await call(api.PUT('/api/v1/messages/{message_id}/feedback', { params: { path: { message_id: target.id } }, body }))
        : await call(api.PUT('/api/v1/analyses/{analysis_id}/feedback', { params: { path: { analysis_id: target.id } }, body }))
      setSaved(done.data)
      setAsking(false)
    } catch (caught) {
      setError(caught)
    }
  }

  return (
    <div className="feedback" role="group" aria-label="Đánh giá câu trả lời">
      {saved && saved.rating !== 0 && !asking ? (
        <p className="muted small" role="status">
          {saved.rating === 1 ? 'Bạn thấy hữu ích.' : 'Bạn đã báo chưa đúng.'} Cảm ơn!{' '}
          <button type="button" className="button button-ghost button-small" onClick={() => void send(0)}>Bỏ đánh giá</button>
        </p>
      ) : (
        <div className="actions">
          <button type="button" className="button button-ghost button-small" onClick={() => void send(1)}>Hữu ích</button>
          <button type="button" className="button button-ghost button-small" aria-expanded={asking}
                  onClick={() => setAsking(!asking)}>Chưa đúng…</button>
        </div>
      )}
      {asking && (
        <div className="feedback-form">
          <fieldset className="choices">
            <legend className="label">Chưa đúng ở đâu?</legend>
            {CATEGORIES.map(([value, label]) => (
              <label key={value} className="checkbox">
                <input type="checkbox" checked={categories.includes(value)}
                       onChange={(e) => setCategories(e.target.checked ? [...categories, value] : categories.filter((c) => c !== value))} />
                <span>{label}</span>
              </label>
            ))}
          </fieldset>
          <div className="field">
            <label htmlFor={`fb-${target.id}`}>Ghi chú (chỉ bạn xem được)</label>
            <textarea id={`fb-${target.id}`} rows={2} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
          <div className="actions">
            <button type="button" className="button button-ghost button-small" onClick={() => setAsking(false)}>Hủy</button>
            <button type="button" className="button button-small" onClick={() => void send(-1)}>Gửi đánh giá</button>
          </div>
        </div>
      )}
      <FormError error={error} />
    </div>
  )
}
