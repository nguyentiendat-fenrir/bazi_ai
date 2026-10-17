'use client'
// Retrieval evaluation (docs/11 /evaluation, docs/13): datasets, their items, approval, runs
// against the active corpus with a chosen strategy, release gates, a baseline comparison,
// failed examples and a side-by-side comparison of runs. Scores from fixture models are
// labelled as such, never as a benchmark of real models.
import Link from 'next/link'
import { useCallback, useState } from 'react'
import type { FormEvent } from 'react'

import { api, call, type Schemas } from '@/api/client'
import { Dialog } from '@/components/Dialog'
import { Badge, Empty, ErrorState, Forbidden, FormError, Loading, Notice, PageHeader } from '@/components/ui'
import { formatDateTime, shortId } from '@/lib/format'
import { usePagedList, useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type Run = Schemas['EvaluationRunSummary']
type Dataset = Schemas['DatasetDTO']

const METRICS = ['recall@20', 'ndcg@10', 'mrr@10', 'page@1', 'school_leakage', 'no_answer_recall'] as const
const STRATEGIES: Record<string, string> = {
  hybrid_rerank: 'Kết hợp + rerank', hybrid: 'Kết hợp (từ khóa + vector)', lexical: 'Chỉ từ khóa', vector: 'Chỉ vector',
}
const DATASET_STATES: Record<string, [string, 'neutral' | 'ok' | 'warning']> = {
  draft: ['Bản nháp', 'warning'], approved: ['Đã duyệt', 'ok'], retired: ['Ngưng', 'neutral'],
}

function Gates({ run }: { run: Run }) {
  return (
    <span className="gates">
      {run.gates.map((g) => (
        <Badge key={g.metric} tone={g.passed === null ? 'neutral' : g.passed ? 'ok' : 'danger'}>
          {g.metric} {g.op} {g.target}{g.passed === null ? ' · chưa đo' : g.passed ? ' · đạt' : ' · trượt'}
        </Badge>
      ))}
      {run.regressed && <Badge tone="danger">hồi quy so với baseline</Badge>}
    </span>
  )
}

function metric(run: Run, name: string): string {
  const value = (run.metrics as Record<string, unknown>)[name]
  return typeof value === 'number' ? value.toFixed(3) : '—'
}

function Items({ dataset }: { dataset: Dataset }) {
  const load = useCallback((cursor: string | null) => call(api.GET('/api/v1/evaluation-datasets/{dataset_id}/items', {
    params: { path: { dataset_id: dataset.id }, query: { limit: 50, cursor } } })), [dataset.id])
  const items = usePagedList(`dataset-items:${dataset.id}`, load)
  if (items.error && items.items.length === 0) return <ErrorState error={items.error} retry={items.reload} />
  if (items.loading) return <Loading rows={3} />
  return (
    <>
      <div className="table-wrap">
        <table>
          <caption className="visually-hidden">Câu hỏi của bộ {dataset.name}</caption>
          <thead><tr><th scope="col">Khóa</th><th scope="col">Câu hỏi</th><th scope="col">Trang đúng</th><th scope="col">Phần</th></tr></thead>
          <tbody>
            {items.items.map((i) => {
              const expected = i.expected as { no_answer?: boolean, relevant?: { pages: number[] }[] }
              return (
                <tr key={i.id}>
                  <td><code>{i.key}</code></td>
                  <td className="wrap">{String((i.input as { query?: string }).query ?? '')}</td>
                  <td>{expected.no_answer ? <Badge>không có đáp án</Badge> : (expected.relevant ?? []).map((r) => r.pages.join(', ')).join(' · ')}</td>
                  <td>{i.split}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {items.hasMore && <div className="pager"><button type="button" className="button button-secondary" onClick={items.loadMore} disabled={items.loadingMore}>Tải thêm</button></div>}
    </>
  )
}

export default function EvaluationPage() {
  const { can } = useSession()
  const reviewer = can('library:review')
  const datasets = useQuery(reviewer ? 'evaluation-datasets' : null, () => call(api.GET('/api/v1/evaluation-datasets')))
  const profiles = useQuery(reviewer ? 'model-profiles' : null, () => call(api.GET('/api/v1/model-profiles')))
  const [selected, setSelected] = useState<string>('')
  const [split, setSplit] = useState('')
  const [topK, setTopK] = useState(10)
  const [strategy, setStrategy] = useState('hybrid_rerank')
  const [baseline, setBaseline] = useState('')
  const [shown, setShown] = useState<string | null>(null)
  const [approving, setApproving] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)

  const history = useQuery(reviewer ? 'evaluation-runs' : null, () =>
    call(api.GET('/api/v1/evaluation-runs', { params: { query: { limit: 20 } } })))
  const detail = useQuery(shown ? `evaluation-run:${shown}` : null, () =>
    call(api.GET('/api/v1/evaluation-runs/{run_id}', { params: { path: { run_id: shown! } } })))

  if (!reviewer) return <Forbidden what="đánh giá" />
  const list = datasets.data?.data ?? []
  const dataset = list.find((d) => d.id === selected) ?? null
  const fixtureModels = (profiles.data?.data ?? []).filter((p) => p.active && p.is_fixture && p.kind !== 'llm')

  const run = async (event: FormEvent) => {
    event.preventDefault()
    if (!dataset) return
    setBusy(true)
    setError(null)
    try {
      const done = await call(api.POST('/api/v1/evaluation-runs', { body: {
        dataset_id: dataset.id, top_k: topK, rerank: strategy === 'hybrid_rerank', tolerance: 0.02,
        strategy: strategy as 'hybrid_rerank', baseline_run_id: baseline || null,
        split: (split || null) as 'dev' | null } }))
      history.reload()
      setShown(done.data.id)
    } catch (caught) {
      setError(caught)
    } finally {
      setBusy(false)
    }
  }
  const approve = async () => {
    if (!dataset) return
    setError(null)
    try {
      await call(api.POST('/api/v1/evaluation-datasets/{dataset_id}/approve', { params: { path: { dataset_id: dataset.id } } }))
      setApproving(false)
      datasets.reload()
    } catch (caught) {
      setError(caught)
      setApproving(false)
    }
  }

  const runs = history.data?.data ?? []
  const current = detail.data?.data ?? null
  const failed = current?.results.filter((r) => r.status !== 'passed') ?? []
  const baselines = runs.filter((r) => dataset && r.dataset_id === dataset.id)
  const nameOf = (id: string) => list.find((d) => d.id === id)?.name ?? shortId(id)
  return (
    <>
      <title>Đánh giá · Kho Bát Tự</title>
      <PageHeader title="Đánh giá tra cứu" description="Đo tra cứu trên bộ câu hỏi có trang đúng đã biết, với kho tra cứu đang dùng." />
      {fixtureModels.length > 0 && (
        <Notice tone="warning">Đang dùng mô hình fixture kiểm thử ({fixtureModels.map((p) => p.model_name).join(', ')}): điểm chỉ để kiểm hệ thống, không phải số đo chất lượng mô hình thật.</Notice>
      )}
      {datasets.error ? <ErrorState error={datasets.error} retry={datasets.reload} />
        : !datasets.data ? <Loading rows={3} />
        : list.length === 0 ? (
          <Empty title="Chưa có bộ đánh giá">Bộ câu hỏi vàng (≥ 70 câu, trang đúng do chuyên gia gán) được nạp qua API hoặc CLI rồi duyệt ở đây.</Empty>
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <caption className="visually-hidden">Bộ đánh giá</caption>
                <thead><tr><th scope="col">Bộ</th><th scope="col">Phiên bản</th><th scope="col">Số câu</th><th scope="col">Trạng thái</th><th scope="col">Tạo lúc</th></tr></thead>
                <tbody>
                  {list.map((d) => (
                    <tr key={d.id} className={d.id === selected ? 'selected' : undefined}>
                      <td><button type="button" className="button button-ghost button-small" aria-pressed={d.id === selected}
                                  onClick={() => setSelected(d.id === selected ? '' : d.id)}>{d.name}</button></td>
                      <td>{d.version}</td>
                      <td>{d.items}</td>
                      <td><Badge tone={DATASET_STATES[d.state]?.[1] ?? 'neutral'}>{DATASET_STATES[d.state]?.[0] ?? d.state}</Badge></td>
                      <td className="nowrap">{formatDateTime(d.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {dataset && (
              <section className="panel">
                <div className="panel-head">
                  <h2>{dataset.name} · {dataset.version}</h2>
                  {dataset.state === 'draft' && <button type="button" className="button button-secondary" onClick={() => setApproving(true)}>Duyệt bộ…</button>}
                </div>
                {dataset.state === 'draft' && <Notice tone="info">Bộ nháp vẫn chạy được, nhưng kết quả ghi rõ là trên bộ chưa duyệt.</Notice>}
                <form className="toolbar" onSubmit={run}>
                  <div className="field">
                    <label htmlFor="ev-split">Phần</label>
                    <select id="ev-split" value={split} onChange={(e) => setSplit(e.target.value)}>
                      <option value="">Tất cả</option><option value="dev">dev</option><option value="test">test</option><option value="holdout">holdout</option>
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="ev-topk">Top k</label>
                    <input id="ev-topk" type="number" min={1} max={50} value={topK} onChange={(e) => setTopK(Number(e.target.value))} />
                  </div>
                  <div className="field">
                    <label htmlFor="ev-strategy">Cách tìm</label>
                    <select id="ev-strategy" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                      {Object.entries(STRATEGIES).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="ev-baseline">So với lần chạy</label>
                    <select id="ev-baseline" value={baseline} onChange={(e) => setBaseline(e.target.value)}>
                      <option value="">Không so</option>
                      {baselines.map((r) => (
                        <option key={r.id} value={r.id}>{formatDateTime(r.created_at)} · {STRATEGIES[String((r.config as { strategy?: string }).strategy)] ?? ''}</option>
                      ))}
                    </select>
                  </div>
                  <button type="submit" className="button" disabled={busy}>{busy ? 'Đang chạy…' : 'Chạy đánh giá'}</button>
                </form>
                <FormError error={error} />
                <details>
                  <summary>Câu hỏi trong bộ</summary>
                  <Items dataset={dataset} />
                </details>
              </section>
            )}
          </>
        )}
      {runs.length > 0 && (
        <section className="panel">
          <h2>So sánh các lần chạy</h2>
          <div className="table-wrap">
            <table>
              <caption className="visually-hidden">So sánh lần chạy đánh giá</caption>
              <thead><tr><th scope="col">Lần chạy</th><th scope="col">Bộ</th><th scope="col">Cấu hình</th>
                {METRICS.map((m) => <th key={m} scope="col">{m}</th>)}<th scope="col">p95 (ms)</th><th scope="col">Ngưỡng</th></tr></thead>
              <tbody>
                {runs.map((r) => {
                  const config = r.config as { top_k?: number, strategy?: string, split?: string | null, dataset_state?: string }
                  return (
                    <tr key={r.id} className={r.id === shown ? 'selected' : undefined}>
                      <td><button type="button" className="button button-ghost button-small" onClick={() => setShown(r.id)}>{formatDateTime(r.created_at)}</button></td>
                      <td>{nameOf(r.dataset_id)}{config.dataset_state === 'draft' && <> <Badge tone="warning">bộ nháp</Badge></>}</td>
                      <td className="small">{STRATEGIES[config.strategy ?? ''] ?? config.strategy} · k={config.top_k}{config.split ? ` · ${config.split}` : ''}</td>
                      {METRICS.map((m) => <td key={m}>{metric(r, m)}</td>)}
                      <td>{String(((r.metrics as { latency_ms?: { p95?: number } }).latency_ms?.p95) ?? '—')}</td>
                      <td><Gates run={r} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {current && (
        <section className="panel">
          <h2>Lần chạy {formatDateTime(current.created_at)}</h2>
          <p><Gates run={current} /></p>
          {current.comparison && (
            <div className="table-wrap">
              <table>
                <caption className="visually-hidden">So với baseline</caption>
                <thead><tr><th scope="col">Chỉ số</th><th scope="col">Baseline</th><th scope="col">Lần này</th><th scope="col">Chênh</th></tr></thead>
                <tbody>
                  {current.comparison.map((d) => (
                    <tr key={d.metric}>
                      <td>{d.metric}</td><td>{d.baseline.toFixed(3)}</td><td>{d.value.toFixed(3)}</td>
                      <td>{d.delta > 0 ? '+' : ''}{d.delta.toFixed(3)}{d.regressed && <> <Badge tone="danger">hồi quy</Badge></>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <h3>Câu trượt ({failed.length}/{current.results.length})</h3>
          {failed.length === 0 ? <p className="muted">Mọi câu đều có trang đúng trong top 20.</p> : (
            <ul className="plain-list">
              {failed.map((f) => {
                const actual = f.actual as { status?: string, hits?: { book_version_id: string, pages: number[] }[] }
                return (
                  <li key={f.key}>
                    <code>{f.key}</code> · {actual.status === 'ok' ? `trả ${actual.hits?.length ?? 0} đoạn, không có trang đúng` : `tra cứu: ${actual.status}`}
                    {actual.hits && actual.hits.length > 0 && (
                      <span className="muted small"> · đầu tiên: <Link href={`/versions/${actual.hits[0].book_version_id}`}>trang {actual.hits[0].pages.join(', ')}</Link></span>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      )}
      <Dialog open={approving} onClose={() => setApproving(false)} title="Duyệt bộ đánh giá?"
              footer={<>
                <button type="button" className="button button-ghost" onClick={() => setApproving(false)}>Không</button>
                <button type="button" className="button" onClick={() => void approve()}>Duyệt bộ</button>
              </>}>
        <p>Bộ đã duyệt không sửa được nữa; câu hỏi và trang đúng phải do chuyên gia kiểm.</p>
      </Dialog>
    </>
  )
}
