/* ============================================================
   NudgeModal.jsx — One-Click Auto-Nudge & Escalation Drafter
   ============================================================ */
import React, { useState } from 'react';

export function NudgeModal({
  isOpen,
  onClose,
  targetType, // 'STAGING_ITEM' | 'TASK'
  targetId,
  initialRecipient = '',
  initialMessage = '',
  taskTitle = '',
  onSend,
}) {
  const [recipient, setRecipient] = useState(initialRecipient || 'Marcus');
  const [channel, setChannel] = useState('slack');
  const [message, setMessage] = useState(
    initialMessage ||
      `Hi @${initialRecipient || 'team'}, friendly check-in regarding "${taskTitle}". Could you please clarify the owner/timeline so this task can be approved?`
  );
  const [sending, setSending] = useState(false);

  if (!isOpen) return null;

  async function handleSend() {
    if (!recipient.trim()) return;
    setSending(true);
    try {
      await onSend({
        target_type: targetType,
        target_id: targetId,
        recipient: recipient.trim(),
        channel,
        message: message.trim(),
      });
      onClose();
    } catch {
      // error handled in useWorkspace
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="ws-modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="ws-modal-card" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="ws-modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 18 }}>⚡</span>
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 600, color: '#0D0D0C', margin: 0 }}>
                Draft &amp; Send Agent Nudge
              </h3>
              <p style={{ fontSize: 12, color: 'rgba(13,13,12,0.5)', margin: '2px 0 0' }}>
                Autonomous quote-backed follow-up dispatched via webhook
              </p>
            </div>
          </div>
          <button className="ws-modal-close" onClick={onClose} type="button">✕</button>
        </div>

        {/* Target context banner */}
        {taskTitle && (
          <div className="ws-modal-context">
            <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: 'rgba(13,13,12,0.5)' }}>
              Regarding Commitment:
            </span>
            <div style={{ fontSize: 13, fontWeight: 500, color: '#0D0D0C', marginTop: 2 }}>
              "{taskTitle}"
            </div>
          </div>
        )}

        {/* Inputs */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 14 }}>
          <div>
            <label className="ws-form-label">Recipient (@handle / name)</label>
            <input
              className="ws-form-input"
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              placeholder="e.g. Marcus, Sarah"
            />
          </div>
          <div>
            <label className="ws-form-label">Dispatch Channel</label>
            <select
              className="ws-form-input"
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              style={{ paddingRight: 24, cursor: 'pointer' }}
            >
              <option value="slack">Slack (#standup-sync)</option>
              <option value="discord">Discord (#engineering)</option>
              <option value="email">Email Notification</option>
            </select>
          </div>
        </div>

        <div style={{ marginTop: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <label className="ws-form-label" style={{ margin: 0 }}>
              AI-Generated Nudge Draft
            </label>
            <span style={{ fontSize: 10, color: '#3FB874', fontWeight: 600 }}>
              ✓ Quoted from meeting record
            </span>
          </div>
          <textarea
            className="ws-form-textarea"
            style={{ height: 110, fontSize: 13, lineHeight: 1.5 }}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Write your message here..."
          />
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 18 }}>
          <button className="ws-btn ws-btn-sm ws-btn-ghost" onClick={onClose} type="button">
            Cancel
          </button>
          <button
            className="ws-btn ws-btn-sm ws-btn-approve"
            onClick={handleSend}
            disabled={sending || !recipient.trim()}
            type="button"
          >
            {sending ? 'Dispatching…' : `Send via ${channel.charAt(0).toUpperCase() + channel.slice(1)}`}
          </button>
        </div>
      </div>
    </div>
  );
}
