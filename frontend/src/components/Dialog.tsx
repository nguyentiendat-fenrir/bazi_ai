'use client'
// Modal on the native <dialog>: focus stays inside, Esc closes, the page behind is inert.
import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'

export function Dialog({ open, title, onClose, children, footer }: {
  open: boolean, title: string, onClose(): void, children: ReactNode, footer?: ReactNode,
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog ref={ref} className="dialog" aria-labelledby={titleId}
            onCancel={(event) => { event.preventDefault(); onClose() }}>
      <div className="dialog-head">
        <h2 id={titleId}>{title}</h2>
        <button type="button" className="button button-ghost" onClick={onClose} aria-label="Đóng">✕</button>
      </div>
      <div className="dialog-body">{open && children}</div>
      {footer && <div className="dialog-foot">{footer}</div>}
    </dialog>
  )
}
