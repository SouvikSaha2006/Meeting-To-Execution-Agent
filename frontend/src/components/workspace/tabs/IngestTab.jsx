import { useState, useRef, useCallback } from 'react';
import { parsePayload, parseConflictMeta } from '../../../api/client.js';

// ─── Stage name prettifier ────────────────────────────────────────────────────
const STAGE_LABELS = {
  parse_transcript: '1. Speaker Diarization',
  extract_commitments: '2. Structured Extraction',
  detect_conflicts_and_duplicates: '3. Cross-Meeting Conflict Audit',
  stage_for_approval: '4. HITL Staging',
};
function prettifyStage(name) {
  return STAGE_LABELS[name] ?? name;
}

// ─── Date formatter ───────────────────────────────────────────────────────────
function fmtDate(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

// ─── Toast ────────────────────────────────────────────────────────────────────
function Toast({ message, onDismiss }) {
  return (
    <div className="ws-toast" onClick={onDismiss}>
      <span>{message}</span>
      <button className="ws-toast-close" onClick={onDismiss}>✕</button>
    </div>
  );
}

// ─── Spinner ──────────────────────────────────────────────────────────────────
function Spinner({ size = 16 }) {
  return (
    <svg
      className="ws-spinner"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
    >
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </svg>
  );
}

// ─── Agent Trace Stepper ──────────────────────────────────────────────────────
function AgentTrace({ trace }) {
  if (!trace || trace.length === 0) return null;

  const statusClass = (status) => {
    if (status === 'success' || status === 'completed') return 'ws-trace-dot--success';
    if (status === 'running' || status === 'in_progress') return 'ws-trace-dot--running';
    if (status === 'error' || status === 'failed') return 'ws-trace-dot--error';
    return 'ws-trace-dot--idle';
  };

  return (
    <div style={{ marginTop: 24 }}>
      <p style={{ fontSize: 13, fontWeight: 500, color: 'rgba(13,13,12,0.56)', marginBottom: 12 }}>
        Agent Reasoning Trace
      </p>
      <div className="ws-trace">
        {trace.map((step, idx) => (
          <div key={idx} className="ws-trace-step">
            {/* Left: dot + connector line */}
            <div className="ws-trace-dot-col">
              <div className={`ws-trace-dot ${statusClass(step.status)}`}>
                {idx + 1}
              </div>
              {idx < trace.length - 1 && <div className="ws-trace-line" />}
            </div>

            {/* Right: stage info */}
            <div className="ws-trace-body">
              <div className="ws-trace-header">
                <span className="ws-trace-stage">{prettifyStage(step.stage)}</span>
                {step.duration_ms != null && (
                  <span style={{ fontSize: 11, color: 'rgba(13,13,12,0.46)', marginLeft: 8 }}>
                    {step.duration_ms}ms
                  </span>
                )}
              </div>
              {step.output_summary && (
                <p className="ws-trace-summary">{step.output_summary}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Conflict Card ────────────────────────────────────────────────────────────
function ConflictCard({ item, actions }) {
  const [busy, setBusy] = useState(false);
  const payload = parsePayload(item);
  const conflictMeta = parseConflictMeta(item);
  const title = item.item_type === 'DECISION' ? payload.statement : payload.title;

  async function handleSupersede() {
    setBusy(true);
    try {
      await actions.resolveItem(item.id, { conflict_resolution: 'SUPERSEDE_OLD' });
      await actions.approveItem(item.id);
    } finally {
      setBusy(false);
    }
  }

  async function handleKeepOriginal() {
    setBusy(true);
    try {
      await actions.resolveItem(item.id, { conflict_resolution: 'KEEP_ORIGINAL' });
      await actions.rejectItem(item.id);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ws-card ws-card-conflict">
      <div className="ws-card-badges">
        <span className="ws-badge ws-badge-conflict">CROSS-MEETING CONFLICT</span>
        <span className="ws-badge ws-badge-type">{item.item_type === 'DECISION' ? 'DECISION' : 'ACTION ITEM'}</span>
      </div>

      <p className="ws-card-title">{title}</p>

      {item.verbatim_quote && (
        <blockquote className="ws-quote-box">"{item.verbatim_quote}"</blockquote>
      )}

      <div className="ws-conflict-compare">
        <p className="ws-conflict-label">⚡ Conflicts with:</p>
        <p className="ws-conflict-prev-meeting">
          {conflictMeta.previous_meeting_title}
          {conflictMeta.previous_meeting_date && (
            <span style={{ color: 'rgba(13,13,12,0.46)', marginLeft: 6 }}>
              {fmtDate(conflictMeta.previous_meeting_date)}
            </span>
          )}
        </p>
        {conflictMeta.previous_quote && (
          <p className="ws-conflict-prev-quote">"{conflictMeta.previous_quote}"</p>
        )}
        {conflictMeta.conflict_explanation && (
          <p className="ws-conflict-explanation">{conflictMeta.conflict_explanation}</p>
        )}
      </div>

      <div className="ws-card-actions">
        <button
          className="ws-btn ws-btn-primary"
          onClick={handleSupersede}
          disabled={busy}
        >
          {busy ? <Spinner size={13} /> : null}
          Supersede Old Decision
        </button>
        <button
          className="ws-btn ws-btn-ghost"
          onClick={handleKeepOriginal}
          disabled={busy}
        >
          Keep Original
        </button>
      </div>
    </div>
  );
}

// ─── Clarification Card ───────────────────────────────────────────────────────
function ClarifyCard({ item, actions }) {
  const [owner, setOwner] = useState('');
  const [deadline, setDeadline] = useState('');
  const [busy, setBusy] = useState(false);
  const payload = parsePayload(item);
  const title = item.item_type === 'DECISION' ? payload.statement : payload.title;
  const missingFields = payload.missing_fields ?? [];

  async function handleSave() {
    setBusy(true);
    try {
      await actions.resolveItem(item.id, {
        owner: owner || undefined,
        deadline_iso: deadline || undefined,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ws-card ws-card-clarify">
      <div className="ws-card-badges">
        <span className="ws-badge ws-badge-clarify">GUARDRAIL BLOCKED: MISSING INFO</span>
        <span className="ws-badge ws-badge-type">{item.item_type === 'DECISION' ? 'DECISION' : 'ACTION ITEM'}</span>
      </div>

      <p className="ws-card-title">{title}</p>

      {payload.clarification_prompt && (
        <p style={{ fontSize: 13, color: 'rgba(13,13,12,0.56)', margin: '8px 0' }}>
          {payload.clarification_prompt}
        </p>
      )}

      {missingFields.length > 0 && (
        <div className="ws-missing-fields">
          {missingFields.map((f) => (
            <span key={f} className="ws-badge ws-badge-missing">{f}</span>
          ))}
        </div>
      )}

      {item.verbatim_quote && (
        <blockquote className="ws-quote-box">"{item.verbatim_quote}"</blockquote>
      )}

      <div className="ws-inline-form">
        <input
          className="ws-form-input"
          placeholder="Owner"
          value={owner}
          onChange={(e) => setOwner(e.target.value)}
        />
        <input
          className="ws-form-input"
          type="date"
          value={deadline}
          onChange={(e) => setDeadline(e.target.value)}
        />
        <button
          className="ws-btn ws-btn-primary"
          onClick={handleSave}
          disabled={busy}
        >
          {busy ? <Spinner size={13} /> : null}
          Save &amp; Mark Ready
        </button>
      </div>
    </div>
  );
}

// ─── Ready Card ───────────────────────────────────────────────────────────────
function ReadyCard({ item, actions, onToast }) {
  const [busy, setBusy] = useState(false);
  const [quoteOpen, setQuoteOpen] = useState(false);
  const payload = parsePayload(item);
  const title = item.item_type === 'DECISION' ? payload.statement : payload.title;

  const priorityClass =
    payload.priority === 'HIGH'
      ? 'ws-badge-high'
      : payload.priority === 'LOW'
      ? 'ws-badge-low'
      : 'ws-badge-medium';

  async function handleApprove() {
    setBusy(true);
    try {
      const result = await actions.approveItem(item.id);
      const receiptId = result?.execution_receipt_id ?? result?.id ?? null;
      onToast(receiptId ? `✓ Approved — receipt #${receiptId}` : '✓ Approved & queued for execution');
    } catch (err) {
      onToast(`Error: ${err.message ?? 'Could not approve'}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleReject() {
    setBusy(true);
    try {
      await actions.rejectItem(item.id);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ws-card ws-card-ready">
      <div className="ws-card-badges">
        <span className="ws-badge ws-badge-ready">READY TO APPROVE</span>
        <span className="ws-badge ws-badge-type">{item.item_type === 'DECISION' ? 'DECISION' : 'ACTION ITEM'}</span>
      </div>

      <p style={{ fontSize: 15, fontWeight: 600, margin: '10px 0 8px' }}>{title}</p>

      <div className="ws-meta-badges">
        {payload.owner && <span className="ws-badge ws-badge-meta">👤 {payload.owner}</span>}
        {payload.deadline_iso && (
          <span className="ws-badge ws-badge-meta">📅 {fmtDate(payload.deadline_iso)}</span>
        )}
        {payload.priority && (
          <span className={`ws-badge ${priorityClass}`}>{payload.priority}</span>
        )}
      </div>

      {payload.depends_on_task_title && (
        <div className="ws-dependency-warn">
          ⚠ Blocked by: {payload.depends_on_task_title}
        </div>
      )}

      {item.verbatim_quote && (
        <div style={{ marginTop: 8 }}>
          <button
            className="ws-toggle-quote"
            onClick={() => setQuoteOpen((o) => !o)}
          >
            {quoteOpen ? 'Hide quote ▴' : 'Show quote ▾'}
          </button>
          {quoteOpen && (
            <blockquote className="ws-quote-box">"{item.verbatim_quote}"</blockquote>
          )}
        </div>
      )}

      <div className="ws-card-actions">
        <button
          className="ws-btn ws-btn-primary"
          onClick={handleApprove}
          disabled={busy}
        >
          {busy ? <Spinner size={13} /> : null}
          ✓ Approve &amp; Execute
        </button>
        <button
          className="ws-btn ws-btn-ghost"
          onClick={handleReject}
          disabled={busy}
        >
          Reject
        </button>
      </div>
    </div>
  );
}

// ─── Approved / Rejected Cards ────────────────────────────────────────────────
function ClosedCard({ item }) {
  const payload = parsePayload(item);
  const title = item.item_type === 'DECISION' ? payload.statement : payload.title;
  const isApproved = item.state === 'APPROVED';

  return (
    <div className={`ws-card ${isApproved ? 'ws-card-approved' : 'ws-card-rejected'}`}>
      <div className="ws-card-badges">
        <span className={`ws-badge ${isApproved ? 'ws-badge-approved' : 'ws-badge-rejected'}`}>
          {isApproved ? '✓ Approved' : '✗ Rejected'}
        </span>
        <span className="ws-badge ws-badge-type">{item.item_type === 'DECISION' ? 'DECISION' : 'ACTION ITEM'}</span>
      </div>
      <p className="ws-card-title" style={{ opacity: 0.6 }}>{title}</p>
      {!isApproved && item.rejection_reason && (
        <p style={{ fontSize: 12, color: 'rgba(13,13,12,0.46)', marginTop: 4 }}>
          Reason: {item.rejection_reason}
        </p>
      )}
    </div>
  );
}

// ─── HITL Staging Queue ───────────────────────────────────────────────────────
function StagingQueue({ state, actions, onToast }) {
  const { staging = [], pendingCount = 0, stagingFilter = 'All', loading = {} } = state;

  const conflictCount = staging.filter((i) => i.state === 'CONFLICT_DETECTED').length;
  const clarifyCount = staging.filter((i) => i.state === 'NEEDS_CLARIFICATION').length;
  const readyCount = staging.filter((i) => i.state === 'READY_TO_APPROVE').length;

  const FILTERS = [
    { label: 'All', key: 'All', dotClass: null },
    { label: 'Conflicts', key: 'Conflicts', dotClass: 'ws-dot-rose', count: conflictCount },
    { label: 'Needs Clarification', key: 'Clarification', dotClass: 'ws-dot-apricot', count: clarifyCount },
    { label: 'Ready', key: 'Ready', dotClass: 'ws-dot-sage', count: readyCount },
  ];

  function filterItems() {
    switch (stagingFilter) {
      case 'Conflicts':
        return staging.filter((i) => i.state === 'CONFLICT_DETECTED');
      case 'Clarification':
        return staging.filter((i) => i.state === 'NEEDS_CLARIFICATION');
      case 'Ready':
        return staging.filter((i) => i.state === 'READY_TO_APPROVE');
      default: // 'All'
        return staging;
    }
  }

  const activeItems = filterItems().filter(
    (i) => i.state === 'CONFLICT_DETECTED' || i.state === 'NEEDS_CLARIFICATION' || i.state === 'READY_TO_APPROVE'
  );
  const closedItems = filterItems().filter(
    (i) => i.state === 'APPROVED' || i.state === 'REJECTED'
  );

  return (
    <div className="ws-queue-col">
      {/* Header */}
      <div className="ws-queue-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 16, fontWeight: 600 }}>Approval Queue</span>
          {pendingCount > 0 && (
            <span className="ws-badge ws-badge-count">{pendingCount} pending</span>
          )}
        </div>
        <button
          className="ws-btn ws-btn-primary"
          onClick={actions.approveAllReady}
          disabled={readyCount === 0}
        >
          Approve All Ready
        </button>
      </div>

      {/* Filter pills */}
      <div className="ws-filter-pills">
        {FILTERS.map(({ label, key, dotClass, count }) => (
          <button
            key={key}
            className={`ws-filter-pill ${stagingFilter === key ? 'active' : ''}`}
            onClick={() => actions.setStagingFilter(key)}
          >
            {dotClass && <span className={`ws-dot ${dotClass}`} />}
            {label}
            {count != null && count > 0 && (
              <span className="ws-filter-count">{count}</span>
            )}
          </button>
        ))}
      </div>

      {/* Items */}
      {loading.staging ? (
        <div className="ws-empty">
          <Spinner size={24} />
        </div>
      ) : activeItems.length === 0 && closedItems.length === 0 ? (
        <div className="ws-empty">
          Run the agent pipeline or load a demo meeting to see the approval queue.
        </div>
      ) : (
        <div className="ws-queue-list">
          {activeItems.map((item) => {
            if (item.state === 'CONFLICT_DETECTED') {
              return <ConflictCard key={item.id} item={item} actions={actions} />;
            }
            if (item.state === 'NEEDS_CLARIFICATION') {
              return <ClarifyCard key={item.id} item={item} actions={actions} />;
            }
            if (item.state === 'READY_TO_APPROVE') {
              return (
                <ReadyCard
                  key={item.id}
                  item={item}
                  actions={actions}
                  onToast={onToast}
                />
              );
            }
            return null;
          })}

          {closedItems.length > 0 && (
            <div className="ws-closed-items">
              {closedItems.map((item) => (
                <ClosedCard key={item.id} item={item} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Ingest Form ──────────────────────────────────────────────────────────────
function IngestForm({ state, actions }) {
  const [title, setTitle] = useState('');
  const [meetingDate, setMeetingDate] = useState('');
  const [transcript, setTranscript] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const dropRef = useRef(null);

  const isLoading = state.loading?.ingest === true;

  function handleFileRead(file) {
    const reader = new FileReader();
    reader.onload = (e) => setTranscript(e.target.result ?? '');
    reader.readAsText(file);
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file && (file.name.endsWith('.txt') || file.name.endsWith('.md'))) {
      handleFileRead(file);
    }
  }

  function handleDragOver(e) {
    e.preventDefault();
    setDragOver(true);
  }

  function handleDragLeave() {
    setDragOver(false);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!transcript.trim()) return;
    await actions.ingestMeeting({ title, meeting_date: meetingDate, raw_transcript: transcript });
    setTitle('');
    setMeetingDate('');
    setTranscript('');
  }

  return (
    <div className="ws-card">
      <div style={{ marginBottom: 16 }}>
        <p style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>New Meeting Transcript</p>
        <p style={{ fontSize: 12, color: 'rgba(13,13,12,0.56)', marginTop: 4 }}>
          Vela will extract decisions, detect cross-meeting conflicts, and stage items for your review.
        </p>
      </div>

      {state.error && (
        <div className="ws-error-banner">{state.error}</div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="ws-form-field">
          <label className="ws-form-label">Meeting Title</label>
          <input
            className="ws-form-input"
            placeholder="e.g. Q4 Planning Sync"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>

        <div className="ws-form-field">
          <label className="ws-form-label">Meeting Date</label>
          <input
            className="ws-form-input"
            type="date"
            value={meetingDate}
            onChange={(e) => setMeetingDate(e.target.value)}
          />
        </div>

        <div className="ws-form-field">
          <label className="ws-form-label">Raw Transcript</label>
          <textarea
            className="ws-form-textarea"
            style={{ height: 220 }}
            placeholder="Paste raw transcript here, or drag & drop a .txt / .md file below..."
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
          />
        </div>

        {/* Dropzone */}
        <div
          ref={dropRef}
          className={`ws-dropzone ${dragOver ? 'ws-dropzone--over' : ''}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
        >
          Drop .txt or .md file to auto-fill
        </div>

        <button
          type="submit"
          className={`ws-btn ws-btn-primary ws-btn-full ${isLoading ? 'ws-btn--loading' : ''}`}
          disabled={isLoading || !transcript.trim()}
          style={{ marginTop: 16 }}
        >
          {isLoading && <Spinner size={15} />}
          {isLoading ? 'Running Pipeline…' : 'Run Agent Pipeline'}
        </button>
      </form>
    </div>
  );
}

// ─── IngestTab (root) ─────────────────────────────────────────────────────────
export function IngestTab({ state, actions }) {
  const [toast, setToast] = useState(null);

  const showToast = useCallback((msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 5000);
  }, []);

  return (
    <div className="ws-ingest-layout">
      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}

      {/* Left column — 42% */}
      <div className="ws-ingest-left">
        <IngestForm state={state} actions={actions} />
        <AgentTrace trace={state.lastIngestTrace ?? []} />
      </div>

      {/* Right column — 58% */}
      <div className="ws-ingest-right">
        <StagingQueue state={state} actions={actions} onToast={showToast} />
      </div>
    </div>
  );
}
