/* ============================================================
   VeriflowWorkspace.jsx — Root workspace section orchestrator
   ============================================================ */
import React, { useEffect, useState, forwardRef, useImperativeHandle } from 'react';
import { useWorkspace } from './useWorkspace.js';
import { ToastContainer } from './ToastContainer.jsx';
import { IngestTab } from './tabs/IngestTab.jsx';
import { BoardTab } from './tabs/BoardTab.jsx';
import { DecisionsTab } from './tabs/DecisionsTab.jsx';
import { DigestTab } from './tabs/DigestTab.jsx';
import './workspace.css';

const TABS = [
  { id: 'ingest',    label: 'Ingest & Approval Queue', badge: true },
  { id: 'board',     label: 'Execution Board',         badge: false },
  { id: 'decisions', label: 'Decision Memory',         badge: false },
  { id: 'digest',    label: 'Weekly Digest',           badge: false },
];

export const VeriflowWorkspace = forwardRef(function VeriflowWorkspace(props, ref) {
  const { state, dispatch, actions } = useWorkspace();
  const [demo1Loading, setDemo1Loading] = useState(false);
  const [demo2Loading, setDemo2Loading] = useState(false);

  // On mount: load staging queue to populate pending badge
  useEffect(() => {
    actions.loadStaging();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleDemo1() {
    setDemo1Loading(true);
    try {
      actions.switchTab('ingest');
      await actions.runDemo1();
    } finally {
      setDemo1Loading(false);
    }
  }

  async function handleDemo2() {
    setDemo2Loading(true);
    try {
      actions.switchTab('ingest');
      dispatch({ type: 'SET_FILTER', filter: 'conflicts' });
      await actions.runDemo2();
    } finally {
      setDemo2Loading(false);
    }
  }

  function handleReset() {
    if (window.confirm('Reset all demo data? This cannot be undone.')) {
      actions.resetDemo();
    }
  }

  // Expose imperative API for top navigation and hero buttons
  useImperativeHandle(ref, () => ({
    switchTab: (tabId, filterId) => {
      actions.switchTab(tabId);
      if (filterId) {
        dispatch({ type: 'SET_FILTER', filter: filterId });
      }
    },
    runDemo1: handleDemo1,
    runDemo2: handleDemo2,
    resetDemo: handleReset,
  }));

  function renderContent() {
    switch (state.activeTab) {
      case 'ingest':
        return <IngestTab state={state} actions={actions} />;
      case 'board':
        return <BoardTab state={state} actions={actions} />;
      case 'decisions':
        return <DecisionsTab state={state} actions={actions} />;
      case 'digest':
        return <DigestTab state={state} actions={actions} />;
      default:
        return <IngestTab state={state} actions={actions} />;
    }
  }

  return (
    <section id="workspace" className="veriflow-workspace">
      {/* Sticky sub-header */}
      <div className="ws-header">
        {/* Left: label + tab pills */}
        <div className="ws-header-left">
          <span className="ws-workspace-label">VeriFlow Workspace</span>
          <div className="ws-tabs">
            {TABS.map((tab) => {
              const isActive = state.activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  className={`ws-tab ${isActive ? 'active' : 'inactive'}`}
                  onClick={() => actions.switchTab(tab.id)}
                  type="button"
                >
                  {tab.label}
                  {tab.badge && state.pendingCount > 0 && (
                    <span className={`ws-tab-badge ${isActive ? 'active' : ''}`}>
                      {state.pendingCount}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: demo control bar */}
        <div className="ws-demo-bar">
          <button
            className="ws-demo-btn"
            onClick={handleDemo1}
            disabled={demo1Loading || demo2Loading}
            type="button"
          >
            {demo1Loading ? 'Loading…' : '1. Load Sprint Kickoff (Nov 14)'}
          </button>
          <button
            className="ws-demo-btn"
            onClick={handleDemo2}
            disabled={demo1Loading || demo2Loading}
            type="button"
          >
            {demo2Loading ? 'Loading…' : '2. Load Tech Sync (Nov 21 — Conflicts)'}
          </button>
          <button
            className="ws-demo-btn reset"
            onClick={handleReset}
            disabled={demo1Loading || demo2Loading}
            type="button"
          >
            Reset Demo
          </button>
        </div>
      </div>

      {/* Tab content */}
      <div className="ws-content">
        {renderContent()}
      </div>

      {/* Anchor targets for direct linking */}
      <div id="conflict-guard" aria-hidden="true" style={{ position: 'relative', top: -100 }} />
      <div id="decision-log"   aria-hidden="true" style={{ position: 'relative', top: -100 }} />
      <div id="weekly-digest"  aria-hidden="true" style={{ position: 'relative', top: -100 }} />

      {/* Toast notifications */}
      <ToastContainer
        toasts={state.toasts}
        onRemove={(id) => dispatch({ type: 'REMOVE_TOAST', id })}
      />
    </section>
  );
});
