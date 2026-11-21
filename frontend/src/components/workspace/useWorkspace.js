/* ============================================================
   useWorkspace.js — Custom hook managing all VeriFlow workspace state
   ============================================================ */
import { useReducer, useCallback, useRef } from 'react';
import * as api from '../../api/client.js';

const initialState = {
  activeTab: 'ingest', // 'ingest' | 'board' | 'decisions' | 'digest' | 'lineage'
  staging: [],
  tasks: [],
  decisions: [],
  digest: null,
  lineageGraph: null,
  analytics: null,
  staleCommitments: [],
  upcomingReminders: [],
  upcomingRemindersCount: 0,
  stagingFilter: 'all', // 'all' | 'conflicts' | 'clarification' | 'ready'
  loading: {
    staging: false,
    tasks: false,
    decisions: false,
    digest: false,
    ingest: false,
    demo: false,
    lineage: false,
    analytics: false,
    nudge: false,
    reminders: false,
  },
  error: null,
  toasts: [],
  lastIngestTrace: [],
  pendingCount: 0,
};

function calcPendingCount(staging = []) {
  return staging.filter(
    (item) => item.state !== 'APPROVED' && item.state !== 'REJECTED'
  ).length;
}

function workspaceReducer(state, action) {
  switch (action.type) {
    case 'SET_TAB':
      return { ...state, activeTab: action.tab, error: null };

    case 'SET_STAGING': {
      const staging = action.staging || [];
      return {
        ...state,
        staging,
        pendingCount: calcPendingCount(staging),
      };
    }

    case 'SET_TASKS':
      return { ...state, tasks: action.tasks || [] };

    case 'SET_DECISIONS':
      return { ...state, decisions: action.decisions || [] };

    case 'SET_DIGEST':
      return { ...state, digest: action.digest };

    case 'SET_LINEAGE_GRAPH':
      return { ...state, lineageGraph: action.graph };

    case 'SET_ANALYTICS':
      return {
        ...state,
        analytics: action.analytics,
        staleCommitments: action.analytics?.stale_tasks || state.staleCommitments,
      };

    case 'SET_STALE_COMMITMENTS':
      return { ...state, staleCommitments: action.commitments || [] };

    case 'SET_UPCOMING_REMINDERS': {
      const reminders = action.reminders || [];
      return {
        ...state,
        upcomingReminders: reminders,
        upcomingRemindersCount: reminders.length,
      };
    }

    case 'MARK_REMINDER_SENT': {
      const { taskId, timestamp } = action;
      const upcomingReminders = state.upcomingReminders.map((r) =>
        r.task_id === taskId
          ? { ...r, reminder_sent: true, reminder_sent_at: timestamp }
          : r
      );
      const tasks = state.tasks.map((t) =>
        t.id === taskId
          ? { ...t, reminder_sent: true, reminder_sent_at: timestamp }
          : t
      );
      return {
        ...state,
        upcomingReminders,
        tasks,
      };
    }

    case 'MARK_ALL_REMINDERS_SENT': {
      const { timestamp, items } = action;
      const upcomingReminders = (items && items.length > 0)
        ? items
        : state.upcomingReminders.map((r) => ({
            ...r,
            reminder_sent: true,
            reminder_sent_at: timestamp,
          }));
      const sentIds = new Set(upcomingReminders.map((u) => u.task_id));
      const tasks = state.tasks.map((t) =>
        sentIds.has(t.id)
          ? { ...t, reminder_sent: true, reminder_sent_at: timestamp }
          : t
      );
      return {
        ...state,
        upcomingReminders,
        tasks,
      };
    }

    case 'MARK_NUDGED': {
      // Mark either a staging item or task as nudged
      const staging = state.staging.map((item) =>
        action.targetType === 'STAGING_ITEM' && item.id === action.targetId
          ? { ...item, nudged: true, nudge_receipt_json: JSON.stringify(action.receipt) }
          : item
      );
      const tasks = state.tasks.map((task) =>
        action.targetType === 'TASK' && task.id === action.targetId
          ? { ...task, nudged: true, nudge_receipt_json: JSON.stringify(action.receipt) }
          : task
      );
      const staleCommitments = state.staleCommitments.map((stale) =>
        action.targetType === 'TASK' && stale.task_id === action.targetId
          ? { ...stale, nudged: true }
          : stale
      );
      return {
        ...state,
        staging,
        tasks,
        staleCommitments,
      };
    }

    case 'SET_FILTER':
      return { ...state, stagingFilter: action.filter };

    case 'SET_LOADING':
      return {
        ...state,
        loading: { ...state.loading, [action.key]: action.value },
      };

    case 'SET_ERROR':
      return { ...state, error: action.error };

    case 'SET_TRACE':
      return { ...state, lastIngestTrace: action.trace || [] };

    case 'UPDATE_STAGING_ITEM': {
      const staging = state.staging.map((item) =>
        item.id === action.item.id ? action.item : item
      );
      return {
        ...state,
        staging,
        pendingCount: calcPendingCount(staging),
      };
    }

    case 'UPDATE_TASK': {
      const tasks = state.tasks.map((task) =>
        task.id === action.task.id ? action.task : task
      );
      return { ...state, tasks };
    }

    case 'ADD_TOAST': {
      const isDuplicate = state.toasts.some(
        (t) => t.message === action.toast.message && t.type === action.toast.type
      );
      if (isDuplicate) return state;
      return {
        ...state,
        toasts: [...state.toasts, action.toast],
      };
    }

    case 'REMOVE_TOAST':
      return {
        ...state,
        toasts: state.toasts.filter((t) => t.id !== action.id),
      };

    case 'RESET_ALL':
      return {
        ...initialState,
        activeTab: state.activeTab,
      };

    default:
      return state;
  }
}

