/* ============================================================
   BoardTab.jsx — Execution Board with Proactive Deadline Reminders
   ============================================================ */
import React, { useEffect } from 'react';

function formatDeadline(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
    });
  } catch {
    return iso;
  }
}

function parseReceipt(json) {
  if (!json) return null;
  try {
    return JSON.parse(json);
  } catch {
    return null;
  }
}

/**
 * Upcoming Deadline Reminders Strip
 * Displays tasks due in <48h with live countdown pills and one-click bulk reminder dispatch.
 */
function UpcomingRemindersStrip({ reminders, loading, onDispatchAll, onSendSingle }) {
  const [localDispatching, setLocalDispatching] = React.useState(false);

  if (!reminders || reminders.length === 0) return null;

  const allSent = reminders.every((r) => r.reminder_sent);
  const pendingCount = reminders.filter((r) => !r.reminder_sent).length;
  const isBusy = loading || localDispatching;

  const handleDispatch = async () => {
    if (isBusy || allSent) return;
    setLocalDispatching(true);
    try {
      await onDispatchAll();
    } finally {
      setLocalDispatching(false);
    }
  };

  return (
    <div className="ws-reminders-strip">
      <div className="ws-reminders-strip-header">
        <div className="ws-reminders-header-left">
          <div className="ws-reminders-icon-wrapper">
            <span className="ws-reminders-icon">🔔</span>
          </div>
          <div>
            <div className="ws-reminders-title-row">
              <span className="ws-reminders-title">Proactive Pre-Deadline Reminders</span>
              <span className={`ws-reminders-count-badge ${allSent ? 'all-sent' : 'pending'}`}>
                {pendingCount > 0 ? `${pendingCount} Due <48h` : 'All Reminders Sent ✓'}
              </span>
            </div>
            <p className="ws-reminders-subtitle">
              Automated 48-hour watchdog: proactive alerts dispatched before sprint commitments slip.
            </p>
          </div>
        </div>

        <div className="ws-reminders-header-right">
          <button
            className={`ws-btn-dispatch-reminders ${allSent ? 'sent' : ''}`}
            onClick={handleDispatch}
            disabled={isBusy || allSent}
            type="button"
            title="Dispatch proactive reminders to all task owners due within 48h"
          >
            {isBusy ? (
              <>
                <span className="ws-spinner-sm" />
                <span>Dispatching…</span>
              </>
            ) : allSent ? (
              <>✓ Reminders Dispatched</>
            ) : (
              <>⚡ Trigger Deadline Reminders</>
            )}
          </button>
        </div>
      </div>

      <div className="ws-reminders-cards-grid">
        {reminders.map((item) => {
          const title = item.task_title || item.title;
          const countdown = item.countdown_label || (item.hours_remaining > 0 ? `Due in ${item.hours_remaining}h` : 'Overdue');
          return (
            <div
              key={item.task_id}
              className={`ws-reminder-item-card ${item.reminder_sent ? 'sent' : ''}`}
            >
              <div className="ws-reminder-item-top">
                <span className="ws-reminder-countdown-pill">{countdown}</span>
                {item.reminder_sent ? (
                  <span className="ws-reminder-sent-tag">Reminder Sent ✓</span>
                ) : (
                  <button
                    className="ws-reminder-item-btn"
                    onClick={() => onSendSingle(item.task_id)}
                    type="button"
                  >
                    Remind Owner →
                  </button>
                )}
              </div>
              <div className="ws-reminder-item-title" title={title}>
                {title}
              </div>
              <div className="ws-reminder-item-meta">
                <span className="ws-badge">👤 {item.owner || 'Unassigned'}</span>
                {item.deadline_iso && (
                  <span className="ws-badge">📅 {item.deadline_iso}</span>
                )}
                {item.urgency && (
                  <span className={`ws-badge ws-badge-${item.urgency === 'CRITICAL_DUE_SOON' ? 'apricot' : 'medium'}`}>
                    {item.urgency === 'CRITICAL_DUE_SOON' ? 'Critical' : 'Upcoming'}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TaskCard({ task, actions, reminderMeta }) {
  const receipt = parseReceipt(task.external_execution_receipt_json);
  const isReminded = Boolean(task.reminder_sent || reminderMeta?.reminder_sent);
  const countdown = reminderMeta?.countdown_label || (reminderMeta?.hours_remaining > 0 ? `Due in ${reminderMeta.hours_remaining}h` : null);

  return (
    <div className="ws-task-card">
      <div className="ws-task-title">{task.title}</div>

      <div className="ws-task-meta-row">
        {task.owner && (
          <span className="ws-badge">{task.owner}</span>
        )}
        {task.deadline_iso && (
          <span className="ws-badge">{formatDeadline(task.deadline_iso)}</span>
        )}
        {countdown && (
          <span className="ws-countdown-pill-card">
            ⏳ {countdown}
          </span>
        )}
        {task.priority && (
          <span className={`ws-badge ws-badge-${(task.priority || '').toLowerCase()}`}>
            {task.priority}
          </span>
        )}
        {task.depends_on_id && (
          <span className="ws-badge ws-badge-apricot">⚠ Blocker</span>
        )}
        {receipt && (
          <span className="ws-receipt-tag">
            🔗 Dispatched
            {receipt.id ? ` #${receipt.id}` : ''}
            {receipt.channel ? ` · ${receipt.channel}` : ''}
          </span>
        )}
      </div>

      {/* Reminder Action Row on To Do & In Progress cards */}
      {(task.status === 'TODO' || task.status === 'IN_PROGRESS') && (
        <div className="ws-task-reminder-row">
          {isReminded ? (
            <span
              className="ws-reminded-pill"
              title="Automated deadline reminder dispatched"
            >
              🔔 Reminded ✓
            </span>
          ) : (
            <button
              className="ws-btn-remind-owner"
              onClick={() => actions.sendTaskReminderAction(task.id)}
              type="button"
              title={`Send automated pre-deadline reminder to ${task.owner || 'owner'}`}
            >
              🔔 Remind Owner
            </button>
          )}
        </div>
      )}

      <div className="ws-task-actions">
        {task.status === 'TODO' && (
          <button
            className="ws-btn-sm"
            onClick={() => actions.moveTask(task.id, 'IN_PROGRESS')}
          >
            → Start
          </button>
        )}
        {task.status === 'IN_PROGRESS' && (
          <>
            <button
              className="ws-btn-sm ws-btn-sm-success"
              onClick={() => actions.moveTask(task.id, 'DONE')}
            >
              ✓ Complete
            </button>
            <button
              className="ws-btn-sm"
              onClick={() => actions.moveTask(task.id, 'TODO')}
            >
              ← Reset
            </button>
          </>
        )}
        {task.status === 'DONE' && (
          <button
            className="ws-btn-sm"
            onClick={() => actions.moveTask(task.id, 'IN_PROGRESS')}
          >
            ↩ Reopen
          </button>
        )}
      </div>
    </div>
  );
}

function KanbanColumn({ title, tasks, actions, reminderMap }) {
  return (
    <div className="ws-kanban-col">
      <div className="ws-kanban-col-header">
        <span>{title}</span>
        <span className="ws-tab-badge">{tasks.length}</span>
      </div>
      {tasks.length === 0 ? (
        <p className="ws-kanban-empty">Nothing here yet</p>
      ) : (
        tasks.map((task) => (
          <TaskCard
            key={task.id}
            task={task}
            actions={actions}
            reminderMeta={reminderMap[task.id]}
          />
        ))
      )}
    </div>
  );
}

export function BoardTab({ state, actions }) {
  useEffect(() => {
    if (state.tasks.length === 0) {
      actions.loadTasks();
    }
    actions.loadUpcomingReminders();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reminderMap = (state.upcomingReminders || []).reduce((acc, r) => {
    acc[r.task_id] = r;
    return acc;
  }, {});

  if (state.loading?.tasks && state.tasks.length === 0) {
    return (
      <div className="ws-loading-state">
        <div className="ws-spinner" />
        <span>Loading execution tasks…</span>
      </div>
    );
  }

  const todo = state.tasks.filter((t) => t.status === 'TODO');
  const inProgress = state.tasks.filter((t) => t.status === 'IN_PROGRESS');
  const done = state.tasks.filter((t) => t.status === 'DONE');

  return (
    <div className="ws-board-container">
      {/* Top Strip: Upcoming Deadline Reminders Alert Bar */}
      <UpcomingRemindersStrip
        reminders={state.upcomingReminders}
        loading={state.loading?.reminders}
        onDispatchAll={actions.dispatchAllRemindersAction}
        onSendSingle={actions.sendTaskReminderAction}
      />

      {/* 3-Column Kanban Board */}
      <div className="ws-kanban">
        <KanbanColumn
          title="To Do"
          tasks={todo}
          actions={actions}
          reminderMap={reminderMap}
        />
        <KanbanColumn
          title="In Progress"
          tasks={inProgress}
          actions={actions}
          reminderMap={reminderMap}
        />
        <KanbanColumn
          title="Done"
          tasks={done}
          actions={actions}
          reminderMap={reminderMap}
        />
      </div>
    </div>
  );
}

export default BoardTab;
