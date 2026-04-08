import React from 'react'

/**
 * In-app confirm dialog (replaces window.confirm).
 */
export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  busy = false,
  onConfirm,
  onCancel,
}) {
  if (!open) return null
  const confirmClass =
    variant === 'danger'
      ? 'bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-50'
      : 'bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-50'

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title">
      <button type="button" className="absolute inset-0 bg-slate-900/50" aria-label="Dismiss" onClick={busy ? undefined : onCancel} disabled={busy} />
      <div className="relative z-10 w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-xl">
        <h2 id="confirm-dialog-title" className="text-lg font-semibold text-slate-900">
          {title}
        </h2>
        {description ? <p className="mt-2 text-sm text-slate-600 whitespace-pre-wrap">{description}</p> : null}
        <div className="mt-6 flex justify-end gap-2">
          <button type="button" className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-800" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button type="button" className={`rounded-xl px-4 py-2 text-sm font-medium ${confirmClass}`} onClick={onConfirm} disabled={busy}>
            {busy ? 'Please wait…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
