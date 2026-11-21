import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import { parsePayload, parseConflictMeta, parseBlastRadius } from '../../../api/client.js';
import { NudgeModal } from '../NudgeModal.jsx';

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

// ─── Meeting Execution Readiness Gauge ────────────────────────────────────────
function ReadinessGauge({ staging = [], analytics }) {
  const activeConflicts = staging.filter((s) => s.state === 'CONFLICT_DETECTED').length;
  const activeClarifications = staging.filter((s) => s.state === 'NEEDS_CLARIFICATION').length;

  // Compute deductions
  const conflictDeduction = activeConflicts * 10;
  const clarifyDeduction = activeClarifications * 6;
  const rawScore = 100 - conflictDeduction - clarifyDeduction;
  const score = analytics?.overall_readiness_avg
    ? Math.round(analytics.overall_readiness_avg)
    : Math.max(20, Math.min(100, rawScore));

  const isLow = score < 70;
  const isMed = score >= 70 && score < 85;

  return (
    <div className="ws-readiness-card">
      <div className="ws-readiness-header">
        <div>
          <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'rgba(13,13,12,0.5)' }}>
            Execution Readiness Engine
          </span>
          <h3 style={{ fontSize: 16, fontWeight: 600, color: '#0D0D0C', margin: '2px 0 0' }}>
            Meeting Execution Readiness Score
          </h3>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className="ws-readiness-score-num" style={{ color: isLow ? '#C564C4' : isMed ? '#E9C22E' : '#3FB874' }}>
            {score} <span style={{ fontSize: 16, fontWeight: 500, color: 'rgba(13,13,12,0.4)' }}>/ 100</span>
          </div>
          <span style={{ fontSize: 10, fontWeight: 600, color: isLow ? '#C564C4' : '#3FB874', textTransform: 'uppercase' }}>
            {isLow ? '⚠️ High Delivery Slippage Risk' : '✓ Safe to Dispatch'}
          </span>
        </div>
      </div>

      {/* Segmented Bar */}
      <div className="ws-readiness-bar-track">
        <div
          className="ws-readiness-bar-fill"
          style={{
            width: `${score}%`,
            background: isLow
              ? 'linear-gradient(90deg, #F2772F 0%, #C564C4 100%)'
              : 'linear-gradient(90deg, #E9C22E 0%, #3FB874 100%)',
          }}
        />
      </div>

      {/* Deduction Tags */}
      <div className="ws-deduction-tags">
        <span style={{ fontSize: 11, color: 'rgba(13,13,12,0.5)' }}>Deduction audit:</span>
        {activeConflicts > 0 && (
          <span className="ws-deduction-tag" style={{ color: '#C564C4', background: '#ECD6E2', borderColor: '#C564C4' }}>
            -{conflictDeduction} Cross-Meeting Conflicts
          </span>
        )}
        {activeClarifications > 0 && (
          <span className="ws-deduction-tag" style={{ color: '#F2772F', background: '#F9CBA9', borderColor: '#F2772F' }}>
            -{clarifyDeduction} Missing Owner / Deadline
          </span>
        )}
        {activeConflicts === 0 && activeClarifications === 0 && (
          <span className="ws-deduction-tag" style={{ color: '#3FB874', background: '#DFE9D4', borderColor: '#3FB874' }}>
            0 Unresolved Blockers
          </span>
        )}
      </div>
    </div>
  );
}

// ─── Stale Commitment Watchdog Banner ─────────────────────────────────────────
function WatchdogBanner({ staleCommitments = [], onNudge }) {
  if (!staleCommitments || staleCommitments.length === 0) return null;
  const first = staleCommitments[0];

  return (
    <div className="ws-watchdog-banner">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 20 }}>⏰</span>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#0D0D0C' }}>
            Watchdog Alert: {staleCommitments.length} task from {first.meeting_title || 'Sprint 14 Kickoff'} is still untouched in TODO
          </div>
          <div style={{ fontSize: 11, color: 'rgba(13,13,12,0.6)', marginTop: 2 }}>
            <strong>{first.owner}</strong>: "{first.title}" — {first.days_overdue || 3} days overdue
          </div>
        </div>
      </div>

      <button
        type="button"
        className="ws-btn ws-btn-sm"
        style={{ background: '#0D0D0C', color: '#FBF6EF', border: 'none', whiteSpace: 'nowrap' }}
        onClick={() => onNudge(first)}
      >
        ⚡ Draft &amp; Send Nudge
      </button>
    </div>
  );
}

