// Centralized Smart API Base Resolution for VeriFlow
const RENDER_BACKEND_DEFAULT = 'https://meeting-to-execution-agent-7q5a.onrender.com';

const rawUrl =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) ||
  (typeof window !== 'undefined' &&
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://localhost:8000'
    : RENDER_BACKEND_DEFAULT);

export const API_BASE = (rawUrl || 'http://localhost:8000').replace(/\/+$/, '');

export default API_BASE;
