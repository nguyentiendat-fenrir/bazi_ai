'use client'
// Concepts and their terms (docs/11 /knowledge/terms): one record per school's meaning, so the
// same label in two schools shows as two concepts; search matches forms without diacritics.
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { api, call } from '@/api/client'
import { Dialog } from '@/components/Dialog'
import { KnowledgeTabs } from '@/components/KnowledgeTabs'
import { Empty, ErrorState, Forbidden, FormError, Loading, PageHeader, StateBadge } from '@/components/ui'
import { formatDateTime } from '@/lib/format'
import { ALIAS_KINDS, KNOWLEDGE_STATES, STATE_OPTIONS } from '@/lib/knowledge'
import { usePagedList, useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

function NewConcept({ open, onClose }: { open: boolean, onClose(): void }) {
  const router = useRouter()
  const schools = useQuery(open ? 'knowledge:schools' : null, () => call(api.GET('/api/v1/schools')))
  const [form, setForm] = useState({ school_id: '', canonical_key: '', label: '', han: '', description: '' })
  const [error, setError] = useState<unknown>(null)
  const set = (key: keyof typeof form, value: string) => setForm({ ...form, [key]: value })

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      const made = await call(api.POST('/api/v1/concepts', { body: { ...form, han: form.han || null } }))
      router.push(`/knowledge/concepts/${made.data.id}`)
    } catch (caught) {
      setError(caught)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Khái niệm mới">
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="concept-school">Trường phái</label>
          <select id="concept-school" required value={form.school_id} onChange={(e) => set('school_id', e.target.value)}>
            <option value="">Chọn…</option>
            {schools.data?.data.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="concept-label">Tên hiển thị</label>
          <input id="concept-label" required maxLength={200} value={form.label} onChange={(e) => set('label', e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="concept-key">Khóa chuẩn</label>
          <input id="concept-key" required maxLength={100} pattern="[a-z0-9_.]+" value={form.canonical_key}
                 onChange={(e) => set('canonical_key', e.target.value)} aria-describedby="concept-key-hint" />
          <p id="concept-key-hint" className="muted small">Chữ thường không dấu, số, “_” hoặc “.”; ví dụ <code>ten_god.seven_killings</code>.</p>
        </div>
        <div className="field">
          <label htmlFor="concept-han">Chữ Hán (tùy chọn)</label>
          <input id="concept-han" maxLength={50} value={form.han} onChange={(e) => set('han', e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="concept-description">Mô tả</label>
          <textarea id="concept-description" rows={3} value={form.description} onChange={(e) => set('description', e.target.value)} />
        </div>
        <FormError error={error} />
        <div className="actions">
          <button type="button" className="button button-ghost" onClick={onClose}>Hủy</button>
          <button type="submit" className="button">Tạo bản nháp</button>
        </div>
      </form>
    </Dialog>
  )
}

export default function TermsPage() {
  const { can } = useSession()
  const [input, setInput] = useState('')
  const [term, setTerm] = useState('')
  const [school, setSchool] = useState('')
  const [state, setState] = useState('')
  const [creating, setCreating] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setTerm(input.trim()), 300)
    return () => clearTimeout(timer)
  }, [input])
  const schools = useQuery('knowledge:schools', () => call(api.GET('/api/v1/schools')))
  const load = useCallback((cursor: string | null) => call(api.GET('/api/v1/concepts', {
    params: { query: { q: term || undefined, school_id: school || undefined, state: (state || undefined) as never, limit: 50, cursor } } })),
  [term, school, state])
  const concepts = usePagedList(`concepts:${term}:${school}:${state}`, load)
  const hits = useQuery(term ? `terms:${term}:${school}` : null, () => call(api.GET('/api/v1/terms', {
    params: { query: { q: term, school_id: school || undefined, limit: 20 } } })))

  if (!can('library:review')) return <Forbidden what="quản trị tri thức" />
  return (
    <>
      <title>Khái niệm · Kho Bát Tự</title>
      <PageHeader title="Tri thức" description="Khái niệm theo từng trường phái, thuật ngữ và cách gọi khác; chỉ bản đã duyệt được dùng khi tra cứu."
                  actions={<button type="button" className="button" onClick={() => setCreating(true)}>Khái niệm mới</button>} />
      <KnowledgeTabs />
      <div className="toolbar">
        <div className="field grow">
          <label htmlFor="concept-search">Tìm khái niệm hoặc thuật ngữ</label>
          <input id="concept-search" type="search" value={input} onChange={(e) => setInput(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="concept-school-filter">Trường phái</label>
          <select id="concept-school-filter" value={school} onChange={(e) => setSchool(e.target.value)}>
            <option value="">Tất cả</option>
            {schools.data?.data.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="concept-state-filter">Trạng thái</label>
          <select id="concept-state-filter" value={state} onChange={(e) => setState(e.target.value)}>
            <option value="">Tất cả</option>
            {STATE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.text}</option>)}
          </select>
        </div>
      </div>
      {term && hits.data && hits.data.data.length > 0 && (
        <section className="panel">
          <h2>Thuật ngữ khớp “{term}”</h2>
          <ul className="plain-list">
            {hits.data.data.map((h) => (
              <li key={h.id}>
                <strong>{h.form}</strong> <span className="muted small">({ALIAS_KINDS[h.alias_kind] ?? h.alias_kind})</span>
                {' → '}<Link href={`/knowledge/concepts/${h.concept_id}`}>{h.concept.label}</Link>
                <span className="muted small"> · {h.concept.school_key}</span> <StateBadge labels={KNOWLEDGE_STATES} value={h.state} />
              </li>
            ))}
          </ul>
        </section>
      )}
      {concepts.error && concepts.items.length === 0 ? <ErrorState error={concepts.error} retry={concepts.reload} />
        : concepts.loading ? <Loading rows={4} />
        : concepts.items.length === 0 ? (
          <Empty title={term || school || state ? 'Không có khái niệm khớp' : 'Chưa có khái niệm'}
                 action={<button type="button" className="button" onClick={() => setCreating(true)}>Khái niệm mới</button>}>
            Khái niệm cũng được đề xuất tự động khi xử lý sách; chúng chờ duyệt ở đây.
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Danh sách khái niệm</caption>
              <thead><tr><th scope="col">Khái niệm</th><th scope="col">Khóa</th><th scope="col">Trường phái</th>
                <th scope="col">Bản</th><th scope="col">Trạng thái</th><th scope="col">Tạo lúc</th></tr></thead>
              <tbody>
                {concepts.items.map((c) => (
                  <tr key={c.id}>
                    <td><Link href={`/knowledge/concepts/${c.id}`}>{c.label}</Link></td>
                    <td><code>{c.canonical_key}</code></td>
                    <td>{c.school_key}</td>
                    <td>{c.revision}</td>
                    <td><StateBadge labels={KNOWLEDGE_STATES} value={c.state} /></td>
                    <td className="nowrap">{formatDateTime(c.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      {concepts.hasMore && (
        <div className="pager"><button type="button" className="button button-secondary" onClick={concepts.loadMore}
                                       disabled={concepts.loadingMore}>Tải thêm</button></div>
      )}
      <NewConcept open={creating} onClose={() => setCreating(false)} />
    </>
  )
}