// ─── Conflict Card with Blast Radius Simulator ────────────────────────────────
function ConflictCard({ item, actions }) {
  const [busy, setBusy] = useState(false);
  const [showBlastRadius, setShowBlastRadius] = useState(false);

  const payload = parsePayload(item);
  const conflictMeta = parseConflictMeta(item);
  const blastRadius = parseBlastRadius(item) || {
    risk_level: 'HIGH',
    estimated_delay_days: 3,
    impacted_tasks: [],
    mitigation_suggestion:
      'Align affected task owners and apply mocked contracts so downstream teams can proceed without waiting on schema refactoring.',
  };

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
      <div className="ws-card-badges" style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        <span className="ws-badge ws-badge-conflict">CROSS-MEETING CONFLICT</span>
        <span className="ws-badge ws-badge-type">{item.item_type === 'DECISION' ? 'DECISION' : 'ACTION ITEM'}</span>
        {/* Blast Radius Pill Badge */}
        <span className="ws-blast-badge">
          ⚡ Blast Radius: {blastRadius.risk_level || 'HIGH'} (+{blastRadius.estimated_delay_days || 3} Days Slip)
        </span>
      </div>

      <p className="ws-card-title">{title}</p>

      {item.verbatim_quote && (
        <blockquote className="ws-quote-box">"{item.verbatim_quote}"</blockquote>
      )}

      {/* Contradiction Box */}
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

      {/* Blast Radius Toggle & Drawer */}
      <div>
        <button
          type="button"
          className="ws-blast-toggle"
          onClick={() => setShowBlastRadius(!showBlastRadius)}
        >
          {showBlastRadius ? '▲ Hide Downstream Impact (Blast Radius)' : '▼ View Downstream Impact (Blast Radius)'}
        </button>

        {showBlastRadius && (
          <div className="ws-blast-drawer">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: '#C564C4' }}>
                Counterfactual Downstream Cascade ({blastRadius.impacted_tasks?.length || 0} Tasks Impacted)
              </span>
              <span className="ws-badge ws-badge-conflict" style={{ fontSize: 10 }}>
                +{blastRadius.estimated_delay_days || 3} Days Total Slip
              </span>
            </div>

            {blastRadius.impacted_tasks && blastRadius.impacted_tasks.length > 0 ? (
              <div>
                {blastRadius.impacted_tasks.map((task, idx) => (
                  <div key={idx} className="ws-blast-impact-row">
                    <span style={{ color: '#C564C4', fontWeight: 'bold' }}>•</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, color: '#0D0D0C' }}>
                        {task.title}{' '}
                        {task.owner && <span className="ws-badge ws-badge-low" style={{ fontSize: 9, padding: '1px 5px' }}>👤 {task.owner}</span>}
                        {task.current_deadline && <span style={{ fontSize: 10, color: 'rgba(13,13,12,0.45)', marginLeft: 4 }}>Due {fmtDate(task.current_deadline)}</span>}
                      </div>
                      <div style={{ fontSize: 11, color: 'rgba(13,13,12,0.6)', marginTop: 2 }}>
                        {task.impact_reason}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ fontSize: 12, color: 'rgba(13,13,12,0.5)', fontStyle: 'italic', margin: '4px 0' }}>
                Direct team commitments require rescheduling.
              </p>
            )}

            {/* AI Mitigation Recommendation */}
            {blastRadius.mitigation_suggestion && (
              <div className="ws-blast-mitigation">
                <strong>💡 AI Mitigation Suggestion:</strong> {blastRadius.mitigation_suggestion}
              </div>
            )}
          </div>
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

