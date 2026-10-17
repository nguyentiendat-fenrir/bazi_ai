'use client'
// One concept (docs/06): its revisions, terms and review history. Editing makes a new draft
// revision; approval is a separate action with a reason.
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useState } from 'react'
import type { FormEvent } from 'react'

import { api, call } from '@/api/client'
import { KnowledgeTabs } from '@/components/KnowledgeTabs'
import { ReviewPanel, type ReviewOutcome } from '@/components/ReviewPanel'
import { ErrorState, Facts, Forbidden, FormError, Loading, Notice, PageHeader, StateBadge } from '@/components/ui'
import { formatDateTime } from '@/lib/format'
import { ALIAS_KINDS, KNOWLEDGE_STATES } from '@/lib/knowledge'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type AliasKind = 'same_concept' | 'translation_variant' | 'related' | 'contrasts_with'

export default function ConceptPage() {
  const { conceptId } = useParams<{ conceptId: string }>()
  const router = useRouter()
  const { can } = useSession()
  const concept = useQuery(`concept:${conceptId}`, () =>
    call(api.GET('/api/v1/concepts/{concept_id}', { params: { path: { concept_id: conceptId } } })))
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({ label: '', description: '', reason: '' })
  const [alias, setAlias] = useState<{ form: string, alias_kind: AliasKind, language: string }>(
    { form: '', alias_kind: 'same_concept', language: 'vi' })
  const [error, setError] = useState<unknown>(null)
  const [aliasError, setAliasError] = useState<unknown>(null)
  const [outcome, setOutcome] = useState<string | null>(null)

  if (!can('library:review')) return <Forbidden what="quản trị tri thức" />
  if (concept.error) return <ErrorState error={concept.error} retry={concept.reload} />
  if (!concept.data) return <Loading rows={5} />
  const c = concept.data.data
  const latest = Math.max(...c.revisions.map((r) => r.revision), c.revision)

  const reviewed = (result: ReviewOutcome) => {
    const parts = [`Trạng thái mới: ${KNOWLEDGE_STATES[result.state]?.[0] ?? result.state}.`]
    if (result.terms_approved) parts.push(`${result.terms_approved} thuật ngữ được duyệt lại theo bản trước.`)
    if (result.analyses_stale) parts.push(`${result.analyses_stale} phân tích được đánh dấu cũ.`)
    setOutcome(parts.join(' '))
    concept.reload()
  }

  const revise = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      const made = await call(api.POST('/api/v1/concepts/{concept_id}/revisions', {
        params: { path: { concept_id: c.id } },
        body: { base_revision: c.revision, label: draft.label, description: draft.description, reason: draft.reason } }))
      setEditing(false)
      if (made.data.id === c.id) concept.reload()
      else router.push(`/knowledge/concepts/${made.data.id}`)
    } catch (caught) {
      setError(caught)
    }
  }

  const addAlias = async (event: FormEvent) => {
    event.preventDefault()
    setAliasError(null)
    try {
      await call(api.POST('/api/v1/terms', { body: { concept_id: c.id, ...alias, form: alias.form.trim() } }))
      setAlias({ ...alias, form: '' })
      concept.reload()
    } catch (caught) {
      setAliasError(caught)
    }
  }

  return (
    <>
      <title>{`${c.label} · Khái niệm`}</title>
      <PageHeader title={c.label} back={{ href: '/knowledge/terms', label: 'Khái niệm' }}
                  description={<>{c.school_key} · <code>{c.canonical_key}</code> · bản {c.revision} <StateBadge labels={KNOWLEDGE_STATES} value={c.state} /></>}
                  actions={c.revision === latest && !editing && (
                    <button type="button" className="button button-secondary" onClick={() => {
                      setDraft({ label: c.label, description: c.description, reason: '' })
                      setEditing(true)
                    }}>Sửa thành bản mới</button>
                  )} />
      <KnowledgeTabs />
      {c.revision !== latest && (
        <Notice tone="warning">Đây là bản cũ. <Link href={`/knowledge/concepts/${c.revisions.find((r) => r.revision === latest)?.id}`}>Mở bản {latest}</Link>.</Notice>
      )}
      {outcome && <Notice tone="ok">{outcome}</Notice>}
      <div className="grid">
        <section className="panel">
          <h2>Nội dung</h2>
          {editing ? (
            <form onSubmit={revise}>
              <div className="field">
                <label htmlFor="rev-label">Tên hiển thị</label>
                <input id="rev-label" required value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="rev-description">Mô tả</label>
                <textarea id="rev-description" rows={4} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="rev-reason">Lý do sửa</label>
                <input id="rev-reason" required value={draft.reason} onChange={(e) => setDraft({ ...draft, reason: e.target.value })} />
              </div>
              <p className="hint">Bản mới là bản nháp; bản đã duyệt vẫn được dùng cho tới khi bản mới được duyệt.</p>
              <FormError error={error} />
              <div className="actions">
                <button type="button" className="button button-ghost" onClick={() => setEditing(false)}>Hủy</button>
                <button type="submit" className="button">Lưu bản nháp</button>
              </div>
            </form>
          ) : (
            <>
              <Facts items={[['Mô tả', c.description || <span className="muted">Chưa có</span>], ['Tạo lúc', formatDateTime(c.created_at)]]} />
              {c.revision === latest && (
                <ReviewPanel kind="concept" id={c.id} revision={c.revision} state={c.state} onDone={reviewed} />
              )}
            </>
          )}
        </section>
        <section className="panel">
          <h2>Lịch sử</h2>
          <ul className="plain-list">
            {c.revisions.map((r) => (
              <li key={r.id}>
                {r.id === c.id ? <strong>Bản {r.revision}</strong> : <Link href={`/knowledge/concepts/${r.id}`}>Bản {r.revision}</Link>}
                {' '}<StateBadge labels={KNOWLEDGE_STATES} value={r.state} />
              </li>
            ))}
          </ul>
          {c.reviews.length > 0 && (
            <ul className="plain-list review-history">
              {c.reviews.map((r, i) => (
                <li key={i} className="small">{formatDateTime(r.created_at)} · {r.decision} bản {r.base_revision}: {r.reason}</li>
              ))}
            </ul>
          )}
        </section>
      </div>
      <section className="panel">
        <h2>Thuật ngữ</h2>
        {c.terms.length === 0 ? <p className="muted">Chưa có thuật ngữ.</p> : (
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Thuật ngữ của khái niệm</caption>
              <thead><tr><th scope="col">Cách viết</th><th scope="col">Loại</th><th scope="col">Ngôn ngữ</th>
                <th scope="col">Trạng thái</th><th scope="col">Duyệt</th></tr></thead>
              <tbody>
                {c.terms.map((t) => (
                  <tr key={t.id}>
                    <td>{t.form}</td>
                    <td>{ALIAS_KINDS[t.alias_kind] ?? t.alias_kind}</td>
                    <td>{t.language}</td>
                    <td><StateBadge labels={KNOWLEDGE_STATES} value={t.state} /></td>
                    <td><ReviewPanel kind="term" id={t.id} revision={1} state={t.state} compact subject={`“${t.form}”`}
                                     onDone={reviewed} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <form className="inline-form" onSubmit={addAlias}>
          <div className="field">
            <label htmlFor="alias-form">Thêm cách gọi</label>
            <input id="alias-form" required maxLength={200} value={alias.form} onChange={(e) => setAlias({ ...alias, form: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="alias-kind">Loại</label>
            <select id="alias-kind" value={alias.alias_kind} onChange={(e) => setAlias({ ...alias, alias_kind: e.target.value as AliasKind })}>
              {(['same_concept', 'translation_variant', 'related', 'contrasts_with'] as const).map((k) => <option key={k} value={k}>{ALIAS_KINDS[k]}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="alias-language">Ngôn ngữ</label>
            <select id="alias-language" value={alias.language} onChange={(e) => setAlias({ ...alias, language: e.target.value })}>
              <option value="vi">Tiếng Việt</option><option value="zh">Chữ Hán</option><option value="en">Tiếng Anh</option>
            </select>
          </div>
          <button type="submit" className="button button-secondary">Thêm</button>
        </form>
        <FormError error={aliasError} />
      </section>
    </>
  )
}
