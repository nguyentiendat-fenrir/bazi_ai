'use client'
// Chat (docs/11 /chat): three modes over the user's conversations. Progress streams over
// SSE; only validated claims and the canonical answer are shown, never raw model text.
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { api, call, idempotencyKey, ifMatch, type Schemas } from '@/api/client'
import { AnswerView, type AnswerClaim, type AnswerData } from '@/components/AnswerView'
import { Dialog } from '@/components/Dialog'
import { Empty, ErrorState, FormError, Loading, Notice } from '@/components/ui'
import { pairLabel } from '@/lib/bazi'
import { formatDateTime } from '@/lib/format'
import { usePagedList, useQuery } from '@/lib/query'

type Mode = 'research' | 'chart_analysis' | 'comparison'
type Conversation = Schemas['ConversationDTO']
type Message = Schemas['MessageDTO']

const MODES: Record<Mode, string> = {
  research: 'Tra cứu', chart_analysis: 'Luận lá số', comparison: 'So sánh trường phái',
}
const STEPS: Record<string, string> = {
  'run.started': 'Bắt đầu', get_chart_facts: 'Đọc lá số', evaluate_rules: 'Chạy quy tắc đã duyệt',
  search_knowledge: 'Tìm trong sách', 'retrieval.ready': 'Đã có đoạn nguồn',
  'provider.waiting': 'Chờ mô hình', 'answer.claim': 'Đã kiểm một nhận định',
}

interface Live {
  runId: string
  steps: string[]
  claims: AnswerClaim[]
  ended: boolean
}

