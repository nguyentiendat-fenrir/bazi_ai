'use client'
// Who may read a book (docs/12 · Quyền nội dung sách): readers see a book only when it is
// shared with them, by role or one by one. Reviewers see the list; admins change it. Every
// change bumps the book revision (If-Match) and hides cached results at once.
import { useState } from 'react'

import { api, call, ifMatch, type Schemas } from '@/api/client'
import { ErrorState, FormError, Loading, Notice } from '@/components/ui'
import { useQuery } from '@/lib/query'
import { useSession } from '@/lib/session'

type Grant = Schemas['Grant']

export function BookAccessPanel({ bookId, revision, onChanged }: {
  bookId: string, revision: number, onChanged(): void,
}) {
  const { can } = useSession()
  const admin = can('system:admin')
  const grants = useQuery(`book-access:${bookId}:${revision}`, () => call(api.GET('/api/v1/books/{book_id}/access', {
    params: { path: { book_id: bookId } } })))
  const users = useQuery(admin ? 'access:users' : null, () => call(api.GET('/api/v1/users')))
  const [adding, setAdding] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [saved, setSaved] = useState(false)

  if (grants.error) return <ErrorState error={grants.error} retry={grants.reload} />
  if (!grants.data) return <Loading rows={2} />
  const list = grants.data.data
  const everyone = list.some((g) => g.role_scope === 'reader' && g.permission === 'read')
  const people = list.filter((g) => g.user_id)
  const emailOf = (id: string | null | undefined) => users.data?.data.find((u) => u.id === id)?.email ?? id?.slice(0, 8)

  const save = async (next: Grant[]) => {
    setError(null)
    setSaved(false)
    try {
      await call(api.PATCH('/api/v1/books/{book_id}/access', {
        params: { path: { book_id: bookId }, header: { 'If-Match': ifMatch(revision) } },
        body: { grants: next.map((g) => ({ permission: g.permission, role_scope: g.role_scope ?? null, user_id: g.user_id ?? null })) } }))
      setSaved(true)
      onChanged()
    } catch (caught) {
      setError(caught)
    }
  }
  const toggleEveryone = (on: boolean) => save(on
    ? [...list, { permission: 'read', role_scope: 'reader', user_id: null }]
    : list.filter((g) => !(g.role_scope === 'reader' && g.permission === 'read')))

  return (
    <div className="access">
      <label className="checkbox">
        <input type="checkbox" checked={everyone} disabled={!admin} onChange={(e) => void toggleEveryone(e.target.checked)} />
        <span>Mọi người đọc đều xem được sách này</span>
      </label>
      {people.length > 0 && (
        <ul className="plain-list" aria-label="Người được chia sẻ riêng">
          {people.map((g) => (
            <li key={`${g.user_id}:${g.permission}`}>
              {emailOf(g.user_id)} <span className="muted small">({g.permission})</span>
              {admin && (
                <button type="button" className="button button-ghost button-small" aria-label={`Bỏ chia sẻ với ${emailOf(g.user_id)}`}
                        onClick={() => void save(list.filter((x) => x !== g))}>Bỏ</button>
              )}
            </li>
          ))}
        </ul>
      )}
      {admin ? (
        <div className="inline-form">
          <div className="field">
            <label htmlFor="share-user">Chia sẻ riêng với</label>
            <select id="share-user" value={adding} onChange={(e) => setAdding(e.target.value)}>
              <option value="">Chọn người…</option>
              {users.data?.data.filter((u) => u.enabled && u.role === 'reader' && !people.some((g) => g.user_id === u.id))
                .map((u) => <option key={u.id} value={u.id}>{u.email}</option>)}
            </select>
          </div>
          <button type="button" className="button button-secondary" disabled={!adding}
                  onClick={() => { void save([...list, { permission: 'read', role_scope: null, user_id: adding }]); setAdding('') }}>Chia sẻ</button>
        </div>
      ) : <p className="hint">Chỉ quản trị viên đổi được quyền xem.</p>}
      {saved && <Notice tone="ok">Đã lưu quyền xem; kết quả tra cứu cũ được làm mới ngay.</Notice>}
      <FormError error={error} />
      <p className="hint">Người duyệt và quản trị luôn xem được mọi sách. Sách quyền “hạn chế” không vào kho tra cứu dù được chia sẻ.</p>
    </div>
  )
}
