'use client'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { ApiError, describe } from '@/api/problem'
import { safeNext } from '@/lib/format'
import { useSession } from '@/lib/session'

function nextPath(): string {
  if (typeof window === 'undefined') return '/'
  return safeNext(new URLSearchParams(window.location.search).get('next'))
}

export default function LoginPage() {
  const router = useRouter()
  const { status, reason, signIn } = useSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (status === 'signed-in') router.replace(nextPath())
  }, [status, router])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await signIn(email, password)
    } catch (caught) {
      setError(caught)
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  // A session that ended elsewhere (expired cookie, missing CSRF) explains itself once.
  const ended = !error && reason && (reason.status === 401 || reason.code === 'CSRF_FAILED')
  const retryAfter = error instanceof ApiError && error.code === 'RATE_LIMITED' ? error.retryAfter : null

  return (
    <div className="login">
      <title>Đăng nhập · Kho Bát Tự</title>
      <form className="login-card" onSubmit={submit} noValidate>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">八</span>
          <span className="brand-name">Kho Bát Tự</span>
        </div>
        <h1>Đăng nhập</h1>
        <p className="muted">Tài khoản do quản trị tạo; không có đăng ký công khai.</p>
        {ended && <div className="notice notice-warning" role="status">Phiên trước đã kết thúc. Hãy đăng nhập lại.</div>}
        {status === 'unreachable' && (
          <div className="notice notice-danger" role="alert">{describe(reason)}</div>
        )}
        {error ? (
          <div className="form-error" role="alert">
            <p>{error instanceof ApiError && error.code === 'AUTH_REQUIRED'
              ? 'Email hoặc mật khẩu không đúng, hoặc tài khoản đã bị khóa.' : describe(error)}</p>
            {retryAfter && <p className="small">Thử lại sau khoảng {Math.ceil(retryAfter / 60)} phút.</p>}
          </div>
        ) : null}
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username" required value={email}
                 onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="password">Mật khẩu</label>
          <input id="password" type="password" autoComplete="current-password" required
                 value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <button className="button" type="submit" disabled={busy || !email || !password}>
          {busy ? 'Đang đăng nhập…' : 'Đăng nhập'}
        </button>
      </form>
    </div>
  )
}
