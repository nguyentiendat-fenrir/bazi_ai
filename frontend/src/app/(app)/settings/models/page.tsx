'use client'
// Model profiles (docs/09, docs/12): add, test and activate LLM/reranker profiles. API keys
// stay in the environment; a profile names an allowlisted variable, never the key itself.
// Fixture providers are for tests and are labelled so their scores are not read as benchmarks.
import { useState } from 'react'
import type { FormEvent } from 'react'

import { api, call, type Schemas } from '@/api/client'
import { Dialog } from '@/components/Dialog'
import { SettingsTabs } from '@/components/SettingsTabs'
import { Badge, Empty, ErrorState, Forbidden, FormError, Loading, Notice, PageHeader } from '@/components/ui'
import { formatDateTime } from '@/lib/format'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type Kind = 'llm' | 'embedding' | 'reranker'
type Result = Schemas['TestResult']

const KINDS: Record<Kind, string> = { llm: 'Mô hình ngôn ngữ', embedding: 'Embedding', reranker: 'Reranker' }
const PROVIDERS: Record<Kind, string[]> = {
  llm: ['openai_compatible', 'fixture-scripted'], embedding: ['openai_compatible', 'fixture-hashing'],
  reranker: ['openai_compatible', 'fixture-overlap'],
}

function NewProfile({ open, onClose, onSaved }: { open: boolean, onClose(): void, onSaved(): void }) {
  const [kind, setKind] = useState<'llm' | 'reranker'>('llm')
  const [form, setForm] = useState({ provider: 'openai_compatible', model_name: '', model_revision: '', base_url: '',
    timeout: '60', locality: 'local', secret_ref: '', daily_budget: '' })
  const [error, setError] = useState<unknown>(null)
  const set = (key: keyof typeof form, value: string) => setForm({ ...form, [key]: value })

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    const config: Record<string, unknown> = { locality: form.locality, timeout: Number(form.timeout) }
    if (form.base_url) config.base_url = form.base_url
    if (form.daily_budget) config.daily_budget = Number(form.daily_budget)
    try {
      await call(api.POST('/api/v1/model-profiles', { body: {
        kind, provider: form.provider, model_name: form.model_name, model_revision: form.model_revision,
        config, secret_ref: form.secret_ref || null } }))
      onSaved()
      onClose()
    } catch (caught) {
      setError(caught)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Profile mô hình mới">
      <form onSubmit={submit}>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="mp-kind">Loại</label>
            <select id="mp-kind" value={kind} onChange={(e) => { setKind(e.target.value as 'llm' | 'reranker'); set('provider', 'openai_compatible') }}>
              <option value="llm">{KINDS.llm}</option><option value="reranker">{KINDS.reranker}</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="mp-provider">Nhà cung cấp</label>
            <select id="mp-provider" value={form.provider} onChange={(e) => set('provider', e.target.value)}>
              {PROVIDERS[kind].map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="mp-model">Tên mô hình</label>
            <input id="mp-model" required value={form.model_name} onChange={(e) => set('model_name', e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="mp-revision">Phiên bản / checksum</label>
            <input id="mp-revision" required value={form.model_revision} onChange={(e) => set('model_revision', e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="mp-url">Địa chỉ API</label>
            <input id="mp-url" type="url" placeholder="http://llama:8080/v1" value={form.base_url} onChange={(e) => set('base_url', e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="mp-locality">Vị trí xử lý</label>
            <select id="mp-locality" value={form.locality} onChange={(e) => set('locality', e.target.value)}>
              <option value="local">Trong máy chủ của bạn</option><option value="external">Dịch vụ bên ngoài</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="mp-secret">Biến môi trường chứa khóa</label>
            <select id="mp-secret" value={form.secret_ref} onChange={(e) => set('secret_ref', e.target.value)}>
              <option value="">Không cần khóa</option><option value="LLM_API_KEY">LLM_API_KEY</option><option value="EMBEDDING_API_KEY">EMBEDDING_API_KEY</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="mp-timeout">Thời gian chờ (giây)</label>
            <input id="mp-timeout" type="number" min={1} max={600} value={form.timeout} onChange={(e) => set('timeout', e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="mp-budget">Trần chi phí mỗi ngày (USD, tùy chọn)</label>
            <input id="mp-budget" type="number" min={0} step="0.01" value={form.daily_budget} onChange={(e) => set('daily_budget', e.target.value)} />
          </div>
        </div>
        <p className="hint">Profile vừa tạo được dùng ngay cho loại của nó; chọn “Dùng” ở profile cũ để quay lại. Khóa API không nhập ở đây: đặt trong biến môi trường của máy chủ. Sách chỉ gửi ra dịch vụ bên ngoài khi phiên bản sách cho phép.</p>
        <FormError error={error} />
        <div className="actions">
          <button type="button" className="button button-ghost" onClick={onClose}>Hủy</button>
          <button type="submit" className="button">Tạo profile</button>
        </div>
      </form>
    </Dialog>
  )
}

export default function ModelsPage() {
  const { can } = useSession()
  const profiles = useQuery(can('system:admin') ? 'model-profiles' : null, () => call(api.GET('/api/v1/model-profiles')))
  const [creating, setCreating] = useState(false)
  const [results, setResults] = useState<Record<string, Result | { failed: unknown }>>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<unknown>(null)

  if (!can('system:admin')) return <Forbidden what="cấu hình mô hình" />

  const test = async (id: string, kind: string) => {
    setBusy(id)
    try {
      const done = await call(api.POST('/api/v1/model-profiles/{profile_id}/test', {
        params: { path: { profile_id: id } }, body: { check_json: kind === 'llm', max_tokens: 32 } }))
      setResults({ ...results, [id]: done.data })
    } catch (caught) {
      setResults({ ...results, [id]: { failed: caught } })
    } finally {
      setBusy(null)
    }
  }
  const activate = async (id: string) => {
    setError(null)
    try {
      await call(api.POST('/api/v1/model-profiles/{profile_id}/activate', { params: { path: { profile_id: id } } }))
      profiles.reload()
    } catch (caught) {
      setError(caught)
    }
  }

  const rows = profiles.data?.data ?? []
  return (
    <>
      <title>Mô hình AI · Cài đặt</title>
      <PageHeader title="Cài đặt" actions={<button type="button" className="button" onClick={() => setCreating(true)}>Profile mới</button>} />
      <SettingsTabs />
      <FormError error={error} />
      {profiles.error ? <ErrorState error={profiles.error} retry={profiles.reload} />
        : !profiles.data ? <Loading rows={3} />
        : rows.length === 0 ? (
          <Empty title="Chưa có profile mô hình" action={<button type="button" className="button" onClick={() => setCreating(true)}>Profile mới</button>}>
            Không có mô hình thì hỏi đáp vẫn trả lời bằng đoạn trích nguồn, không có diễn giải của AI.
          </Empty>
        ) : (
          (['llm', 'reranker', 'embedding'] as Kind[]).map((kind) => {
            const ofKind = rows.filter((p) => p.kind === kind)
            if (ofKind.length === 0) return null
            return (
              <section key={kind} className="panel">
                <h2>{KINDS[kind]}</h2>
                {kind === 'embedding' && <Notice tone="info">Đổi embedding cần dựng lại toàn bộ vector của kho, nên không kích hoạt ở đây.</Notice>}
                <div className="table-wrap">
                  <table>
                    <caption className="visually-hidden">Profile {KINDS[kind]}</caption>
                    <thead><tr><th scope="col">Mô hình</th><th scope="col">Nhà cung cấp</th><th scope="col">Vị trí</th><th scope="col">Khóa</th>
                      <th scope="col">Trạng thái</th><th scope="col">Kiểm tra</th><th scope="col"><span className="visually-hidden">Thao tác</span></th></tr></thead>
                    <tbody>
                      {ofKind.map((p) => {
                        const result = results[p.id]
                        return (
                          <tr key={p.id}>
                            <td>{p.model_name} <span className="muted small">{p.model_revision}</span>
                              <br /><span className="muted small">{formatDateTime(p.created_at)}</span></td>
                            <td>{p.provider}{p.is_fixture && <> <Badge tone="warning">fixture kiểm thử</Badge></>}</td>
                            <td>{String((p.config as Record<string, unknown>).locality ?? 'external') === 'local' ? 'Trong máy chủ' : 'Bên ngoài'}</td>
                            <td>{p.secret_ref ? <code>{p.secret_ref}</code> : <span className="muted">không</span>}</td>
                            <td>{p.active ? <Badge tone="ok">Đang dùng</Badge> : p.enabled ? <Badge>Bật</Badge> : <Badge>Tắt</Badge>}</td>
                            <td aria-live="polite">
                              {result === undefined ? <span className="muted">—</span>
                                : 'failed' in result ? <FormError error={result.failed} />
                                : <span className="small">{result.latency_ms} ms{result.json_ok === false ? ' · JSON lỗi' : result.json_ok ? ' · JSON đạt' : ''}{result.is_fixture ? ' · fixture' : ''}</span>}
                            </td>
                            <td>
                              <div className="actions">
                                <button type="button" className="button button-secondary button-small" disabled={busy === p.id}
                                        aria-label={`Thử ${p.model_name}`} onClick={() => void test(p.id, p.kind)}>{busy === p.id ? 'Đang thử…' : 'Thử'}</button>
                                {!p.active && kind !== 'embedding' && (
                                  <button type="button" className="button button-small" aria-label={`Dùng ${p.model_name}`}
                                          onClick={() => void activate(p.id)}>Dùng</button>
                                )}
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </section>
            )
          })
        )}
      <NewProfile open={creating} onClose={() => setCreating(false)} onSaved={profiles.reload} />
    </>
  )
}