// ─── Clarification Card with Auto-Nudge ────────────────────────────────────────
function ClarifyCard({ item, actions, onOpenNudge }) {
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
      <div className="ws-card-badges" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span className="ws-badge ws-badge-clarify">GUARDRAIL BLOCKED: MISSING INFO</span>
          <span className="ws-badge ws-badge-type">{item.item_type === 'DECISION' ? 'DECISION' : 'ACTION ITEM'}</span>
        </div>
        {item.nudged && (
          <span className="ws-badge ws-badge-ready" style={{ fontSize: 10 }}>
            Nudge Dispatched ✓
          </span>
        )}
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
          placeholder="Owner (e.g. Souvik, Manas)"
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

      {/* Auto-Nudge Trigger Button */}
      <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 11, color: 'rgba(13,13,12,0.45)' }}>
          Missing info blocking execution?
        </span>
        <button
          type="button"
          className="ws-btn ws-btn-sm"
          style={{ height: 28, fontSize: 11, gap: 4 }}
          onClick={() => {
            const cleanTitle = title || item.verbatim_quote || 'this commitment';
            onOpenNudge({
              targetType: 'STAGING_ITEM',
              targetId: item.id,
              recipient: owner || payload.owner || '@team',
              taskTitle: cleanTitle,
              verbatimQuote: item.verbatim_quote || '',
              commitmentTitle: cleanTitle,
              message:
                item.nudge_draft ||
                payload.clarification_prompt ||
                `Hi team, could you please confirm the owner and deadline for "${cleanTitle}" so we can stage and dispatch it?`,
            });
          }}
        >
          ⚡ Draft &amp; Send Nudge
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
      const receiptId = result?.execution_receipt?.id ?? result?.id ?? null;
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
          {isApproved ? '✓ Approved' : '✕ Rejected'}
        </span>
        <span className="ws-badge ws-badge-type">{item.item_type === 'DECISION' ? 'DECISION' : 'ACTION ITEM'}</span>
      </div>
      <p style={{ fontSize: 13, margin: '6px 0 0', textDecoration: isApproved ? 'none' : 'line-through' }}>
        {title}
      </p>
      {item.rejection_reason && (
        <p style={{ fontSize: 11, color: 'rgba(13,13,12,0.45)', margin: '4px 0 0' }}>
          Reason: {item.rejection_reason}
        </p>
      )}
    </div>
  );
}

// ─── Staging Queue ────────────────────────────────────────────────────────────
function StagingQueue({ state, actions, onToast, onOpenNudge }) {
  const filter = state.stagingFilter ?? 'all';
  const items = state.staging ?? [];

  const conflicts = items.filter((i) => i.state === 'CONFLICT_DETECTED');
  const clarify = items.filter((i) => i.state === 'NEEDS_CLARIFICATION');
  const ready = items.filter((i) => i.state === 'READY_TO_APPROVE');
  const closed = items.filter((i) => i.state === 'APPROVED' || i.state === 'REJECTED');

  let filtered = items;
  if (filter === 'conflicts') filtered = conflicts;
  else if (filter === 'clarification') filtered = clarify;
  else if (filter === 'ready') filtered = ready;
  else if (filter === 'all') {
    filtered = [...conflicts, ...clarify, ...ready, ...closed];
  }

  const [bulkBusy, setBulkBusy] = useState(false);
  async function handleApproveAll() {
    setBulkBusy(true);
    try {
      await actions.approveAllReady();
    } finally {
      setBulkBusy(false);
    }
  }

  return (
    <div>
      {/* Meeting Execution Readiness Score Card */}
      <ReadinessGauge staging={items} analytics={state.analytics} />

      {/* Watchdog Alert Banner */}
      <WatchdogBanner
        staleCommitments={state.staleCommitments}
        onNudge={(task) => {
          const title = task.title || 'this task';
          onOpenNudge({
            targetType: 'TASK',
            targetId: task.task_id,
            recipient: task.owner || 'Team',
            taskTitle: title,
            commitmentTitle: title,
            message:
              task.nudge_draft ||
              `Hi @${task.owner || 'team'}, friendly reminder that task "${title}" is untouched in TODO. Please share a quick update!`,
          });
        }}
      />

      {/* Queue Header & Filters */}
      <div className="ws-queue-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 16, fontWeight: 600 }}>Approval Queue</span>
          <span className="ws-badge ws-badge-ready">{items.filter(i => i.state !== 'APPROVED' && i.state !== 'REJECTED').length} Pending</span>
        </div>

        <button
          className="ws-btn ws-btn-approve ws-btn-sm"
          onClick={handleApproveAll}
          disabled={bulkBusy || ready.length === 0}
        >
          {bulkBusy ? <Spinner size={12} /> : null}
          Approve All Ready ({ready.length})
        </button>
      </div>

      <div className="ws-filter-pills" style={{ marginBottom: 16 }}>
        <button
          className={`ws-filter-pill ${filter === 'all' ? 'active' : ''}`}
          onClick={() => actions.switchTab ? actions.loadStaging() : null}
        >
          All ({items.length})
        </button>
        <button
          className={`ws-filter-pill ${filter === 'conflicts' ? 'active' : ''}`}
          onClick={() => actions.dispatch ? actions.dispatch({ type: 'SET_FILTER', filter: 'conflicts' }) : null}
        >
          Conflicts ({conflicts.length})
        </button>
        <button
          className={`ws-filter-pill ${filter === 'clarification' ? 'active' : ''}`}
          onClick={() => actions.dispatch ? actions.dispatch({ type: 'SET_FILTER', filter: 'clarification' }) : null}
        >
          Needs Clarification ({clarify.length})
        </button>
        <button
          className={`ws-filter-pill ${filter === 'ready' ? 'active' : ''}`}
          onClick={() => actions.dispatch ? actions.dispatch({ type: 'SET_FILTER', filter: 'ready' }) : null}
        >
          Ready ({ready.length})
        </button>
      </div>

      {/* Items list */}
      <div className="ws-queue-list">
        {state.loading?.staging && items.length === 0 ? (
          <div className="ws-loading-state">
            <Spinner size={20} />
            <span>Loading queue…</span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="ws-empty">
            <div className="ws-empty-icon">✓</div>
            <div className="ws-empty-text">No items in this filter view.</div>
          </div>
        ) : (
          filtered.map((item) => {
            if (item.state === 'CONFLICT_DETECTED') {
              return <ConflictCard key={item.id} item={item} actions={actions} />;
            }
            if (item.state === 'NEEDS_CLARIFICATION') {
              return <ClarifyCard key={item.id} item={item} actions={actions} onOpenNudge={onOpenNudge} />;
            }
            if (item.state === 'READY_TO_APPROVE') {
              return <ReadyCard key={item.id} item={item} actions={actions} onToast={onToast} />;
            }
            return <ClosedCard key={item.id} item={item} />;
          })
        )}
      </div>
    </div>
  );
}

