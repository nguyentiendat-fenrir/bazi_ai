'use client'
// Users (docs/12): admins create accounts, change roles and disable sign-in. Changes use the
// user's ETag so two admins cannot overwrite each other; nobody can lock out the last admin.
import { useState } from 'react'
import type { FormEvent } from 'react'

import { api, call, type Schemas } from '@/api/client'
import { Dialog } from '@/components/Dialog'
import { ErasureDialog } from '@/components/ErasureDialog'
import { SettingsTabs } from '@/components/SettingsTabs'
import { Badge, ErrorState, Forbidden, FormError, Loading, PageHeader } from '@/components/ui'
import { ROLES, formatDateTime } from '@/lib/format'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type User = Schemas['UserDTO']
type Role = User['role']

function NewUser({ open, onClose, onSaved }: { open: boolean, onClose(): void, onSaved(): void }) {
  const [form, setForm] = useState<{ email: string, password: string, role: Role }>({ email: '', password: '', role: 'reader' })
  const [error, setError] = useState<unknown>(null)
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      await call(api.POST('/api/v1/users', { body: form }))
      setForm({ email: '', password: '', role: 'reader' })
      onSaved()
      onClose()
    } catch (caught) {
      setError(caught)
    }
  }
  return (
    <Dialog open={open} onClose={onClose} title="Người dùng mới">
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="nu-email">Email</label>
          <input id="nu-email" type="email" required autoComplete="off" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="nu-password">Mật khẩu tạm</label>
          <input id="nu-password" type="password" required minLength={12} autoComplete="new-password" value={form.password}
                 onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <p className="hint">Ít nhất 12 ký tự; gửi cho người dùng qua kênh riêng.</p>
        </div>
        <div className="field">
          <label htmlFor="nu-role">Vai trò</label>
          <select id="nu-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
            {(['reader', 'reviewer', 'admin'] as Role[]).map((r) => <option key={r} value={r}>{ROLES[r] ?? r}</option>)}
          </select>
        </div>
        <FormError error={error} />
        <div className="actions">
          <button type="button" className="button button-ghost" onClick={onClose}>Hủy</button>
          <button type="submit" className="button">Tạo tài khoản</button>
        </div>
      </form>
    </Dialog>
  )
}

export default function UsersPage() {
  const { can, user: me } = useSession()
  const admin = can('system:admin')
  const users = useQuery(admin ? 'users' : null, () => call(api.GET('/api/v1/users')))
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [erasing, setErasing] = useState<User | null>(null)
  if (!admin) return <Forbidden what="quản lý người dùng" />

  const patch = async (u: User, body: { role?: Role, enabled?: boolean }) => {
    setError(null)
    try {
      // The ETag of the user as it is now; a change by someone else since the list loaded fails with 412.
      const current = await api.GET('/api/v1/users/{user_id}', { params: { path: { user_id: u.id } } })
      if (current.data && current.data.data.updated_at !== u.updated_at) {
        users.reload()
        throw new Error('Người dùng vừa được người khác sửa; danh sách đã tải lại, hãy thử lại.')
      }
      await call(api.PATCH('/api/v1/users/{user_id}', {
        params: { path: { user_id: u.id }, header: { 'If-Match': current.response.headers.get('ETag') ?? '' } }, body }))
      users.reload()
    } catch (caught) {
      setError(caught)
    }
  }

  return (
    <>
      <title>Người dùng · Cài đặt</title>
      <PageHeader title="Cài đặt" actions={<button type="button" className="button" onClick={() => setCreating(true)}>Người dùng mới</button>} />
      <SettingsTabs />
      <FormError error={error} />
      {users.error ? <ErrorState error={users.error} retry={users.reload} /> : !users.data ? <Loading rows={3} /> : (
        <div className="table-wrap">
          <table>
            <caption className="visually-hidden">Người dùng</caption>
            <thead><tr><th scope="col">Email</th><th scope="col">Vai trò</th><th scope="col">Đăng nhập</th><th scope="col">Tạo lúc</th><th scope="col"><span className="visually-hidden">Thao tác</span></th></tr></thead>
            <tbody>
              {users.data.data.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}{u.id === me?.id && <> <Badge>bạn</Badge></>}</td>
                  <td>
                    <select aria-label={`Vai trò của ${u.email}`} value={u.role} disabled={u.id === me?.id}
                            onChange={(e) => void patch(u, { role: e.target.value as Role })}>
                      {(['reader', 'reviewer', 'admin'] as Role[]).map((r) => <option key={r} value={r}>{ROLES[r] ?? r}</option>)}
                    </select>
                  </td>
                  <td>
                    <label className="checkbox">
                      <input type="checkbox" checked={u.enabled} disabled={u.id === me?.id}
                             onChange={(e) => void patch(u, { enabled: e.target.checked })} />
                      <span>{u.enabled ? 'Được phép' : 'Đã khóa'}</span>
                    </label>
                  </td>
                  <td className="nowrap">{formatDateTime(u.created_at)}</td>
                  <td>{u.id !== me?.id && !u.email.endsWith('@invalid') && (
                    <button type="button" className="button button-ghost button-small" aria-label={`Xóa dữ liệu của ${u.email}`}
                            onClick={() => setErasing(u)}>Xóa dữ liệu…</button>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <NewUser open={creating} onClose={() => setCreating(false)} onSaved={users.reload} />
      {erasing && (
        <ErasureDialog open onClose={() => setErasing(null)} email={erasing.email} userId={erasing.id}
                       onDone={() => users.reload()} />
      )}
    </>
  )
}
