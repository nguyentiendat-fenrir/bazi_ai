'use client'
// Judging of RAG answers (shared judge password, no app account). A judge picks a run,
// reads each question's answer next to the book passages the model was given and the
// chunks retrieval found, and saves one score sheet per question.
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'

import { api, call } from '@/api/client'
import type { Schemas } from '@/api/client'
import { ApiError, describe } from '@/api/problem'
import { withBase } from '@/lib/base'
import { Badge, Loading } from '@/components/ui'
import {
  answerParts, DROP_LABELS, judgeName, NEED_KINDS, NEED_LABELS, pages, RELEVANCE, RUBRIC, score,
  SPEAKER_LABELS, STATUS_LABELS, statusTone, STOP_LABELS,
} from '@/lib/judge'
import type { AskOut, ChildOut, ChunkLabel, HarnessTrace, ParentOut, Relevance } from '@/lib/judge'

type Judge = Schemas['JudgeMe']
type Run = Schemas['RunSummary']
type Summary = Schemas['ResultSummary']
type Detail = Schemas['ResultDetail']

export default function JudgePage() {
  const [judge, setJudge] = useState<Judge | null | undefined>(undefined)

  useEffect(() => {
    call(api.GET('/api/v1/judge/me'), { quietAuth: true })
      .then((r) => setJudge(r.data))
      .catch(() => setJudge(null))
  }, [])

  const signOut = async () => {
    await api.DELETE('/api/v1/judge/session')
    setJudge(null)
  }

  if (judge === undefined) return <div className="login"><Loading label="Đang kiểm tra…" /></div>
  if (judge === null) return <JudgeGate onSignedIn={setJudge} />
  return <Workspace judge={judge} onSignOut={signOut} />
}

function JudgeGate({ onSignedIn }: { onSignedIn: (judge: Judge) => void }) {
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => setName(judgeName.get()), [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const result = await call(api.POST('/api/v1/judge/session', {
        body: { name: name.trim(), password } }), { quietAuth: true })
      judgeName.set(name.trim())
      onSignedIn(result.data)
    } catch (caught) {
      setError(caught)
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  const wrong = error instanceof ApiError && error.code === 'AUTH_REQUIRED'
  return (
    <div className="login">
      <title>Chấm câu trả lời · Kho Bát Tự</title>
      <form className="login-card" onSubmit={submit} noValidate>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">八</span>
          <span className="brand-name">Chấm câu trả lời</span>
        </div>
        <h1>Vào trang chấm</h1>
        <p className="muted">Dùng mật khẩu chấm được chia sẻ. Tên của bạn gắn với các phiếu chấm.</p>
        {error ? (
          <div className="form-error" role="alert">
            <p>{wrong ? 'Mật khẩu chấm không đúng.' : describe(error)}</p>
          </div>
        ) : null}
        <div className="field">
          <label htmlFor="judge-name">Tên người chấm</label>
          <input id="judge-name" autoComplete="nickname" required maxLength={80} value={name}
                 onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="judge-password">Mật khẩu chấm</label>
          <input id="judge-password" type="password" autoComplete="current-password" required
                 value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <button className="button" type="submit" disabled={busy || !name.trim() || !password}>
          {busy ? 'Đang vào…' : 'Vào trang chấm'}
        </button>
      </form>
    </div>
  )
}

function Workspace({ judge, onSignOut }: { judge: Judge, onSignOut: () => void }) {
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [runId, setRunId] = useState<string>('')
  const [results, setResults] = useState<Summary[] | null>(null)
  const [resultId, setResultId] = useState<string>('')
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    call(api.GET('/api/v1/judge/runs'))
      .then((r) => {
        setRuns(r.data)
        if (r.data.length) setRunId(r.data[0].id)
      })
      .catch(setError)
  }, [])

  const loadResults = useCallback(async (id: string, keep?: string) => {
    if (!id) return
    const r = await call(api.GET('/api/v1/judge/runs/{run_id}/results', {
      params: { path: { run_id: id } } }))
    setResults(r.data)
    setResultId(keep && r.data.some((x) => x.id === keep) ? keep : (r.data[0]?.id ?? ''))
  }, [])

  useEffect(() => {
    setResults(null)
    loadResults(runId).catch(setError)
  }, [runId, loadResults])

  const run = runs?.find((r) => r.id === runId)
  const done = results?.filter((r) => r.scored_by_me).length ?? 0

  return (
    <div className="judge">
      <title>Chấm câu trả lời · Kho Bát Tự</title>
      <header className="judge-bar">
        <strong>Chấm câu trả lời RAG</strong>
        <label className="judge-run">
          <span className="muted small">Lượt chạy</span>
          <select value={runId} onChange={(e) => setRunId(e.target.value)}>
            {(runs ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                {r.label} · {new Date(r.created_at).toLocaleString('vi-VN')}
              </option>
            ))}
          </select>
        </label>
        {results && <span className="muted small">Đã chấm {done}/{results.length}</span>}
        {run && (
          <a className="button button-secondary button-small"
             href={withBase(`/api/v1/judge/runs/${run.id}/scores.csv`)}>Tải điểm (CSV)</a>
        )}
        <span className="grow" />
        <span className="small">Người chấm: <strong>{judge.name}</strong></span>
        <button className="button button-ghost button-small" onClick={onSignOut}>Thoát</button>
      </header>
      {error ? <div className="notice notice-danger" role="alert">{describe(error)}</div> : null}
      {runs && runs.length === 0 && (
        <div className="notice notice-info">Chưa có lượt chạy nào. Chạy <code>scripts/rag_eval.py run</code> trước.</div>
      )}
      {run && <RunSettings run={run} />}
      <div className="judge-body">
        <nav className="judge-list" aria-label="Câu hỏi">
          {results === null ? <Loading rows={6} /> : results.map((r) => (
            <button key={r.id} className={'judge-item' + (r.id === resultId ? ' judge-item-active' : '')}
                    onClick={() => setResultId(r.id)}>
              <span className="judge-item-head">
                <strong>Câu {r.ordinal}</strong>
                {r.scored_by_me ? <Badge tone="ok">đã chấm</Badge> : <Badge>chưa chấm</Badge>}
              </span>
              <span className="judge-item-q">{r.question}</span>
              <span className="muted small">{STATUS_LABELS[r.status] ?? r.status}
                {r.scores > 0 ? ` · ${r.scores} phiếu` : ''}</span>
            </button>
          ))}
        </nav>
        <main className="judge-detail">
          {resultId ? (
            <ResultView key={resultId} resultId={resultId}
                        onSaved={() => loadResults(runId, resultId).catch(setError)} />
          ) : <p className="muted">Chọn một câu hỏi.</p>}
        </main>
      </div>
    </div>
  )
}

