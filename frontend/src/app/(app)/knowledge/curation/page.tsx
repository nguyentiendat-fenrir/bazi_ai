'use client'
// Curated definitions (docs/10 · Biên soạn): drafts written and checked by the curator model,
// waiting for a person. Drafts the model judged sound can be approved together.
import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { api, call } from '@/api/client'
import { KnowledgeTabs } from '@/components/KnowledgeTabs'
import { Empty, ErrorState, Forbidden, FormError, Loading, Notice, PageHeader, StateBadge } from '@/components/ui'
import { CURATION_STATUSES, CURATION_VERDICTS, KNOWLEDGE_STATES } from '@/lib/knowledge'
import { usePagedList, useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type Verdict = 'pass' | 'fix' | 'fail' | 'pending'

export default function CurationPage() {
  const { can } = useSession()
  const [input, setInput] = useState('')
  const [term, setTerm] = useState('')
  const [school, setSchool] = useState('')
  const [verdict, setVerdict] = useState<Verdict | ''>('pass')
  const [state, setState] = useState('draft')
  const [picked, setPicked] = useState<Record<string, number>>({})
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [outcome, setOutcome] = useState<string | null>(null)
  useEffect(() => {
    const timer = setTimeout(() => setTerm(input.trim()), 300)
    return () => clearTimeout(timer)
  }, [input])
  const schools = useQuery('knowledge:schools', () => call(api.GET('/api/v1/schools')))
  const load = useCallback((cursor: string | null) => call(api.GET('/api/v1/curation/definitions', {
    params: { query: { q: term || undefined, school_id: school || undefined, verdict: verdict || undefined,
                       state: state || undefined, limit: 50, cursor } } })),
  [term, school, verdict, state])
  const list = usePagedList(`curation:${term}:${school}:${verdict}:${state}`, load)

  if (!can('library:review')) return <Forbidden what="biên soạn định nghĩa" />
  const pickable = list.items.filter((d) => d.state === 'draft' || d.state === 'in_review')
  const chosen = Object.keys(picked)

  const toggle = (id: string, revision: number) => setPicked((now) => {
    const next = { ...now }
    if (id in next) delete next[id]
    else next[id] = revision
    return next
  })

  const approve = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const result = await call(api.POST('/api/v1/curation/definitions/approve', { body: {
        reason, items: chosen.map((id) => ({ concept_id: id, base_revision: picked[id] })) } }))
      const failed = result.data.filter((r) => !r.approved)
      setOutcome(`Đã duyệt ${result.data.length - failed.length} định nghĩa.` + (failed.length
        ? ` ${failed.length} mục không duyệt được: ${failed.map((f) => f.error).join('; ')}` : ''))
      setPicked({})
      setReason('')
      list.reload()
    } catch (caught) {
      setError(caught)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <title>Biên soạn · Kho Bát Tự</title>
      <PageHeader title="Tri thức" description="Định nghĩa do model biên soạn từ sách đã nạp và tự kiểm; người duyệt quyết định." />
      <KnowledgeTabs />
      {outcome && <Notice tone="ok">{outcome}</Notice>}
      <div className="toolbar">
        <div className="field grow">
          <label htmlFor="cur-search">Tìm theo tên</label>
          <input id="cur-search" type="search" value={input} onChange={(e) => setInput(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="cur-school">Trường phái</label>
          <select id="cur-school" value={school} onChange={(e) => setSchool(e.target.value)}>
            <option value="">Tất cả</option>
            {schools.data?.data.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="cur-verdict">Máy kiểm</label>
          <select id="cur-verdict" value={verdict} onChange={(e) => { setVerdict(e.target.value as Verdict | ''); setPicked({}) }}>
            <option value="">Tất cả</option>
            <option value="pass">Đạt</option>
            <option value="fix">Cần sửa</option>
            <option value="fail">Không đạt</option>
            <option value="pending">Chưa kiểm</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="cur-state">Trạng thái</label>
          <select id="cur-state" value={state} onChange={(e) => { setState(e.target.value); setPicked({}) }}>
            <option value="">Tất cả</option>
            {Object.entries(KNOWLEDGE_STATES).map(([value, [text]]) => <option key={value} value={value}>{text}</option>)}
          </select>
        </div>
      </div>
      {chosen.length > 0 && (
        <form className="panel inline-form" onSubmit={approve}>
          <div className="field grow">
            <label htmlFor="cur-reason">Duyệt {chosen.length} định nghĩa đã chọn · lý do</label>
            <input id="cur-reason" required minLength={3} maxLength={1000} value={reason}
                   placeholder="Ví dụ: đã đọc và đối chiếu nguồn" onChange={(e) => setReason(e.target.value)} />
          </div>
          <button type="submit" className="button" disabled={busy}>{busy ? 'Đang duyệt…' : 'Duyệt'}</button>
          <button type="button" className="button button-ghost" onClick={() => setPicked({})}>Bỏ chọn</button>
          <FormError error={error} />
        </form>
      )}
      {list.error && list.items.length === 0 ? <ErrorState error={list.error} retry={list.reload} />
        : list.loading ? <Loading rows={5} />
        : list.items.length === 0 ? (
          <Empty title={term || school || verdict || state ? 'Không có định nghĩa khớp bộ lọc' : 'Chưa có định nghĩa nào được biên soạn'}>
            Chạy <code>python -m backend.app.cli curate --as &lt;email&gt;</code> để model đọc sách đã nạp và soạn định nghĩa.
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">Định nghĩa chờ duyệt</caption>
              <thead><tr>
                <th scope="col">
                  <input type="checkbox" aria-label="Chọn tất cả mục duyệt được trên trang"
                         checked={pickable.length > 0 && pickable.every((d) => d.concept_id in picked)}
                         onChange={(e) => setPicked(e.target.checked
                           ? Object.fromEntries(pickable.map((d) => [d.concept_id, d.revision])) : {})} />
                </th>
                <th scope="col">Khái niệm</th><th scope="col">Trường phái</th><th scope="col">Máy kiểm</th>
                <th scope="col">Bản soạn</th><th scope="col">Nguồn</th><th scope="col">Trạng thái</th></tr></thead>
              <tbody>
                {list.items.map((d) => {
                  const open = d.state === 'draft' || d.state === 'in_review'
                  return (
                    <tr key={d.concept_id}>
                      <td>{open && <input type="checkbox" aria-label={`Chọn ${d.label}`} checked={d.concept_id in picked}
                                          onChange={() => toggle(d.concept_id, d.revision)} />}</td>
                      <td className="wrap"><Link href={`/knowledge/curation/${d.concept_id}`}>{d.label}</Link></td>
                      <td>{d.school_key}</td>
                      <td>{d.llm_verdict ? <StateBadge labels={CURATION_VERDICTS} value={d.llm_verdict} /> : <span className="muted">chưa kiểm</span>}
                        {d.problems > 0 && <span className="small muted"> · {d.problems} vấn đề</span>}</td>
                      <td><StateBadge labels={CURATION_STATUSES} value={d.status} /></td>
                      <td className="nowrap">{d.sources} đoạn · {d.independent_sources} sách</td>
                      <td><StateBadge labels={KNOWLEDGE_STATES} value={d.state} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      {list.hasMore && (
        <div className="pager"><button type="button" className="button button-secondary" onClick={list.loadMore}
                                       disabled={list.loadingMore}>Tải thêm</button></div>
      )}
    </>
  )
}
