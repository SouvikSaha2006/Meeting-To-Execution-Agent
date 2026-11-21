/* ============================================================
   DecisionsTab.jsx — Tab 3: Decision Memory Log
   ============================================================ */
import React, { useEffect, useState } from 'react';

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

function DecisionCard({ decision }) {
  const [showQuote, setShowQuote] = useState(false);
  const isSuperseded = decision.status === 'SUPERSEDED';

  return (
    <div className={`ws-decision-row ${isSuperseded ? 'superseded' : ''}`}>
      <div style={{ flexShrink: 0, paddingTop: 2 }}>
        {isSuperseded ? (
          <span className="ws-badge ws-badge-rejected">SUPERSEDED</span>
        ) : (
          <span className="ws-badge ws-badge-ready">ACTIVE</span>
        )}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="ws-decision-statement">
          {decision.statement}
        </div>

        <div className="ws-decision-meta">
          <span className="ws-badge ws-badge-low" style={{ marginRight: 6 }}>
            #{decision.topic_key}
          </span>
          {decision.decided_by && (
            <span style={{ marginRight: 10 }}>
              Decided by: <strong>{decision.decided_by}</strong>
            </span>
          )}
          {decision.meeting_title && (
            <span style={{ marginRight: 10 }}>
              Meeting: <em>{decision.meeting_title}</em> ({fmtDate(decision.meeting_date)})
            </span>
          )}
          {decision.confidence && (
            <span className={`ws-badge ws-badge-${(decision.confidence || '').toLowerCase()}`}>
              {decision.confidence} Confidence
            </span>
          )}
        </div>

        {isSuperseded && decision.superseded_by_id && (
          <div className="ws-superseded-link" style={{ marginTop: 6 }}>
            ↳ Superseded by decision #{decision.superseded_by_id}
          </div>
        )}

        {decision.verbatim_quote && (
          <div style={{ marginTop: 8 }}>
            <button
              type="button"
              className="ws-btn-sm"
              style={{ padding: '2px 8px', height: 22, fontSize: 11 }}
              onClick={() => setShowQuote(!showQuote)}
            >
              {showQuote ? '▲ Hide Quote' : '▼ View Verbatim Quote'}
            </button>
            {showQuote && (
              <div className="ws-quote-box" style={{ marginTop: 6 }}>
                "{decision.verbatim_quote}"
              </div>
            )}
          </div>
        )}
      </div>

      <div style={{ flexShrink: 0, textAlign: 'right', fontSize: 11, color: 'rgba(13,13,12,0.42)' }}>
        {fmtDate(decision.created_at)}
      </div>
    </div>
  );
}

export function DecisionsTab({ state, actions }) {
  useEffect(() => {
    if (state.decisions.length === 0) {
      actions.loadDecisions();
    }
  }, [state.decisions.length, actions]);

  const activeDecisions = state.decisions.filter((d) => d.status !== 'SUPERSEDED');
  const supersededDecisions = state.decisions.filter((d) => d.status === 'SUPERSEDED');

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 600, letterSpacing: '-0.02em', color: '#0D0D0C' }}>
            Decision Memory Log
          </h2>
          <p style={{ fontSize: 13, color: 'rgba(13,13,12,0.56)', marginTop: 2 }}>
            Immutable team decision registry with full cross-meeting lineage and supersession tracking.
          </p>
        </div>
        <button
          className="ws-btn ws-btn-sm"
          onClick={() => actions.loadDecisions()}
          disabled={state.loading.decisions}
        >
          {state.loading.decisions ? 'Refreshing…' : '↻ Refresh Ledger'}
        </button>
      </div>

      {state.loading.decisions && state.decisions.length === 0 ? (
        <div className="ws-loading">
          <div className="ws-spinner" style={{ margin: '0 auto 12px' }} />
          Loading decision memory...
        </div>
      ) : state.decisions.length === 0 ? (
        <div className="ws-empty">
          <div className="ws-empty-icon">📜</div>
          <div className="ws-empty-text">No decisions committed yet.</div>
          <p style={{ fontSize: 12, color: 'rgba(13,13,12,0.4)', marginTop: 6 }}>
            Run the agent pipeline or load a demo meeting to populate the decision memory.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
          {/* Active decisions */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'rgba(13,13,12,0.6)' }}>
                Active Decisions
              </span>
              <span className="ws-badge ws-badge-ready">{activeDecisions.length}</span>
            </div>

            {activeDecisions.length === 0 ? (
              <div style={{ fontSize: 13, color: 'rgba(13,13,12,0.4)', fontStyle: 'italic', padding: '12px 0' }}>
                No active decisions currently.
              </div>
            ) : (
              <div className="ws-ledger">
                {activeDecisions.map((d) => (
                  <DecisionCard key={d.id} decision={d} />
                ))}
              </div>
            )}
          </div>

          {/* Superseded decisions */}
          {supersededDecisions.length > 0 && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'rgba(13,13,12,0.45)' }}>
                  Superseded History
                </span>
                <span className="ws-badge ws-badge-rejected">{supersededDecisions.length}</span>
              </div>
              <div className="ws-ledger">
                {supersededDecisions.map((d) => (
                  <DecisionCard key={d.id} decision={d} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
