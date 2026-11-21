/* ============================================================
   App.jsx — VeriFlow Root Application
   Autonomous Meeting-to-Execution Agent
   ============================================================ */
import { useRef } from 'react';
import { VelaHero } from './components/hero/index.js';
import { VeriflowWorkspace } from './components/workspace/index.js';
import './design-tokens.css';
import './App.css';

export default function App() {
  const workspaceRef = useRef(null);

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