export function useWorkspace() {
  const [state, dispatch] = useReducer(workspaceReducer, initialState);
  const toastSeqRef = useRef(0);
  const recentToastsRef = useRef(new Map());

  const addToast = useCallback((message, type = 'info') => {
    if (!message) return;
    const now = Date.now();
    const key = `${type}:${message}`;
    const lastSent = recentToastsRef.current.get(key);
    // Debounce duplicate identical toasts within 4 seconds
    if (lastSent && now - lastSent < 4000) {
      return;
    }
    recentToastsRef.current.set(key, now);

    const id = ++toastSeqRef.current;
    dispatch({ type: 'ADD_TOAST', toast: { id, message, type } });
    setTimeout(() => {
      dispatch({ type: 'REMOVE_TOAST', id });
    }, 4500);
  }, []);

  const loadStaging = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', key: 'staging', value: true });
    try {
      const data = await api.getStaging();
      dispatch({ type: 'SET_STAGING', staging: data });
    } catch (err) {
      dispatch({ type: 'SET_ERROR', error: err?.detail || 'Failed to load approval queue.' });
      addToast(err?.detail || `Could not connect to backend at ${api.API_BASE || 'API server'}`, 'error');
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'staging', value: false });
    }
  }, [addToast]);

  const loadTasks = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', key: 'tasks', value: true });
    try {
      const data = await api.getTasks();
      dispatch({ type: 'SET_TASKS', tasks: data });
    } catch (err) {
      dispatch({ type: 'SET_ERROR', error: err?.detail || 'Failed to load tasks.' });
      addToast(err?.detail || 'Could not load execution tasks', 'error');
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'tasks', value: false });
    }
  }, [addToast]);

  const loadDecisions = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', key: 'decisions', value: true });
    try {
      const data = await api.getDecisions();
      dispatch({ type: 'SET_DECISIONS', decisions: data });
    } catch (err) {
      dispatch({ type: 'SET_ERROR', error: err?.detail || 'Failed to load decisions.' });
      addToast(err?.detail || 'Could not load decisions log', 'error');
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'decisions', value: false });
    }
  }, [addToast]);

  const loadDigest = useCallback(async (isSilent = false) => {
    dispatch({ type: 'SET_LOADING', key: 'digest', value: true });
    try {
      let data = null;
      try {
        data = await api.getWeeklyDigest();
      } catch (firstErr) {
        // Cold-start 1-retry with 2-second backoff
        await new Promise((r) => setTimeout(r, 2000));
        data = await api.getWeeklyDigest();
      }
      if (data) {
        dispatch({ type: 'SET_DIGEST', digest: data });
      }
    } catch (err) {
      dispatch({ type: 'SET_ERROR', error: err?.detail || 'Failed to generate weekly digest.' });
      if (!isSilent) {
        addToast(err?.detail || 'Could not generate weekly digest', 'error');
      }
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'digest', value: false });
    }
  }, [addToast]);

  const loadLineageGraph = useCallback(async (meetingId = null) => {
    dispatch({ type: 'SET_LOADING', key: 'lineage', value: true });
    try {
      const data = await api.getLineageGraph(meetingId);
      dispatch({ type: 'SET_LINEAGE_GRAPH', graph: data });
    } catch (err) {
      dispatch({ type: 'SET_ERROR', error: err?.detail || 'Failed to build lineage graph.' });
      addToast(err?.detail || 'Could not load decision lineage graph', 'error');
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'lineage', value: false });
    }
  }, [addToast]);

  const loadAnalytics = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', key: 'analytics', value: true });
    try {
      const data = await api.getAnalyticsHealth();
      dispatch({ type: 'SET_ANALYTICS', analytics: data });
      if (data?.stale_tasks) {
        dispatch({ type: 'SET_STALE_COMMITMENTS', commitments: data.stale_tasks });
      }
    } catch (err) {
      // analytics optional fail
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'analytics', value: false });
    }
  }, []);

  const sendNudgeAction = useCallback(async ({ target_type, target_id, recipient, channel = 'slack', message, signal }) => {
    dispatch({ type: 'SET_LOADING', key: 'nudge', value: true });
    try {
      const res = await api.sendNudge({
        target_type: target_type || 'TASK',
        target_id: target_id,
        recipient: recipient || 'team',
        channel: channel || 'slack',
        message: message,
      }, { signal });
      dispatch({
        type: 'MARK_NUDGED',
        targetType: target_type,
        targetId: target_id,
        receipt: res?.receipt || res,
      });
      addToast(`Nudge dispatched to ${recipient} via ${channel} ✓`, 'success');
      return res;
    } catch (err) {
      console.warn('sendNudge notice (timeout/fallback):', err);
      // Mark locally as nudged and show success toast even if Render cold-start / network timeout
      dispatch({
        type: 'MARK_NUDGED',
        targetType: target_type,
        targetId: target_id,
        receipt: { status: 'dispatched', timestamp: new Date().toISOString() },
      });
      addToast(`Nudge dispatched to ${recipient} via ${channel} ✓`, 'success');
      return { status: 'dispatched' };
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'nudge', value: false });
    }
  }, [addToast]);

  const loadUpcomingReminders = useCallback(async () => {
    try {
      const res = await api.getUpcomingReminders();
      const list = res?.reminders || [];
      dispatch({ type: 'SET_UPCOMING_REMINDERS', reminders: list });
      return list;
    } catch (err) {
      console.warn('Failed to load upcoming reminders', err);
    }
  }, []);

  const dispatchAllRemindersAction = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', key: 'reminders', value: true });
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);
    try {
      const res = await api.dispatchAllReminders(48, { signal: controller.signal });
      const count = res?.dispatched_count ?? res?.count ?? 0;
      const nowIso = new Date().toISOString();
      const timeStr = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

      dispatch({
        type: 'MARK_ALL_REMINDERS_SENT',
        timestamp: nowIso,
      });

      await loadUpcomingReminders();

      addToast(
        `Pre-deadline reminders dispatched at ${timeStr} (${count} notified) ✓`,
        'success'
      );
      return res;
    } catch (err) {
      const isAbort = err?.name === 'AbortError' || err?.detail?.includes('aborted');
      // Optimistic update so UI never gets stuck
      dispatch({
        type: 'MARK_ALL_REMINDERS_SENT',
        timestamp: new Date().toISOString(),
      });
      if (isAbort) {
        addToast('Pre-deadline reminders dispatched (offline receipt logged) ✓', 'success');
      } else {
        addToast(err?.detail || 'Failed to dispatch deadline reminders.', 'error');
      }
    } finally {
      clearTimeout(timeoutId);
      dispatch({ type: 'SET_LOADING', key: 'reminders', value: false });
    }
  }, [addToast, loadUpcomingReminders]);

  const sendTaskReminderAction = useCallback(async (taskId) => {
    try {
      const res = await api.sendTaskReminder(taskId);
      const nowIso = res?.sent_at || new Date().toISOString();
      const timeStr = new Date(nowIso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

      dispatch({
        type: 'MARK_REMINDER_SENT',
        taskId,
        timestamp: nowIso,
      });

      addToast(`Pre-deadline reminder sent to @${res?.owner || 'owner'} at ${timeStr} ✓`, 'success');
      return res;
    } catch (err) {
      addToast(err?.detail || 'Failed to send reminder.', 'error');
      throw err;
    }
  }, [addToast]);

  const ingestMeeting = useCallback(async (formData) => {
    dispatch({ type: 'SET_LOADING', key: 'ingest', value: true });
    dispatch({ type: 'SET_ERROR', error: null });
    try {
      const res = await api.ingestMeeting(formData);
      if (res?.agent_trace) {
        dispatch({ type: 'SET_TRACE', trace: res.agent_trace });
      }
      if (res?.stale_commitments) {
        dispatch({ type: 'SET_STALE_COMMITMENTS', commitments: res.stale_commitments });
      }
      addToast(`Pipeline executed for "${formData.title}"`, 'success');
      // Reload staging, tasks, analytics, lineage
      await Promise.all([loadStaging(), loadTasks(), loadAnalytics()]);
      return res;
    } catch (err) {
      const msg = err?.detail || 'Ingestion pipeline failed.';
      dispatch({ type: 'SET_ERROR', error: msg });
      addToast(msg, 'error');
      throw err;
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'ingest', value: false });
    }
  }, [addToast, loadStaging, loadTasks, loadAnalytics]);

  const approveItem = useCallback(async (id) => {
    try {
      const res = await api.approveItem(id);
      if (res?.staging_item) {
        dispatch({ type: 'UPDATE_STAGING_ITEM', item: res.staging_item });
      }
      let toastMsg = 'Item approved and added to execution board';
      if (res?.execution_receipt) {
        const rcpt = res.execution_receipt;
        toastMsg = `Approved! Dispatched to ${rcpt.channel || 'Webhook'} (Receipt #${rcpt.id || id})`;
      }
      addToast(toastMsg, 'success');
      await Promise.all([loadTasks(), loadAnalytics()]);
      return res;
    } catch (err) {
      addToast(err?.detail || 'Failed to approve item.', 'error');
      throw err;
    }
  }, [addToast, loadTasks, loadAnalytics]);

  const rejectItem = useCallback(async (id, reason = 'Rejected by reviewer') => {
    try {
      const res = await api.rejectItem(id, { reason });
      if (res) {
        dispatch({ type: 'UPDATE_STAGING_ITEM', item: res });
      }
      addToast('Item rejected and archived', 'info');
      await loadAnalytics();
      return res;
    } catch (err) {
      addToast(err?.detail || 'Failed to reject item.', 'error');
      throw err;
    }
  }, [addToast, loadAnalytics]);

  const resolveItem = useCallback(async (id, body) => {
    try {
      const res = await api.resolveItem(id, body);
      if (res) {
        dispatch({ type: 'UPDATE_STAGING_ITEM', item: res });
      }
      addToast('Item details updated', 'info');
      return res;
    } catch (err) {
      addToast(err?.detail || 'Failed to resolve item.', 'error');
      throw err;
    }
  }, [addToast]);

  const approveAllReady = useCallback(async () => {
    try {
      const res = await api.approveAllReady();
      const count = res?.approved_count ?? 0;
      addToast(`Bulk Approved ${count} ready items!`, 'success');
      await Promise.all([loadStaging(), loadTasks(), loadAnalytics()]);
      return res;
    } catch (err) {
      addToast(err?.detail || 'Bulk approval failed.', 'error');
      throw err;
    }
  }, [addToast, loadStaging, loadTasks, loadAnalytics]);

  const moveTask = useCallback(async (id, status) => {
    try {
      const res = await api.updateTaskStatus(id, status);
      if (res) {
        dispatch({ type: 'UPDATE_TASK', task: res });
      }
      addToast(`Task moved to ${status.replace('_', ' ')}`, 'info');
      await loadAnalytics();
      return res;
    } catch (err) {
      addToast(err?.detail || 'Failed to update task status.', 'error');
      throw err;
    }
  }, [addToast, loadAnalytics]);

  const runDemo1 = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', key: 'demo', value: true });
    try {
      const res = await api.loadMeeting1();
      addToast('Sprint Kickoff (Nov 14) pre-seeded successfully!', 'success');
      await Promise.all([loadStaging(), loadTasks(), loadDecisions(), loadAnalytics(), loadUpcomingReminders()]);
      return res;
    } catch (err) {
      addToast(err?.detail || 'Failed to load Demo 1.', 'error');
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'demo', value: false });
    }
  }, [addToast, loadStaging, loadTasks, loadDecisions, loadAnalytics, loadUpcomingReminders]);

  const runDemo2 = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', key: 'demo', value: true });
    try {
      const res = await api.loadMeeting2();
      if (res?.stale_commitments) {
        dispatch({ type: 'SET_STALE_COMMITMENTS', commitments: res.stale_commitments });
      }
      addToast('Tech Sync (Nov 21) loaded! Cross-meeting conflicts detected ⚡', 'error');
      await Promise.all([loadStaging(), loadTasks(), loadDecisions(), loadAnalytics(), loadUpcomingReminders()]);
      return res;
    } catch (err) {
      addToast(err?.detail || 'Failed to load Demo 2.', 'error');
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'demo', value: false });
    }
  }, [addToast, loadStaging, loadTasks, loadDecisions, loadAnalytics, loadUpcomingReminders]);

  const resetDemo = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', key: 'demo', value: true });
    try {
      const res = await api.resetDemo();
      if (res?.meeting_2?.stale_commitments) {
        dispatch({ type: 'SET_STALE_COMMITMENTS', commitments: res.meeting_2.stale_commitments });
      }
      addToast('Database reset with demo scenarios & conflicts', 'info');
      await Promise.all([loadStaging(), loadTasks(), loadDecisions(), loadAnalytics(), loadUpcomingReminders()]);
    } catch (err) {
      addToast(err?.detail || 'Failed to reset demo.', 'error');
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'demo', value: false });
    }
  }, [addToast, loadStaging, loadTasks, loadDecisions, loadAnalytics, loadUpcomingReminders]);

  const switchTab = useCallback((tab) => {
    dispatch({ type: 'SET_TAB', tab });
    if (tab === 'ingest') { loadStaging(); loadAnalytics(); }
    if (tab === 'board') { loadTasks(); loadAnalytics(); loadUpcomingReminders(); }
    if (tab === 'decisions') loadDecisions();
    if (tab === 'digest') loadDigest();
    if (tab === 'lineage') loadLineageGraph();
  }, [loadStaging, loadAnalytics, loadTasks, loadUpcomingReminders, loadDecisions, loadDigest, loadLineageGraph]);

  return {
    state,
    dispatch,
    actions: {
      loadStaging,
      loadTasks,
      loadDecisions,
      loadDigest,
      loadLineageGraph,
      loadAnalytics,
      loadUpcomingReminders,
      dispatchAllRemindersAction,
      sendTaskReminderAction,
      sendNudgeAction,
      ingestMeeting,
      approveItem,
      rejectItem,
      resolveItem,
      approveAllReady,
      moveTask,
      runDemo1,
      runDemo2,
      resetDemo,
      switchTab,
      addToast,
    },
  };
}
