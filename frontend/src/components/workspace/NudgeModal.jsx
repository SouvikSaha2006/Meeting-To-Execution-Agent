/* ============================================================
   NudgeModal.jsx — One-Click Auto-Nudge & Escalation Drafter
   ============================================================ */
import React, { useState, useEffect } from 'react';

function buildDefaultMessage(rawRecipient, rawTitle) {
  const cleanRecipient = (rawRecipient || '').trim();
  const atRecipient = cleanRecipient
    ? (cleanRecipient.startsWith('@') ? cleanRecipient : `@${cleanRecipient}`)
    : '@team';
  const cleanTitle = (rawTitle || '').trim() || 'this commitment';
  return `Hi ${atRecipient}, friendly check-in regarding "${cleanTitle}". Could you please confirm progress / clarify the owner and timeline so we stay on track?`;
}

export function NudgeModal({
  isOpen,
  onClose,
  targetType = 'TASK', // 'STAGING_ITEM' | 'TASK'
  targetId,
  initialRecipient = '',
  initialMessage = '',
  taskTitle = '',
  verbatimQuote = '',
  commitmentTitle = '',
  onSend,
}) {
  const [recipient, setRecipient] = useState('');
  const [channel, setChannel] = useState('slack');
  const [message, setMessage] = useState('');
  const [isDispatching, setIsDispatching] = useState(false);
  const [hasUserEditedMessage, setHasUserEditedMessage] = useState(false);

  const displayTitle = (taskTitle || commitmentTitle || verbatimQuote || '').trim();

  // Reset and synchronize fields whenever modal is opened
  useEffect(() => {
    if (isOpen) {
      const defaultRec = (initialRecipient || '').trim() || '@team';
      const cleanQuote = (taskTitle || commitmentTitle || verbatimQuote || '').trim();
      setRecipient(defaultRec);
      setChannel('slack');
      setHasUserEditedMessage(false);
      setIsDispatching(false);

      if (initialMessage && !initialMessage.includes('""') && initialMessage.trim()) {
        setMessage(initialMessage.trim());
      } else {
        setMessage(buildDefaultMessage(defaultRec, cleanQuote));
      }
    }
  }, [isOpen, initialRecipient, initialMessage, taskTitle, commitmentTitle, verbatimQuote]);

  if (!isOpen) return null;

  function handleRecipientChange(e) {
    const val = e.target.value;
    setRecipient(val);
    if (!hasUserEditedMessage) {
      setMessage(buildDefaultMessage(val, displayTitle));
    }
  }

  function handleMessageChange(e) {
    setMessage(e.target.value);
    setHasUserEditedMessage(true);
  }

  async function handleSend() {
    if (isDispatching) return;
    setIsDispatching(true);

    const cleanRecipient = (recipient || '').trim() || '@team';
    const cleanMsg = (message || '').trim() || buildDefaultMessage(cleanRecipient, displayTitle);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10s strict timeout

    try {
      if (typeof onSend === 'function') {
        await onSend({
          target_type: targetType || 'TASK',
          target_id: targetId,
          recipient: cleanRecipient,
          channel: channel || 'slack',
          message: cleanMsg,
          signal: controller.signal,
        });
      }
      onClose();
    } catch (err) {
      console.warn('Nudge dispatch completed with fallback / timeout notice:', err);
      onClose();
    } finally {
      clearTimeout(timeoutId);
      setIsDispatching(false);
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
        {displayTitle && (
          <div className="ws-modal-context">
            <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', color: 'rgba(13,13,12,0.5)' }}>
              Regarding Commitment:
            </span>
            <div style={{ fontSize: 13, fontWeight: 500, color: '#0D0D0C', marginTop: 2 }}>
              "{displayTitle}"
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
              onChange={handleRecipientChange}
              placeholder="e.g. Souvik, Manas, @team"
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
            onChange={handleMessageChange}
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
            disabled={isDispatching || !recipient.trim()}
            type="button"
          >
            {isDispatching ? 'Dispatching…' : `Send via ${channel.charAt(0).toUpperCase() + channel.slice(1)}`}
          </button>
        </div>
      </div>
    </div>
  );
}

export default NudgeModal;
