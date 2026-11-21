/* ============================================================
   useWorkspace.js — Custom hook managing all VeriFlow workspace state
   ============================================================ */
import { useReducer, useCallback, useRef } from 'react';
import * as api from '../../api/client.js';

const initialState = {
  activeTab: 'ingest', // 'ingest' | 'board' | 'decisions' | 'digest'
  staging: [],
  tasks: [],
  decisions: [],
  digest: null,
  stagingFilter: 'all', // 'all' | 'conflicts' | 'clarification' | 'ready'
  loading: {
    staging: false,
    tasks: false,
    decisions: false,
    digest: false,
    ingest: false,
    demo: false,
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

    case 'ADD_TOAST':
      return {
        ...state,
        toasts: [...state.toasts, action.toast],
      };

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

  const addToast = useCallback((message, type = 'info') => {
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
      addToast(err?.detail || 'Could not connect to backend at localhost:8000', 'error');
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

  const loadDigest = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', key: 'digest', value: true });
    try {
      const data = await api.getWeeklyDigest();
      dispatch({ type: 'SET_DIGEST', digest: data });
    } catch (err) {
      dispatch({ type: 'SET_ERROR', error: err?.detail || 'Failed to generate weekly digest.' });
      addToast(err?.detail || 'Could not generate weekly digest', 'error');
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'digest', value: false });
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
      addToast(`Pipeline executed for "${formData.title}"`, 'success');
      // Reload staging & tasks
      await loadStaging();
      await loadTasks();
      return res;
    } catch (err) {
      const msg = err?.detail || 'Ingestion pipeline failed.';
      dispatch({ type: 'SET_ERROR', error: msg });
      addToast(msg, 'error');
      throw err;
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'ingest', value: false });
    }
  }, [addToast, loadStaging, loadTasks]);

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
      await loadTasks();
      return res;
    } catch (err) {
      addToast(err?.detail || 'Failed to approve item.', 'error');
      throw err;
    }
  }, [addToast, loadTasks]);

  const rejectItem = useCallback(async (id, reason = 'Rejected by reviewer') => {
    try {
      const res = await api.rejectItem(id, { reason });
      if (res) {
        dispatch({ type: 'UPDATE_STAGING_ITEM', item: res });
      }
      addToast('Item rejected and archived', 'info');
      return res;
    } catch (err) {
      addToast(err?.detail || 'Failed to reject item.', 'error');
      throw err;
    }
  }, [addToast]);

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
      await loadStaging();
      await loadTasks();
      return res;
    } catch (err) {
      addToast(err?.detail || 'Bulk approval failed.', 'error');
      throw err;
    }
  }, [addToast, loadStaging, loadTasks]);

  const moveTask = useCallback(async (id, status) => {
    try {
      const res = await api.updateTaskStatus(id, status);
      if (res) {
        dispatch({ type: 'UPDATE_TASK', task: res });
      }
      addToast(`Task moved to ${status.replace('_', ' ')}`, 'info');
      return res;
    } catch (err) {
      addToast(err?.detail || 'Failed to update task status.', 'error');
      throw err;
    }
  }, [addToast]);

  const runDemo1 = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', key: 'demo', value: true });
    try {
      const res = await api.loadMeeting1();
      addToast('Sprint Kickoff (Nov 14) pre-seeded successfully!', 'success');
      await loadStaging();
      await loadTasks();
      await loadDecisions();
      return res;
    } catch (err) {
      addToast(err?.detail || 'Failed to load Demo 1.', 'error');
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'demo', value: false });
    }
  }, [addToast, loadStaging, loadTasks, loadDecisions]);

  const runDemo2 = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', key: 'demo', value: true });
    try {
      const res = await api.loadMeeting2();
      addToast('Tech Sync (Nov 21) loaded! Cross-meeting conflicts detected ⚡', 'error');
      await loadStaging();
      await loadTasks();
      await loadDecisions();
      return res;
    } catch (err) {
      addToast(err?.detail || 'Failed to load Demo 2.', 'error');
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'demo', value: false });
    }
  }, [addToast, loadStaging, loadTasks, loadDecisions]);

  const resetDemo = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', key: 'demo', value: true });
    try {
      await api.resetDemo();
      dispatch({ type: 'RESET_ALL' });
      addToast('Database reset to clean state', 'info');
      await loadStaging();
      await loadTasks();
      await loadDecisions();
    } catch (err) {
      addToast(err?.detail || 'Failed to reset demo.', 'error');
    } finally {
      dispatch({ type: 'SET_LOADING', key: 'demo', value: false });
    }
  }, [addToast, loadStaging, loadTasks, loadDecisions]);

  const switchTab = useCallback((tab) => {
    dispatch({ type: 'SET_TAB', tab });
    if (tab === 'ingest') loadStaging();
    if (tab === 'board') loadTasks();
    if (tab === 'decisions') loadDecisions();
    if (tab === 'digest') loadDigest();
  }, [loadStaging, loadTasks, loadDecisions, loadDigest]);

  return {
    state,
    dispatch,
    actions: {
      loadStaging,
      loadTasks,
      loadDecisions,
      loadDigest,
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
