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

function TaskCard({ task, actions }) {
  const receipt = parseReceipt(task.external_execution_receipt_json);

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

function KanbanColumn({ title, tasks, actions }) {
  return (
    <div className="ws-kanban-col">
      <div className="ws-kanban-col-header">
        <span>{title}</span>
        <span className="ws-tab-badge">{tasks.length}</span>
      </div>
      {tasks.length === 0 ? (
        <p className="ws-kanban-empty">Nothing here yet</p>
      ) : (
        tasks.map(task => (
          <TaskCard key={task.id} task={task} actions={actions} />
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (state.loading?.tasks) {
    return (
      <div className="ws-loading-state">
        <div className="ws-spinner" />
        <span>Loading tasks…</span>
      </div>
    );
  }

  const todo = state.tasks.filter(t => t.status === 'TODO');
  const inProgress = state.tasks.filter(t => t.status === 'IN_PROGRESS');
  const done = state.tasks.filter(t => t.status === 'DONE');

  return (
    <div>
      <div className="ws-kanban">
        <KanbanColumn title="To Do" tasks={todo} actions={actions} />
        <KanbanColumn title="In Progress" tasks={inProgress} actions={actions} />
        <KanbanColumn title="Done" tasks={done} actions={actions} />
      </div>
    </div>
  );
}
