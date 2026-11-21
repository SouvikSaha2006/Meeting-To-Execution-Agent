import React from 'react';

export function ToastContainer({ toasts, onRemove }) {
  if (!toasts.length) return null;
  return (
    <div className="ws-toast-container">
      {toasts.map(t => (
        <div
          key={t.id}
          className={`ws-toast ws-toast-${t.type}`}
          onClick={() => onRemove(t.id)}
          role="alert"
        >
          <span>{t.type === 'success' ? '✓' : t.type === 'error' ? '✗' : 'ℹ'}</span>
          {t.message}
        </div>
      ))}
    </div>
  );
}