// ─── Ingest Form with Live Voice Dictation ──────────────────────────────────
const DEFAULT_SPEAKERS = ['Sarah (PM)', 'Rohan (Backend)', 'Ananya (Design)'];

function extractSpeakersFromTranscript(raw) {
  if (!raw) return [];
  const lines = raw.split(/\r\n|\r|\n/);
  const detected = new Set();

  const regexes = [
    /^\s*(?:\[(?:\d{1,2}:\d{2}(?::\d{2})?|\d{1,2}:\d{2}\s*(?:AM|PM)?)\]|\d{1,2}:\d{2}\s*(?:AM|PM)?\s*[-–])\s*\[?([A-Za-z0-9_.\- ]+?)(?:\s*\([^)]*\))?\]?\s*:\s*/i,
    /^\s*\[([A-Za-z0-9_.\- ]+?)(?:\s*\([^)]*\))?\]\s*:\s*/,
    /^\s*\*\*([A-Za-z0-9_.\- ]+?)(?:\s*\([^)]*\))?\*\*\s*:\s*/,
    /^\s*([A-Za-z][A-Za-z0-9_.\- ]{0,35})\s*:\s*/,
  ];

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    for (const rgx of regexes) {
      const match = trimmed.match(rgx);
      if (match && match[1]) {
        let name = match[1].trim();
        name = name.replace(/^\[|\]$/g, '').replace(/^\*\*|\*\*$/g, '').trim();
        if (
          name &&
          name.length >= 2 &&
          !/^(https?|ftp|note|action|decision|agenda|re|fwd)$/i.test(name)
        ) {
          detected.add(name);
          break;
        }
      }
    }
  }
  return Array.from(detected);
}

function formatFilenameToTitle(filename) {
  if (!filename) return '';
  const base = filename.replace(/\.[^/.]+$/, '');
  return base
    .replace(/[-_]+/g, ' ')
    .trim()
    .split(' ')
    .filter(Boolean)
    .map((w) => {
      if (w.toUpperCase() === w && w.length <= 4) return w;
      return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
    })
    .join(' ');
}

