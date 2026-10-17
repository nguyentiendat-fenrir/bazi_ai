'use client'
// Small shared pieces: badges, headers and the empty / loading / error / forbidden states
// every screen must show (docs/11).
import Link from 'next/link'
import type { ReactNode } from 'react'

import { ApiError, describe } from '@/api/problem'
import { label, type Tone } from '@/lib/format'

export function Badge({ tone = 'neutral', children }: { tone?: Tone, children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

/** A state value rendered with its Vietnamese label and tone. */
export function StateBadge({ labels, value }: {
  labels: Record<string, [string, Tone]>, value: string | null | undefined,
}) {
  const [text, tone] = label(labels, value)
  return <Badge tone={tone}>{text}</Badge>
}

export function PageHeader({ title, description, actions, back }: {
  title: ReactNode, description?: ReactNode, actions?: ReactNode,
  back?: { href: string, label: string },
}) {
  return (
    <header className="page-header">
      <div>
        {back && <Link className="back-link" href={back.href}>← {back.label}</Link>}
        <h1>{title}</h1>
        {description && <p className="muted">{description}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </header>
  )
}

export function Loading({ label: text = 'Đang tải…', rows = 3 }: { label?: string, rows?: number }) {
  return (
    <div className="state" role="status" aria-live="polite" aria-busy="true">
      <span className="visually-hidden">{text}</span>
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" />)}
    </div>
  )
}

export function Empty({ title, children, action }: {
  title: string, children?: ReactNode, action?: ReactNode,
}) {
  return (
    <div className="state state-empty">
      <h2>{title}</h2>
      {children && <p className="muted">{children}</p>}
      {action}
    </div>
  )
}

export function Forbidden({ what = 'màn hình này' }: { what?: string }) {
  return (
    <div className="state state-forbidden" role="alert">
      <h2>Không đủ quyền</h2>
      <p className="muted">Tài khoản của bạn không được xem {what}. Liên hệ quản trị nếu cần quyền.</p>
    </div>
  )
}

export function ErrorState({ error, retry }: { error: unknown, retry?: () => void }) {
  if (error instanceof ApiError && error.status === 403 && error.code === 'FORBIDDEN') {
    return <Forbidden />
  }
  const requestId = error instanceof ApiError ? error.requestId : null
  return (
    <div className="state state-error" role="alert">
      <h2>{error instanceof ApiError && error.status === 404 ? 'Không tìm thấy' : 'Không tải được dữ liệu'}</h2>
      <p>{describe(error)}</p>
      {requestId && <p className="muted small">Mã yêu cầu: <code>{requestId}</code></p>}
      {retry && <button type="button" className="button" onClick={retry}>Thử lại</button>}
    </div>
  )
}

/** Inline result of a mutation: error with field hints, or nothing. */
export function FormError({ error }: { error: unknown }) {
  if (!error) return null
  return (
    <div className="form-error" role="alert">
      <p>{describe(error)}</p>
      {error instanceof ApiError && error.fieldErrors.length > 0 && (
        <ul>
          {error.fieldErrors.map((f) => <li key={f.path}><code>{f.path}</code>: {f.message}</li>)}
        </ul>
      )}
      {error instanceof ApiError && error.requestId && (
        <p className="muted small">Mã yêu cầu: <code>{error.requestId}</code></p>
      )}
    </div>
  )
}

export function Notice({ tone = 'info', children }: { tone?: Tone, children: ReactNode }) {
  return <div className={`notice notice-${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>{children}</div>
}

/** Key/value list for detail screens. */
export function Facts({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="facts">
      {items.map(([term, value]) => (
        <div key={term}><dt>{term}</dt><dd>{value}</dd></div>
      ))}
    </dl>
  )
}
