'use client'
// System settings, runtime configuration and spend (docs/12). Values are validated per key on
// the server; runtime facts are read-only (they come from the environment).
import { useState } from 'react'
import type { FormEvent } from 'react'

import { api, call, ifMatch, type Schemas } from '@/api/client'
import { SettingsTabs } from '@/components/SettingsTabs'
import { UsageTable } from '@/components/UsageTable'
import { Badge, ErrorState, Facts, Forbidden, FormError, Loading, PageHeader } from '@/components/ui'
import { RIGHTS, formatDateTime } from '@/lib/format'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type Setting = Schemas['SettingDTO']
type Kind = 'number' | 'integer' | 'bool' | 'rights'

const SYSTEM: { key: string, label: string, kind: Kind, hint: string }[] = [
  { key: 'budget.daily_limit_usd', label: 'Trần chi phí mô hình mỗi ngày (USD)', kind: 'number', hint: 'Tính tổng mọi người; vượt trần thì hỏi đáp dùng câu trả lời không có AI.' },
  { key: 'retention.log_days', label: 'Giữ nhật ký (ngày)', kind: 'integer', hint: '1–3650 ngày.' },
  { key: 'library.default_rights_status', label: 'Quyền sử dụng mặc định khi tải sách', kind: 'rights', hint: 'Người tải vẫn chọn lại cho từng đợt.' },
  { key: 'library.external_processing_default', label: 'Mặc định cho phép xử lý sách bằng dịch vụ bên ngoài', kind: 'bool', hint: 'Nên tắt nếu sách có bản quyền riêng.' },
]

function SettingRow({ spec, current, onSaved }: { spec: typeof SYSTEM[number], current: Setting | undefined, onSaved(): void }) {
  const initial = current?.value
  const [value, setValue] = useState<string>(initial === undefined || initial === null ? '' : String(initial))
  const [error, setError] = useState<unknown>(null)
  const [saved, setSaved] = useState(false)
  const id = `sys-${spec.key}`

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setSaved(false)
    const parsed = spec.kind === 'number' ? Number(value) : spec.kind === 'integer' ? Number.parseInt(value, 10)
      : spec.kind === 'bool' ? value === 'true' : value
    try {
      await call(api.PATCH('/api/v1/settings', { params: { header: { 'If-Match': ifMatch(current?.revision ?? 0) } },
        body: { scope: 'system', key: spec.key, value: parsed } }))
      setSaved(true)
      onSaved()
    } catch (caught) {
      setError(caught)
    }
  }

  return (
    <form className="setting-row" onSubmit={submit}>
      <div className="field grow">
        <label htmlFor={id}>{spec.label}</label>
        {spec.kind === 'bool' ? (
          <select id={id} value={value} onChange={(e) => setValue(e.target.value)}>
            <option value="">Chưa đặt</option><option value="true">Có</option><option value="false">Không</option>
          </select>
        ) : spec.kind === 'rights' ? (
          <select id={id} value={value} onChange={(e) => setValue(e.target.value)}>
            <option value="">Chưa đặt</option>
            {Object.entries(RIGHTS).map(([k, text]) => <option key={k} value={k}>{text}</option>)}
          </select>
        ) : (
          <input id={id} type="number" min={spec.kind === 'integer' ? 1 : 0} step={spec.kind === 'integer' ? 1 : 0.01}
                 value={value} onChange={(e) => setValue(e.target.value)} />
        )}
        <p className="hint">{spec.hint}{current ? ` Sửa lần cuối ${formatDateTime(current.updated_at)}.` : ''}</p>
        <FormError error={error} />
      </div>
      <div className="actions">
        <button type="submit" className="button button-secondary" disabled={value === '' || value === String(initial ?? '')}
                aria-label={`Lưu ${spec.label}`}>Lưu</button>
        {saved && <span className="hint" role="status">Đã lưu.</span>}
      </div>
    </form>
  )
}

export default function SystemPage() {
  const { can } = useSession()
  const admin = can('system:admin')
  const view = useQuery(admin ? 'settings' : null, () => call(api.GET('/api/v1/settings')))
  const usage = useQuery(admin ? 'usage:all' : null, () => call(api.GET('/api/v1/usage')))
  if (!admin) return <Forbidden what="cài đặt hệ thống" />
  const runtime = view.data?.data.runtime

  return (
    <>
      <title>Hệ thống · Cài đặt</title>
      <PageHeader title="Cài đặt" />
      <SettingsTabs />
      <div className="grid">
        <section className="panel">
          <h2>Cấu hình chạy</h2>
          {view.error ? <ErrorState error={view.error} retry={view.reload} /> : !runtime ? <Loading rows={3} /> : (
            <Facts items={[
              ['Môi trường', runtime.app_env],
              ['Lưu tệp', runtime.storage_backend],
              ['Mô hình ngôn ngữ', runtime.llm_configured ? <Badge tone="ok">{runtime.llm_provider}</Badge> : <Badge tone="warning">chưa cấu hình</Badge>],
              ['Embedding', runtime.embedding_configured ? <Badge tone="ok">đã cấu hình</Badge> : <Badge tone="warning">chưa cấu hình</Badge>],
            ]} />
          )}
          <p className="hint">Đặt trong biến môi trường của máy chủ; khóa bí mật không bao giờ hiển thị ở đây.</p>
        </section>
        <section className="panel">
          <h2>Ngân sách hôm nay</h2>
          {usage.error ? <ErrorState error={usage.error} retry={usage.reload} /> : !usage.data ? <Loading rows={2} />
            : usage.data.data.budgets.length === 0 ? <p className="muted">Chưa đặt trần chi phí cho profile nào.</p> : (
              <ul className="plain-list">
                {usage.data.data.budgets.map((b) => {
                  const ratio = b.daily_budget > 0 ? b.spent_today / b.daily_budget : 0
                  return (
                    <li key={b.profile_id}>
                      <code>{b.profile_id.slice(0, 8)}</code>: {b.spent_today.toFixed(4)} / {b.daily_budget} {b.currency}
                      {' '}<Badge tone={ratio >= 1 ? 'danger' : ratio >= 0.8 ? 'warning' : 'ok'}>{Math.round(ratio * 100)}%</Badge>
                    </li>
                  )
                })}
              </ul>
            )}
        </section>
      </div>
      <section className="panel">
        <h2>Cài đặt hệ thống</h2>
        {view.data && SYSTEM.map((spec) => (
          <SettingRow key={spec.key} spec={spec} current={view.data!.data.settings.find((s) => s.scope === 'system' && s.key === spec.key)}
                      onSaved={view.reload} />
        ))}
      </section>
      <section className="panel">
        <h2>Mức dùng mô hình của mọi người</h2>
        {usage.data && (
          <>
            <p className="muted small">Từ {usage.data.data.from} đến {usage.data.data.to}; chỉ tổng theo profile, không có nội dung câu hỏi.</p>
            <UsageTable rows={usage.data.data.all ?? []} caption="Mức dùng toàn hệ thống" />
          </>
        )}
      </section>
    </>
  )
}
