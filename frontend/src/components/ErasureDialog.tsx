'use client'
// Erasing a person's private data (docs/12 · Deletion): typed email as confirmation, the
// person's own password when they erase themselves, an explicit choice to delete the account.
import { useState } from 'react'

import { api, call } from '@/api/client'
import { Dialog } from '@/components/Dialog'
import { FormError, Notice } from '@/components/ui'

export interface ErasureOutcome { account_deleted: boolean, counts: Record<string, number> }

export function ErasureDialog({ open, onClose, email, userId, onDone }: {
  open: boolean, onClose(): void, email: string,
  /** Another person's id (admin); omitted when the signed-in person erases their own data. */
  userId?: string
  onDone(outcome: ErasureOutcome): void
}) {
  const [confirm, setConfirm] = useState('')
  const [password, setPassword] = useState('')
  const [account, setAccount] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const self = userId === undefined

  const close = () => {
    setConfirm('')
    setPassword('')
    setAccount(false)
    setError(null)
    onClose()
  }
  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const done = self
        ? await call(api.POST('/api/v1/auth/erasure', { body: { confirm, password, delete_account: account } }))
        : await call(api.POST('/api/v1/users/{user_id}/erasure', {
          params: { path: { user_id: userId } }, body: { confirm, delete_account: account } }))
      close()
      onDone(done.data)
    } catch (caught) {
      setError(caught)
    } finally {
      setBusy(false)
    }
  }

  const ready = confirm.trim().toLowerCase() === email.toLowerCase() && (!self || password.length > 0)
  return (
    <Dialog open={open} onClose={close} title={self ? 'Xóa dữ liệu của tôi?' : `Xóa dữ liệu của ${email}?`}
            footer={<>
              <button type="button" className="button button-ghost" onClick={close}>Không</button>
              <button type="button" className="button button-danger" disabled={!ready || busy} onClick={() => void submit()}>
                {account ? 'Xóa dữ liệu và tài khoản' : 'Xóa dữ liệu'}</button>
            </>}>
      <Notice tone="warning">
        Xóa vĩnh viễn, không hoàn tác: mọi lá số, hồ sơ ngày sinh, hội thoại và câu trả lời, ca mẫu riêng, cài đặt cá nhân.
        Sách trong thư viện và tri thức đã duyệt vẫn giữ. Bản sao lưu cũ khi khôi phục cũng bị xóa lại theo sổ xóa.
      </Notice>
      <label className="checkbox">
        <input type="checkbox" checked={account} onChange={(e) => setAccount(e.target.checked)} />
        <span>Xóa cả tài khoản (không đăng nhập được nữa; email bị xóa)</span>
      </label>
      <div className="field">
        <label htmlFor="erase-confirm">Gõ email <strong>{email}</strong> để xác nhận</label>
        <input id="erase-confirm" autoComplete="off" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
      </div>
      {self && (
        <div className="field">
          <label htmlFor="erase-password">Mật khẩu của bạn</label>
          <input id="erase-password" type="password" autoComplete="current-password" value={password}
                 onChange={(e) => setPassword(e.target.value)} />
        </div>
      )}
      <FormError error={error} />
    </Dialog>
  )
}