function RunSettings({ run }: { run: Run }) {
  const s = run.settings as Record<string, unknown>
  const v = run.versions as Record<string, unknown>
  return (
    <details className="judge-settings">
      <summary className="small muted">Cấu hình lượt chạy</summary>
      <p className="small mono">
        dense {String(s.dense_weight)} · sparse {String(s.sparse_weight)} · rerank depth {String(s.rerank_depth)}
        · context {String(s.context_tokens)} tok · thinking {String(s.thinking)} · LLM {String(v.llm)}
        · embedder {String(v.embedder)} · reranker {String(v.reranker)} · prompt {String(v.answer_prompt)}
      </p>
    </details>
  )
}

function ResultView({ resultId, onSaved }: { resultId: string, onSaved: () => void }) {
  const [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [scores, setScores] = useState<Record<string, number | boolean | null>>({})
  const [labels, setLabels] = useState<Record<string, ChunkLabel>>({})
  const [notes, setNotes] = useState('')
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)

  useEffect(() => {
    call(api.GET('/api/v1/judge/results/{result_id}', { params: { path: { result_id: resultId } } }))
      .then((r) => {
        setDetail(r.data)
        const mine = r.data.my_score
        setScores((mine?.scores ?? {}) as Record<string, number | boolean | null>)
        setLabels((mine?.chunk_labels ?? {}) as Record<string, ChunkLabel>)
        setNotes(mine?.notes ?? '')
      })
      .catch(setError)
  }, [resultId])

  const answer = detail?.payload as AskOut | undefined
  const harness = (detail?.payload as { harness?: HarnessTrace } | undefined)?.harness
  const parentsByHandle = useMemo(() => Object.fromEntries(
    (answer?.parents ?? []).map((p) => [p.handle, p])), [answer])

  if (error) return <div className="notice notice-danger" role="alert">{describe(error)}</div>
  if (!detail || !answer) return <Loading rows={8} />

  const showParent = (handle: string) => {
    setOpen((o) => ({ ...o, [handle]: true }))
    document.getElementById(`parent-${handle}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const label = (chunkId: string, patch: Partial<ChunkLabel>) => setLabels((current) => {
    const base: ChunkLabel = current[chunkId] ?? { relevance: null, suggest_rule: false }
    return { ...current, [chunkId]: { ...base, ...patch } }
  })

  const save = async () => {
    setSaving(true)
    setSaved(null)
    setError(null)
    try {
      const r = await call(api.PUT('/api/v1/judge/results/{result_id}/score', {
        params: { path: { result_id: resultId } },
        body: { scores, chunk_labels: labels, notes } }))
      setSaved(r.data.rule_suggestions
        ? `Đã lưu. Đã gửi ${r.data.rule_suggestions} đoạn cho chuyên gia duyệt quy tắc.` : 'Đã lưu.')
      onSaved()
    } catch (caught) {
      setError(caught)
    } finally {
      setSaving(false)
    }
  }

  return (
    <article className="judge-result">
      <h2>Câu {detail.ordinal}. {detail.question}</h2>
      <p className="small muted">
        <Badge tone={statusTone(answer.status)}>
          {STATUS_LABELS[answer.status] ?? answer.status}
        </Badge>{' '}
        {detail.latency_ms ? `${(detail.latency_ms / 1000).toFixed(1)} s` : ''}
        {answer.usage && (answer.usage as Record<string, unknown>).prompt_tokens
          ? ` · ${String((answer.usage as Record<string, unknown>).prompt_tokens)} token vào / ${String((answer.usage as Record<string, unknown>).completion_tokens)} ra`
          : ''}
        {answer.degraded?.length ? ` · suy giảm: ${answer.degraded.join(', ')}` : ''}
      </p>

      <section className="panel">
        <h3>Câu trả lời</h3>
        {answer.answer ? (
          <div className="judge-answer">
            {answerParts(answer.answer).map((part, i) => part.handle ? (
              parentsByHandle[part.handle]
                ? <button key={i} className="cite" onClick={() => showParent(part.handle!)}>{part.text}</button>
                : <span key={i} className="cite cite-bad">{part.text}</span>
            ) : <span key={i}>{part.text}</span>)}
          </div>
        ) : <p className="muted">(Không có câu trả lời — {answer.error ?? STATUS_LABELS[answer.status] ?? answer.status})</p>}
        {answer.invalid_citations?.length ? (
          <div className="notice notice-warning">Mô hình trích mã không có trong nguồn (đã bỏ): {answer.invalid_citations.join(', ')}</div>
        ) : null}
        {answer.model_said_insufficient ? (
          <div className="notice notice-info">Mô hình tự đánh giá: nguồn không đủ để trả lời.</div>
        ) : null}
        {answer.raw_answer && answer.raw_answer !== answer.answer ? (
          <details><summary className="small muted">Bản gốc của mô hình (trước kiểm tra)</summary>
            <pre className="judge-pre">{answer.raw_answer}</pre></details>
        ) : null}
      </section>

      {harness && <HarnessPanel harness={harness} onCite={showParent} />}

      <section className="panel judge-form">
        <h3>Phiếu chấm</h3>
        {RUBRIC.map((c) => (
          <fieldset key={c.key} className="judge-criterion">
            <legend><strong>{c.label}</strong> <span className="muted small">— {c.help}</span></legend>
            {c.kind === 'scale' ? (
              <div className="segmented" role="radiogroup" aria-label={c.label}>
                <span className="muted small">{c.low}</span>
                {[1, 2, 3, 4, 5].map((n) => (
                  <label key={n} className={'judge-pick' + (scores[c.key] === n ? ' judge-pick-on' : '')}>
                    <input type="radio" name={c.key} value={n} checked={scores[c.key] === n}
                           onChange={() => setScores((s) => ({ ...s, [c.key]: n }))} />
                    {n}
                  </label>
                ))}
                <span className="muted small">{c.high}</span>
              </div>
            ) : (
              <div className="segmented" role="radiogroup" aria-label={c.label}>
                {[{ v: true, t: 'Có' }, { v: false, t: 'Không' }].map((o) => (
                  <label key={o.t} className={'judge-pick' + (scores[c.key] === o.v ? ' judge-pick-on' : '')}>
                    <input type="radio" name={c.key} checked={scores[c.key] === o.v}
                           onChange={() => setScores((s) => ({ ...s, [c.key]: o.v }))} />
                    {o.t}
                  </label>
                ))}
              </div>
            )}
          </fieldset>
        ))}
        <div className="field">
          <label htmlFor="judge-notes">Ghi chú (sai ở đâu, nên trả lời thế nào, đoạn nào đáng lẽ phải tìm được…)</label>
          <textarea id="judge-notes" rows={4} maxLength={5000} value={notes}
                    onChange={(e) => setNotes(e.target.value)} />
        </div>
        <p className="small muted">Gắn nhãn từng đoạn truy xuất ở bảng bên dưới — nhãn được lưu cùng phiếu này.</p>
        <div className="actions">
          <button className="button" onClick={save} disabled={saving}>{saving ? 'Đang lưu…' : 'Lưu phiếu chấm'}</button>
          {saved && <span className="small" role="status">{saved}</span>}
        </div>
      </section>

      <section className="panel">
        <h3>Nguồn đưa cho mô hình ({answer.parents?.length ?? 0})</h3>
        <p className="small muted">Mỗi nguồn là cả mục sách chứa đoạn tìm được; mô hình chỉ được trả lời từ những đoạn này.</p>
        {(answer.parents ?? []).map((p) => (
          <ParentCard key={p.handle} parent={p} open={!!open[p.handle]}
                      onToggle={() => setOpen((o) => ({ ...o, [p.handle]: !o[p.handle] }))} />
        ))}
      </section>

      <section className="panel">
        <h3>Đoạn truy xuất được ({answer.children?.length ?? 0})</h3>
        <p className="small muted">
          Xếp theo reranker (nếu có) rồi theo điểm trộn = {String((answer.settings as Record<string, unknown>)?.dense_weight)}·dense + {String((answer.settings as Record<string, unknown>)?.sparse_weight)}·sparse (đã chuẩn hóa 0–1 trong câu hỏi này).
        </p>
        <div className="table-wrap">
          <table className="judge-chunks">
            <thead>
              <tr>
                <th>#</th><th>Sách · mục · trang</th><th title="cosine (đã chuẩn hóa)">Dense</th>
                <th title="BM25 (đã chuẩn hóa)">Sparse</th><th>Trộn</th><th>Rerank</th><th>Nguồn</th>
                <th>Đánh giá</th><th title="Đoạn có quy tắc đáng để chuyên gia duyệt">Quy tắc?</th>
              </tr>
            </thead>
            <tbody>
              {(answer.children ?? []).map((c) => (
                <ChunkRow key={c.chunk_id} chunk={c} label={labels[c.chunk_id]}
                          onLabel={(patch) => label(c.chunk_id, patch)}
                          onParent={c.parent_handle ? () => showParent(c.parent_handle!) : undefined} />
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </article>
  )
}

function HarnessPanel({ harness, onCite }: { harness: HarnessTrace, onCite: (handle: string) => void }) {
  const cite = (handle: string) => /^P\d+$/.test(handle)
    ? <button key={handle} className="cite" onClick={() => onCite(handle)}>[{handle}]</button>
    : <span key={handle} className="cite">[{handle}]</span>
  return (
    <section className="panel">
      <h3>Quá trình trả lời</h3>
      <p className="small muted">
        {harness.rounds} vòng tìm · dừng vì {STOP_LABELS[harness.stop_reason ?? ''] ?? harness.stop_reason ?? '—'}
        {' · '}{harness.llm_calls} lần gọi Qwen
        {harness.focus ? ` · trọng tâm ${harness.focus}` : ''}
      </p>
      {harness.facts && (
        <details><summary className="small muted">Dữ kiện lá số [F] (tính bằng bảng tra)</summary>
          <pre className="judge-pre small">{harness.facts}</pre></details>
      )}
      <h4>Các ý cần biết</h4>
      <ul className="small">
        {harness.needs.map((n) => (
          <li key={n.id}>
            <Badge tone={n.status === 'du' ? 'ok' : n.status === 'thieu' ? 'danger' : 'warning'}>
              {NEED_LABELS[n.status] ?? n.status}</Badge>{' '}
            <strong>{n.id}</strong> <span className="muted">({NEED_KINDS[n.kind] ?? n.kind}{n.school ? `, ${n.school}` : ''})</span>{' '}
            {n.text}
            {n.quotes.length ? (
              <ul>{n.quotes.slice(0, 3).map((q, i) => <li key={i}>{cite(q.handle)} “{q.quote}”</li>)}</ul>
            ) : null}
          </li>
        ))}
      </ul>
      {harness.dropped.length ? (
        <details><summary className="small muted">Nhận định bị loại khi kiểm nguồn ({harness.dropped.length})</summary>
          <ul className="small">{harness.dropped.map((d, i) => (
            <li key={i}><span className="muted">({DROP_LABELS[d.reason.split(':')[0]] ?? d.reason})</span> {d.text}{' '}
              {d.sources.map(cite)}</li>
          ))}</ul>
        </details>
      ) : null}
    </section>
  )
}

function ParentCard({ parent, open, onToggle }: { parent: ParentOut, open: boolean, onToggle: () => void }) {
  return (
    <div id={`parent-${parent.handle}`} className={'judge-parent' + (parent.cited ? ' judge-parent-cited' : '')}>
      <div className="judge-parent-head">
        <strong>[{parent.handle}]</strong>
        <span>{parent.book_title}</span>
        {parent.school && <Badge tone="info">{parent.school}</Badge>}
        <span className="muted small">{parent.breadcrumb.join(' › ')} · {pages(parent.page_start, parent.page_end)} · {parent.tokens} token</span>
        {parent.cited ? <Badge tone="ok">được trích</Badge> : <Badge>không trích</Badge>}
        {parent.expert_reviewed && <Badge tone="warning">có quy tắc đã duyệt</Badge>}
        <span className="grow" />
        <button className="button button-ghost button-small" onClick={onToggle}>{open ? 'Thu gọn' : 'Xem toàn văn'}</button>
      </div>
      {parent.summary && <p className="small"><em>Tóm tắt (Qwen):</em> {parent.summary}</p>}
      {parent.reviewed_rules?.length ? (
        <ul className="small">{parent.reviewed_rules.map((r) => <li key={r.assertion_id}>Quy tắc đã duyệt: {r.text}</li>)}</ul>
      ) : null}
      {open && <pre className="judge-pre">{parent.text}</pre>}
    </div>
  )
}

function ChunkRow({ chunk, label, onLabel, onParent }: {
  chunk: ChildOut, label?: ChunkLabel, onLabel: (patch: Partial<ChunkLabel>) => void, onParent?: () => void,
}) {
  const [open, setOpen] = useState(false)
  const s = chunk.scores
  const meta = chunk.meta as Record<string, unknown>
  return (
    <>
      <tr className={chunk.parent_handle ? 'judge-chunk-used' : undefined}>
        <td>{chunk.rank}</td>
        <td>
          <button className="link-button" onClick={() => setOpen(!open)} aria-expanded={open}>
            {chunk.book_title}
          </button>
          <div className="muted small">{chunk.breadcrumb.join(' › ')} · {pages(chunk.page_start, chunk.page_end)}
            {' · '}{chunk.unit_kind}{chunk.speaker_layer !== 'unknown' ? ` · ${SPEAKER_LABELS[chunk.speaker_layer] ?? chunk.speaker_layer}` : ''}
            {chunk.also_in?.length ? ` · +${chunk.also_in.length} bản khác` : ''}
            {chunk.expert_reviewed ? ' · có quy tắc đã duyệt' : ''}</div>
        </td>
        <td className="mono" title={`raw ${score(s.dense_raw, 4)} · hạng ${s.dense_rank ?? '—'}`}>{score(s.dense)}</td>
        <td className="mono" title={`raw ${score(s.sparse_raw, 2)} · hạng ${s.sparse_rank ?? '—'}`}>{score(s.sparse)}</td>
        <td className="mono">{score(s.fused)}</td>
        <td className="mono">{score(s.rerank)}</td>
        <td>{chunk.parent_handle ? <button className="cite" onClick={onParent}>[{chunk.parent_handle}]</button> : <span className="muted small">—</span>}</td>
        <td>
          <select aria-label="Đánh giá đoạn" value={label?.relevance ?? ''}
                  onChange={(e) => onLabel({ relevance: (e.target.value || null) as Relevance | null })}>
            <option value="">—</option>
            {RELEVANCE.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </td>
        <td>
          <input type="checkbox" aria-label="Có quy tắc đáng duyệt" checked={!!label?.suggest_rule}
                 onChange={(e) => onLabel({ suggest_rule: e.target.checked })} />
        </td>
      </tr>
      {open && (
        <tr className="judge-chunk-text">
          <td />
          <td colSpan={8}>
            <p className="small muted">{chunk.header}</p>
            <pre className="judge-pre">{chunk.text}</pre>
            {chunk.also_in?.length ? (
              <p className="small muted">Cũng có trong: {chunk.also_in.map((a) => String((a as Record<string, unknown>).book_title)).join('; ')}</p>
            ) : null}
            <details><summary className="small muted">Metadata</summary>
              <pre className="judge-pre small">{JSON.stringify(meta, null, 2)}</pre></details>
          </td>
        </tr>
      )}
    </>
  )
}
