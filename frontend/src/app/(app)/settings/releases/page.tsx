'use client'
// Corpus and ontology releases (docs/07, docs/06). Search reads the active corpus release;
// an admin can roll back by activating an earlier ready one (compare-and-swap). Reviewers
// publish a new ontology release after approving concepts and terms.
import { useState } from 'react'

import { api, call, idempotencyKey, type Schemas } from '@/api/client'
import { Dialog } from '@/components/Dialog'
import { SettingsTabs } from '@/components/SettingsTabs'
import { Badge, ErrorState, Forbidden, FormError, Loading, Notice, PageHeader } from '@/components/ui'
import { formatDateTime, formatNumber, shortId } from '@/lib/format'
import { RULESET_STATES } from '@/lib/knowledge'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type Release = Schemas['ReleaseDTO']
const CORPUS_STATES: Record<string, string> = { building: 'Đang dựng', ready: 'Sẵn sàng', active: 'Đang dùng', retired: 'Ngưng' }

export default function ReleasesPage() {
  const { can } = useSession()
  const reviewer = can('library:review')
  const corpus = useQuery(reviewer ? 'corpus-releases' : null, () => call(api.GET('/api/v1/corpus-releases', { params: { query: { limit: 50 } } })))
  const ontology = useQuery(reviewer ? 'ontology-releases' : null, () => call(api.GET('/api/v1/ontology-releases')))
  const preview = useQuery(reviewer ? 'ontology-preview' : null, () => call(api.GET('/api/v1/ontology-releases/preview')))
  const [rollback, setRollback] = useState<Release | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [outcome, setOutcome] = useState<string | null>(null)
  if (!reviewer) return <Forbidden what="bản kho tra cứu" />

  const active = corpus.data?.data.active ?? null
  const activate = async () => {
    if (!rollback) return
    setError(null)
    try {
      await call(api.POST('/api/v1/corpus-releases/{release_id}/activate', {
        params: { path: { release_id: rollback.id } }, body: { expected_active_id: active?.release_id ?? null } }))
      setOutcome(`Tra cứu đang dùng bản ${shortId(rollback.id)}.`)
      setRollback(null)
      corpus.reload()
    } catch (caught) {
      setError(caught)
      corpus.reload()
    }
  }
  const publishOntology = async () => {
    setError(null)
    try {
      const done = await call(api.POST('/api/v1/ontology-releases', { body: {}, headers: { 'Idempotency-Key': idempotencyKey() } }))
      setOutcome(`Đã phát hành ontology ${(done.data as { version?: string }).version ?? ''}.`)
      ontology.reload()
      preview.reload()
      corpus.reload()
    } catch (caught) {
      setError(caught)
    }
  }

  const diff = preview.data?.data
  return (
    <>
      <title>Bản kho tra cứu · Cài đặt</title>
      <PageHeader title="Cài đặt" />
      <SettingsTabs />
      {outcome && <Notice tone="ok">{outcome}</Notice>}
      <FormError error={error} />
      <section className="panel">
        <h2>Kho tra cứu</h2>
        {corpus.error ? <ErrorState error={corpus.error} retry={corpus.reload} /> : !corpus.data ? <Loading rows={3} />
          : corpus.data.data.releases.length === 0 ? <p className="muted">Chưa có bản kho nào; publish sách đầu tiên để tạo.</p> : (
            <div className="table-wrap">
              <table>
                <caption className="visually-hidden">Các bản kho tra cứu</caption>
                <thead><tr><th scope="col">Bản</th><th scope="col">Phiên bản sách</th><th scope="col">Trạng thái</th>
                  <th scope="col">Ontology</th><th scope="col">Tạo lúc</th><th scope="col"><span className="visually-hidden">Thao tác</span></th></tr></thead>
                <tbody>
                  {corpus.data.data.releases.map((r) => (
                    <tr key={r.id}>
                      <td><code>{shortId(r.id)}</code>{r.active && <> <Badge tone="ok">đang dùng</Badge></>}</td>
                      <td>{formatNumber(r.members_count)}</td>
                      <td>{CORPUS_STATES[r.state] ?? r.state}</td>
                      <td><code>{shortId(r.ontology_release_id)}</code></td>
                      <td className="nowrap">{formatDateTime(r.created_at)}</td>
                      <td>{!r.active && r.state === 'ready' && can('system:admin') && (
                        <button type="button" className="button button-secondary button-small" onClick={() => setRollback(r)}>Dùng bản này…</button>
                      )}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </section>
      <section className="panel">
        <div className="panel-head">
          <h2>Ontology</h2>
          {diff?.changed && <button type="button" className="button" onClick={() => void publishOntology()}>Phát hành ontology mới</button>}
        </div>
        {diff && (diff.changed
          ? <Notice tone="info">So với {diff.base_version ?? 'chưa có bản nào'}: khái niệm +{diff.concepts.added.length}/−{diff.concepts.removed.length}, thuật ngữ +{diff.terms.added.length}/−{diff.terms.removed.length}. Tra cứu dùng bản mới sau khi phát hành (không cần embed lại).</Notice>
          : <p className="muted small">Không có thay đổi đã duyệt nào chưa phát hành.</p>)}
        {ontology.error ? <ErrorState error={ontology.error} retry={ontology.reload} /> : !ontology.data ? <Loading rows={2} />
          : ontology.data.data.length === 0 ? <p className="muted">Chưa phát hành ontology.</p> : (
            <ul className="plain-list">
              {ontology.data.data.map((o) => (
                <li key={o.id}>
                  <strong>{o.version}</strong> · {o.concepts} khái niệm · {o.terms} thuật ngữ{' '}
                  <Badge tone={RULESET_STATES[o.state]?.[1] ?? 'neutral'}>{o.state === 'published' ? 'đã phát hành' : o.state}</Badge>
                  {o.pinned_by_active_corpus && <> <Badge tone="ok">kho đang dùng</Badge></>}
                  <span className="muted small"> · {formatDateTime(o.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
      </section>
      <Dialog open={!!rollback} onClose={() => setRollback(null)} title="Đổi bản kho tra cứu?"
              footer={<>
                <button type="button" className="button button-ghost" onClick={() => setRollback(null)}>Không</button>
                <button type="button" className="button" onClick={() => void activate()}>Dùng bản này</button>
              </>}>
        {rollback && <p>Tra cứu sẽ dùng bản <code>{shortId(rollback.id)}</code> ({formatNumber(rollback.members_count)} phiên bản sách, tạo {formatDateTime(rollback.created_at)}) thay cho bản đang dùng. Nếu ai đó vừa đổi bản, thao tác sẽ bị từ chối để bạn xem lại.</p>}
      </Dialog>
    </>
  )
}
