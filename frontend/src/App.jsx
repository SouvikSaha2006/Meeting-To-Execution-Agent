/* ============================================================
   App.jsx — VeriFlow Root Application
   Autonomous Meeting-to-Execution Agent
   ============================================================ */
import { useEffect, useRef } from 'react';
import { API_BASE } from './config/api.js';
import { VelaHero } from './components/hero/index.js';
import { VeriflowWorkspace } from './components/workspace/index.js';
import './design-tokens.css';
import './App.css';

export default function App() {
  const workspaceRef = useRef(null);

  // Global Keep-Alive Ping: silently ping /api/health every 4 minutes (240,000ms)
  // so Render's free tier backend never goes to sleep while a user or judge has VeriFlow open.
  useEffect(() => {
    const pingHealth = () => {
      fetch(`${API_BASE}/api/health`, { method: 'GET' }).catch(() => {});
    };
    // Initial ping
    pingHealth();
    const intervalId = setInterval(pingHealth, 4 * 60 * 1000);
    return () => clearInterval(intervalId);
  }, []);

  const handleTryDemo = () => {
    document.getElementById('workspace')?.scrollIntoView({ behavior: 'smooth' });
    workspaceRef.current?.runDemo1();
  };

  const handleConflictTest = () => {
    document.getElementById('workspace')?.scrollIntoView({ behavior: 'smooth' });
    workspaceRef.current?.runDemo2();
  };

  const handleNavigateTab = (tabId, filterId) => {
    workspaceRef.current?.switchTab(tabId, filterId);
  };

  return (
    <>
      <VelaHero
        onTryDemo={handleTryDemo}
        onConflictTest={handleConflictTest}
        onNavigateTab={handleNavigateTab}
      />
      <VeriflowWorkspace ref={workspaceRef} />
    </>
  );
}