function IngestForm({ state, actions }) {
  const [title, setTitle] = useState('');
  const [meetingDate, setMeetingDate] = useState('');
  const [transcript, setTranscript] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);
  const dropRef = useRef(null);

  // Dynamic Speaker Detection from Transcript
  const detectedSpeakers = useMemo(() => {
    return extractSpeakersFromTranscript(transcript);
  }, [transcript]);

  const availableSpeakers = useMemo(() => {
    if (detectedSpeakers.length > 0) {
      return detectedSpeakers;
    }
    return DEFAULT_SPEAKERS;
  }, [detectedSpeakers]);

  // Live Voice Dictation state
  const [isListening, setIsListening] = useState(false);
  const [activeSpeaker, setActiveSpeaker] = useState(DEFAULT_SPEAKERS[0]);
  const [speechSupported, setSpeechSupported] = useState(true);
  const [speechError, setSpeechError] = useState(null);
  const recognitionRef = useRef(null);
  const activeSpeakerRef = useRef(activeSpeaker);

  // Sync activeSpeaker if current speaker is not in availableSpeakers
  useEffect(() => {
    if (availableSpeakers.length > 0 && !availableSpeakers.includes(activeSpeaker)) {
      setActiveSpeaker(availableSpeakers[0]);
    }
  }, [availableSpeakers, activeSpeaker]);

  // Keep ref synced with latest selected speaker
  useEffect(() => {
    activeSpeakerRef.current = activeSpeaker;
  }, [activeSpeaker]);

  // Clean up speech recognition on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch (_) {}
      }
    };
  }, []);

  function toggleDictation() {
    const SpeechRecognition =
      typeof window !== 'undefined'
        ? window.SpeechRecognition || window.webkitSpeechRecognition
        : null;

    if (!SpeechRecognition) {
      setSpeechSupported(false);
      setSpeechError('Speech recognition is not supported in this browser. Please use Google Chrome or Microsoft Edge.');
      return;
    }

    if (isListening) {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch (_) {}
      }
      setIsListening(false);
      return;
    }

    setSpeechError(null);
    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = false;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setIsListening(true);
      };

      recognition.onresult = (event) => {
        let finalChunk = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            finalChunk += event.results[i][0].transcript;
          }
        }
        const clean = finalChunk.trim();
        if (clean) {
          const raw = activeSpeakerRef.current || 'Speaker';
          const cleanPrefix = raw.replace(/\s*\([^)]*\)/, '').trim() || raw;
          const formattedLine = `[${cleanPrefix}]: ${clean}`;
          setTranscript((prev) => (prev ? `${prev.trim()}\n${formattedLine}` : formattedLine));
        }
      };

      recognition.onerror = (event) => {
        console.warn('SpeechRecognition error:', event.error);
        if (event.error === 'not-allowed') {
          setSpeechError('Microphone permission denied. Please allow microphone access in browser settings.');
        } else if (event.error !== 'no-speech') {
          setSpeechError(`Speech recognition error: ${event.error}`);
        }
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err) {
      console.error('Failed to start speech recognition:', err);
      setSpeechError('Could not start speech recognition.');
      setIsListening(false);
    }
  }

  function insertSampleConflict() {
    const raw = activeSpeakerRef.current || 'Sarah';
    const cleanPrefix = raw.replace(/\s*\([^)]*\)/, '').trim() || raw;
    const sample = `[${cleanPrefix}]: The launch date is now moved to November 22nd. No scope is being cut — the full feature set needs to ship. I'm making this call as lead.`;
    setTranscript((prev) => (prev ? `${prev.trim()}\n${sample}` : sample));
    if (!title) setTitle('Architecture & Scope Sync');
    if (!meetingDate) setMeetingDate('2024-11-21');
  }

  const isLoading = state.loading?.ingest === true;

  function processTranscriptFile(file) {
    if (!file) return;
    const isValidExt = file.name.endsWith('.txt') || file.name.endsWith('.md');
    const isValidMime = file.type === 'text/plain' || file.type === 'text/markdown';

    if (!isValidExt && !isValidMime) {
      actions?.addToast?.('Please upload a .txt or .md transcript file', 'error');
      return;
    }

    const reader = new FileReader();
    reader.onload = (evt) => {
      const content = evt.target?.result ?? '';
      setTranscript(content);

      if (!title.trim()) {
        setTitle(formatFilenameToTitle(file.name));
      }
      if (!meetingDate) {
        const todayIso = new Date().toISOString().split('T')[0];
        setMeetingDate(todayIso);
      }

      const lines = content.split(/\r\n|\r|\n/).filter((l) => l.trim().length > 0).length || 1;
      actions?.addToast?.(`Loaded ${file.name} (${lines} lines) ✓`, 'success');
    };
    reader.readAsText(file);
  }

  function handleFileSelect(e) {
    const file = e.target.files?.[0];
    if (file) {
      processTranscriptFile(file);
    }
    e.target.value = '';
  }

  function handleDragEnter(e) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }

  function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const file = e.dataTransfer?.files?.[0];
    if (file) {
      processTranscriptFile(file);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!transcript.trim()) return;
    if (isListening && recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch (_) {}
      setIsListening(false);
    }
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
          VeriFlow will extract decisions, detect cross-meeting conflicts, and stage items for your review.
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

        {/* Transcript Section with Live Mic Header */}
        <div className="ws-form-field">
          <div className="ws-mic-header-row">
            <label className="ws-form-label" style={{ margin: 0 }}>
              Raw Transcript
            </label>

            {/* Live Dictate Toggle Button */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <button
                type="button"
                className={`ws-btn-mic ${isListening ? 'active' : ''}`}
                onClick={toggleDictation}
                title={speechSupported ? 'Click to dictate live voice speech' : 'Speech recognition requires Chrome/Edge'}
              >
                <span className={`ws-mic-indicator ${isListening ? 'pulsing' : ''}`}>
                  {isListening ? '🔴' : '🎙️'}
                </span>
                <span>{isListening ? 'Recording… (Click to Stop)' : '🎙️ Live Dictate Meeting'}</span>
              </button>
            </div>
          </div>

          {/* Quick Speaker Selector Pills */}
          <div className="ws-speaker-selector-bar">
            <span className="ws-speaker-selector-label">Speaker:</span>
            {availableSpeakers.map((spk) => {
              const isSelected = activeSpeaker === spk;
              const cleanPrefix = spk.replace(/\s*\([^)]*\)/, '').trim() || spk;
              return (
                <button
                  key={spk}
                  type="button"
                  className={`ws-speaker-pill ${isSelected ? 'active' : ''}`}
                  onClick={() => setActiveSpeaker(spk)}
                  title={`Prefix spoken lines with [${cleanPrefix}]:`}
                >
                  <span className="ws-speaker-dot" />
                  {spk}
                </button>
              );
            })}
            <button
              type="button"
              className="ws-speaker-sample-btn"
              onClick={insertSampleConflict}
              title="Quickly insert a voice conflict sample for live judging"
            >
              ⚡ Insert Conflict Quote
            </button>
          </div>

          {speechError && (
            <div className="ws-mic-fallback-note">
              <span>⚠️ {speechError}</span>
            </div>
          )}

          <textarea
            className="ws-form-textarea"
            style={{ height: 200 }}
            placeholder="Paste raw transcript here, or dictate live using the mic above..."
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
          />
        </div>

        {/* Hidden File Input for Click-to-Browse */}
        <input
          type="file"
          accept=".txt,.md,text/plain,text/markdown"
          ref={fileInputRef}
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />

        {/* Dropzone */}
        <div
          ref={dropRef}
          className={`ws-dropzone ${isDragging ? 'is-dragging ws-dropzone--over' : ''}`}
          onClick={() => fileInputRef.current?.click()}
          onDragEnter={handleDragEnter}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          title="Click to browse or drop a .txt or .md transcript file"
        >
          <div className="ws-dropzone-content">
            <span className="ws-dropzone-icon">📄</span>
            <span className="ws-dropzone-text">
              {isDragging
                ? 'Release to load transcript file...'
                : 'Drop .txt or .md file to auto-fill (or click to browse)'}
            </span>
          </div>
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
  const [nudgeModal, setNudgeModal] = useState({
    isOpen: false,
    targetType: 'STAGING_ITEM',
    targetId: null,
    recipient: '',
    taskTitle: '',
    message: '',
  });

  const showToast = useCallback((msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 5000);
  }, []);

  return (
    <div className="ws-ingest-layout">
      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}

      {/* Auto-Nudge Modal */}
      <NudgeModal
        isOpen={nudgeModal.isOpen}
        onClose={() => setNudgeModal((prev) => ({ ...prev, isOpen: false }))}
        targetType={nudgeModal.targetType}
        targetId={nudgeModal.targetId}
        initialRecipient={nudgeModal.recipient}
        taskTitle={nudgeModal.taskTitle}
        commitmentTitle={nudgeModal.commitmentTitle}
        verbatimQuote={nudgeModal.verbatimQuote}
        initialMessage={nudgeModal.message}
        onSend={actions.sendNudgeAction}
      />

      {/* Left column — 42% */}
      <div className="ws-ingest-left">
        <IngestForm state={state} actions={actions} />
        <AgentTrace trace={state.lastIngestTrace ?? []} />
      </div>

      {/* Right column — 58% */}
      <div className="ws-ingest-right">
        <StagingQueue
          state={state}
          actions={actions}
          onToast={showToast}
          onOpenNudge={(cfg) => setNudgeModal({ isOpen: true, ...cfg })}
        />
      </div>
    </div>
  );
}

export default IngestTab;