function ContextBar({ conversation, onSaved }: { conversation: Conversation, onSaved(c: Conversation): void }) {
  const ctx = conversation.context as Record<string, unknown>
  const [mode, setMode] = useState<Mode>((ctx.mode as Mode) ?? 'research')
  const [chartId, setChartId] = useState<string>((ctx.chart_id as string) ?? '')
  const [schools, setSchools] = useState<string[]>((ctx.school_ids as string[]) ?? [])
  const [methodId, setMethodId] = useState<string>(((ctx.method_ids as string[]) ?? [])[0] ?? '')
  const [error, setError] = useState<unknown>(null)
  const charts = useQuery('chat:charts', () => call(api.GET('/api/v1/charts', { params: { query: { limit: 100 } } })))
  const schoolList = useQuery('chat:schools', () => call(api.GET('/api/v1/schools')))
  const methods = useQuery('chat:methods', () => call(api.GET('/api/v1/methods', { params: { query: { state: 'approved' } } })))
  const dirty = mode !== (ctx.mode ?? 'research') || chartId !== (ctx.chart_id ?? '')
    || schools.join() !== ((ctx.school_ids as string[]) ?? []).join() || methodId !== (((ctx.method_ids as string[]) ?? [])[0] ?? '')

  const save = async () => {
    setError(null)
    try {
      const saved = await call(api.PATCH('/api/v1/conversations/{conversation_id}', {
        params: { path: { conversation_id: conversation.id }, header: { 'If-Match': ifMatch(conversation.revision) } },
        body: { context: { mode, chart_id: chartId || null, school_ids: schools, method_ids: methodId ? [methodId] : [],
          book_ids: (ctx.book_ids as string[]) ?? [] } },
      }))
      onSaved(saved.data)
    } catch (caught) {
      setError(caught)
    }
  }

  return (
    <div className="context-bar" role="group" aria-label="Ngữ cảnh hội thoại">
      <div className="field">
        <label htmlFor="ctx-mode">Chế độ</label>
        <select id="ctx-mode" value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
          {Object.entries(MODES).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="ctx-chart">Lá số</label>
        <select id="ctx-chart" value={chartId} onChange={(e) => setChartId(e.target.value)}>
          <option value="">Không dùng lá số</option>
          {charts.data?.data.map((c) => (
            <option key={c.id} value={c.id}>{c.profile_label ?? 'Lá số'} · {pairLabel(c.pillars.day)} ({formatDateTime(c.created_at)})</option>
          ))}
        </select>
      </div>
      <fieldset className="field">
        <legend className="label">Trường phái</legend>
        <div className="choices">
          {schoolList.data?.data.map((s) => (
            <label key={s.id} className="checkbox">
              <input type="checkbox" checked={schools.includes(s.id)}
                     onChange={(e) => setSchools(e.target.checked ? [...schools, s.id] : schools.filter((x) => x !== s.id))} />
              <span>{s.label}</span>
            </label>
          ))}
        </div>
      </fieldset>
      {mode === 'chart_analysis' && (
        <div className="field">
          <label htmlFor="ctx-method">Phương pháp (để chạy quy tắc)</label>
          <select id="ctx-method" value={methodId} onChange={(e) => setMethodId(e.target.value)}>
            <option value="">Chưa chọn</option>
            {methods.data?.data.filter((m) => schools.includes(m.school_id)).map((m) => (
              <option key={m.id} value={m.id}>{m.school_key} · {m.key}</option>
            ))}
          </select>
        </div>
      )}
      {dirty && <button type="button" className="button button-secondary" onClick={() => void save()}>Áp dụng ngữ cảnh</button>}
      <FormError error={error} />
    </div>
  )
}

function Thread({ conversationId, onTitle }: { conversationId: string, onTitle(): void }) {
  const conversation = useQuery(`conversation:${conversationId}`, () =>
    call(api.GET('/api/v1/conversations/{conversation_id}', { params: { path: { conversation_id: conversationId } } })))
  const messages = useQuery(`conversation:${conversationId}:messages`, () =>
    call(api.GET('/api/v1/conversations/{conversation_id}/messages', { params: { path: { conversation_id: conversationId } } })))
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [live, setLive] = useState<Live | null>(null)
  const source = useRef<EventSource | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  const follow = useCallback((runId: string) => {
    source.current?.close()
    setLive({ runId, steps: [], claims: [], ended: false })
    const events = new EventSource(`/api/v1/runs/${runId}/events`)
    source.current = events
    const add = (step: string) => setLive((l) => l && { ...l, steps: [...l.steps, step] })
    events.addEventListener('run.started', () => add(STEPS['run.started']))
    events.addEventListener('tool.started', (e) => add(STEPS[JSON.parse((e as MessageEvent).data).tool] ?? 'Công cụ'))
    events.addEventListener('retrieval.ready', (e) => {
      const data = JSON.parse((e as MessageEvent).data)
      add(`${STEPS['retrieval.ready']}: ${data.groups}`)
    })
    events.addEventListener('provider.waiting', () => add(STEPS['provider.waiting']))
    events.addEventListener('answer.claim', (e) => {
      const claim = JSON.parse((e as MessageEvent).data).claim as AnswerClaim
      setLive((l) => l && { ...l, claims: [...l.claims, claim] })
    })
    const end = () => {
      events.close()
      setLive((l) => l && { ...l, ended: true })
      messages.reload()
      onTitle()
    }
    events.addEventListener('answer.completed', end)
    events.addEventListener('run.failed', end)
    events.addEventListener('run.cancelled', end)
  }, [messages, onTitle])

  useEffect(() => () => source.current?.close(), [])
  // Resume an answer still running when the page opens.
  useEffect(() => {
    const pending = messages.data?.data.find((m) => m.role === 'assistant' && m.status === 'pending')
    if (pending?.run_id && (!live || live.runId !== pending.run_id)) follow(pending.run_id)
  }, [messages.data, follow, live])
  useEffect(() => { bottom.current?.scrollIntoView({ block: 'end' }) }, [messages.data, live])

  const send = async (event?: FormEvent) => {
    event?.preventDefault()
    if (!draft.trim()) return
    setError(null)
    try {
      const posted = await call(api.POST('/api/v1/conversations/{conversation_id}/messages', {
        params: { path: { conversation_id: conversationId }, header: { 'Idempotency-Key': idempotencyKey() } }, body: { content: draft.trim() } }))
      setDraft('')
      messages.reload()
      follow(posted.data.run.id)
    } catch (caught) {
      setError(caught)
    }
  }

  const cancel = async () => {
    if (!live) return
    await call(api.POST('/api/v1/runs/{run_id}/cancel', { params: { path: { run_id: live.runId } } }))
  }

  if (conversation.error) return <ErrorState error={conversation.error} retry={conversation.reload} />
  if (!conversation.data || !messages.data) return <Loading rows={5} />
  const running = !!live && !live.ended
  return (
    <div className="thread">
      <ContextBar conversation={conversation.data.data}
                  onSaved={(c) => conversation.replace({ ...conversation.data!, data: c })} />
      <ol className="messages" aria-live="polite">
        {messages.data.data.map((m: Message) => (
          <li key={m.id} className={`message message-${m.role}`}>
            {m.role === 'user' ? <p>{m.content}</p>
              : m.status === 'completed' && m.answer ? <AnswerView answer={m.answer as unknown as AnswerData} onFollowUp={setDraft} />
              : m.status === 'pending' ? (
                <div className="progress">
                  <p className="muted">Đang trả lời… {live?.steps.at(-1) ?? ''}</p>
                  {live && live.claims.length > 0 && (
                    <AnswerView answer={{ status: 'partial', mode: '', summary: 'Các nhận định đã kiểm nguồn:', claims: live.claims }} />
                  )}
                </div>
              ) : <p className="muted">{m.status === 'cancelled' ? 'Đã hủy câu trả lời.' : 'Không trả lời được; thử lại.'}</p>}
          </li>
        ))}
      </ol>
      <div ref={bottom} />
      <form className="composer" onSubmit={send}>
        <label htmlFor="composer" className="visually-hidden">Câu hỏi</label>
        <textarea id="composer" rows={3} maxLength={4000} value={draft} placeholder="Hỏi về sách, khái niệm hoặc lá số…"
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }} />
        <div className="actions">
          {running ? <button type="button" className="button button-secondary" onClick={() => void cancel()}>Dừng</button>
            : <button type="submit" className="button" disabled={!draft.trim()}>Gửi</button>}
        </div>
        <FormError error={error} />
      </form>
    </div>
  )
}

