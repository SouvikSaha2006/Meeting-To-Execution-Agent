// API client layer for VeriFlow frontend
// Resolves local or cloud backend via centralized config.
import { API_BASE } from '../config/api.js';

const BASE = API_BASE;
export { API_BASE };

/**
 * Core fetch wrapper.
 * Throws { status, detail } on non-2xx responses.
 * Returns parsed JSON on success.
 */
async function request(method, path, body, extraOptions = {}) {
  const options = {
    method,
    headers: { 'Content-Type': 'application/json' },
    ...extraOptions,
  };

  if (body !== undefined) {
    options.body = JSON.stringify(body);
  }

  const res = await fetch(BASE + path, options);

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const err = await res.json();
      detail = err.detail ?? err.message ?? detail;
    } catch (_) {
      // ignore parse errors; keep statusText
    }
    throw { status: res.status, detail };
  }

  // Handle 204 No Content
  const contentType = res.headers.get('content-type') || '';
  if (res.status === 204 || !contentType.includes('application/json')) {
    return null;
  }

  return res.json();
}

// ---------------------------------------------------------------------------
// Health & Analytics
// ---------------------------------------------------------------------------
export const getHealth = () => request('GET', '/api/health');
export const getAnalyticsHealth = () => request('GET', '/api/analytics/health');

// ---------------------------------------------------------------------------
// Ingest
// ---------------------------------------------------------------------------
/** @param {{ title: string, meeting_date: string, raw_transcript: string }} body */
export const ingestMeeting = (body) => request('POST', '/api/meetings/ingest', body);

// ---------------------------------------------------------------------------
// Demo controls
// ---------------------------------------------------------------------------
export const loadMeeting1   = () => request('POST', '/api/demo/load-meeting-1');
export const loadMeeting2   = () => request('POST', '/api/demo/load-meeting-2');
export const resetDemo      = () => request('POST', '/api/demo/seed');

// ---------------------------------------------------------------------------
// Staging queue
// ---------------------------------------------------------------------------
export const getStaging = () => request('GET', '/api/staging');

/**
 * Resolve / patch a staging item.
 * @param {string|number} id
 * @param {{ owner?: string, deadline_iso?: string, title?: string,
 *           conflict_resolution?: 'SUPERSEDE_OLD'|'KEEP_ORIGINAL',
 *           notes?: string }} body
 */
export const resolveItem = (id, body) =>
  request('PATCH', `/api/staging/${id}/resolve`, body);

export const approveItem = (id) =>
  request('POST', `/api/staging/${id}/approve`);

/**
 * @param {string|number} id
 * @param {{ reason?: string }} body
 */
export const rejectItem = (id, body) =>
  request('POST', `/api/staging/${id}/reject`, body);

export const approveAllReady = () =>
  request('POST', '/api/staging/approve-all-ready');

export const getItemBlastRadius = (id) =>
  request('GET', `/api/staging/${id}/blast-radius`);

// ---------------------------------------------------------------------------
// Auto-Nudge & Escalation
// ---------------------------------------------------------------------------
/**
 * @param {{ target_type: 'STAGING_ITEM'|'TASK', target_id: number,
 *           recipient: string, channel: 'slack'|'discord'|'email',
 *           message?: string }} body
 */
export const sendNudge = (body, extraOptions = {}) =>
  request('POST', '/api/actions/send-nudge', body, extraOptions);

// ---------------------------------------------------------------------------
// Proactive Deadline Reminders
// ---------------------------------------------------------------------------
export const getUpcomingReminders = (withinHours = 48) =>
  request('GET', `/api/reminders/upcoming?within_hours=${withinHours}`);

export const dispatchAllReminders = (withinHours = 48) =>
  request('POST', `/api/reminders/dispatch-all?within_hours=${withinHours}`);

export const sendTaskReminder = (taskId, channel = 'webhook') =>
  request('POST', `/api/reminders/${taskId}/send?channel=${channel}`);

export const getReminderLogs = (limit = 50) =>
  request('GET', `/api/reminders/logs?limit=${limit}`);

// ---------------------------------------------------------------------------
// Tasks board
// ---------------------------------------------------------------------------
export const getTasks = () => request('GET', '/api/tasks');

/**
 * @param {string|number} id
 * @param {'TODO'|'IN_PROGRESS'|'DONE'} status
 */
export const updateTaskStatus = (id, status) =>
  request('PATCH', `/api/tasks/${id}/status`, { status });

// ---------------------------------------------------------------------------
// Decisions ledger
// ---------------------------------------------------------------------------
export const getDecisions = () => request('GET', '/api/decisions');

// ---------------------------------------------------------------------------
// Lineage Graph
// ---------------------------------------------------------------------------
export const getLineageGraph = (meetingId) =>
  request('GET', meetingId ? `/api/graph/lineage?meeting_id=${meetingId}` : '/api/graph/lineage');

// ---------------------------------------------------------------------------
// Weekly digest
// ---------------------------------------------------------------------------
export const getWeeklyDigest = () => request('GET', '/api/digest/weekly');

// ---------------------------------------------------------------------------
// Cross-Meeting Organizational Memory Query
// ---------------------------------------------------------------------------
/**
 * @param {string} question
 * @returns {Promise<{ answer: string, citations: Array<{ meeting_title: string, meeting_date: string, speaker: string, quote: string }>, related_task_ids: number[] }>}
 */
export const askMemory = (question) =>
  request('POST', '/api/memory/ask', { question });

// ---------------------------------------------------------------------------
// Payload / meta utilities
// ---------------------------------------------------------------------------

/**
 * Safely parse a staging item's payload_json field.
 * Returns {} on any parse error.
 * @param {{ payload_json?: string }} staging_item
 * @returns {object}
 */
export function parsePayload(staging_item) {
  try {
    return JSON.parse(staging_item?.payload_json) ?? {};
  } catch (_) {
    return {};
  }
}

/**
 * Safely parse a staging item's conflict_meta_json field.
 * Returns {} on any parse error.
 * @param {{ conflict_meta_json?: string }} staging_item
 * @returns {object}
 */
export function parseConflictMeta(staging_item) {
  try {
    return JSON.parse(staging_item?.conflict_meta_json) ?? {};
  } catch (_) {
    return {};
  }
}

/**
 * Safely extract blast radius from a staging item.
 * @param {{ blast_radius?: object, blast_radius_json?: string }} staging_item
 * @returns {object|null}
 */
export function parseBlastRadius(staging_item) {
  if (staging_item?.blast_radius && typeof staging_item.blast_radius === 'object') {
    return staging_item.blast_radius;
  }
  if (staging_item?.blast_radius_json) {
    try {
      return JSON.parse(staging_item.blast_radius_json);
    } catch (_) {
      return null;
    }
  }
  return null;
}