function ChatScreen() {
  const router = useRouter()
  const params = useSearchParams()
  const selected = params.get('c')
  const chartParam = params.get('chart')
  const [query, setQuery] = useState('')
  const [term, setTerm] = useState('')
  const [deleting, setDeleting] = useState<Conversation | null>(null)
  const [error, setError] = useState<unknown>(null)
  useEffect(() => {
    const timer = setTimeout(() => setTerm(query.trim()), 300)
    return () => clearTimeout(timer)
  }, [query])
  const load = useCallback((cursor: string | null) => call(api.GET('/api/v1/conversations', {
    params: { query: { q: term || undefined, limit: 30, cursor } } })), [term])
  const list = usePagedList(`conversations:${term}`, load)

  const create = useCallback(async (chart?: string) => {
    setError(null)
    try {
      const made = await call(api.POST('/api/v1/conversations', { body: { title: '', context: {
        mode: chart ? 'chart_analysis' : 'research', chart_id: chart ?? null, school_ids: [], method_ids: [], book_ids: [] } } }))
      list.reload()
      router.replace(`/chat?c=${made.data.id}`)
    } catch (caught) {
      setError(caught)
    }
  }, [list, router])

  // Arriving from a chart page: open a chart conversation for it once.
  const started = useRef(false)
  useEffect(() => {
    if (chartParam && !selected && !started.current) {
      started.current = true
      void create(chartParam)
    }
  }, [chartParam, selected, create])

  const remove = async () => {
    if (!deleting) return
    await call(api.DELETE('/api/v1/conversations/{conversation_id}', { params: { path: { conversation_id: deleting.id } } }))
    setDeleting(null)
    list.reload()
    if (selected === deleting.id) router.replace('/chat')
  }

  return (
    <div className="chat">
      <aside className="chat-list" aria-label="Hội thoại">
        <button type="button" className="button" onClick={() => void create()}>Hội thoại mới</button>
        <div className="field">
          <label htmlFor="chat-search">Tìm hội thoại</label>
          <input id="chat-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        {list.loading ? <Loading rows={3} /> : list.items.length === 0 ? (
          <p className="muted small">{term ? 'Không có hội thoại khớp.' : 'Chưa có hội thoại.'}</p>
        ) : (
          <ul className="plain-list">
            {list.items.map((c) => (
              <li key={c.id} className={c.id === selected ? 'selected' : undefined}>
                <Link href={`/chat?c=${c.id}`} aria-current={c.id === selected ? 'page' : undefined}>{c.title || 'Hội thoại mới'}</Link>
                <button type="button" className="button button-ghost button-small" aria-label={`Xóa ${c.title || 'hội thoại'}`}
                        onClick={() => setDeleting(c)}>✕</button>
              </li>
            ))}
          </ul>
        )}
        <FormError error={error} />
      </aside>
      <section className="chat-main">
        {selected ? <Thread key={selected} conversationId={selected} onTitle={list.reload} /> : (
          <Empty title="Hỏi đáp Bát Tự" action={<button type="button" className="button" onClick={() => void create()}>Bắt đầu</button>}>
            Tra cứu sách có dẫn nguồn, luận lá số bằng quy tắc đã duyệt, hoặc so sánh các trường phái.
          </Empty>
        )}
        <Notice tone="info">Câu trả lời chỉ hiện sau khi kiểm nguồn; diễn giải về sức khỏe, tiền bạc, tương lai là theo sách và có điều kiện, không phải lời khuyên.</Notice>
      </section>
      <Dialog open={!!deleting} onClose={() => setDeleting(null)} title="Xóa hội thoại?"
              footer={<>
                <button type="button" className="button button-ghost" onClick={() => setDeleting(null)}>Không</button>
                <button type="button" className="button button-danger" onClick={() => void remove()}>Xóa hội thoại</button>
              </>}>
        <p>“{deleting?.title || 'Hội thoại mới'}”: mọi tin nhắn, nhận định và trích dẫn bị xóa; câu trả lời đang chạy bị hủy.</p>
      </Dialog>
    </div>
  )
}

export default function ChatPage() {
  return (
    <>
      <title>Hỏi đáp · Kho Bát Tự</title>
      <Suspense fallback={<Loading rows={5} />}><ChatScreen /></Suspense>
    </>
  )
}
