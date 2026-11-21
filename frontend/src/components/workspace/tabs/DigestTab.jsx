/* ============================================================
   DigestTab.jsx — Tab 4: Weekly Executive Digest
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

export function DigestTab({ state, actions }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!state.digest) {
      actions.loadDigest();
    }
  }, [state.digest, actions]);

  async function handleCopy() {
    if (!state.digest?.markdown) return;
    try {
      await navigator.clipboard.writeText(state.digest.markdown);
      setCopied(true);
      actions.addToast('Executive digest copied to clipboard!', 'success');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      actions.addToast('Failed to copy to clipboard.', 'error');
    }
  }

  const digest = state.digest;

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 600, letterSpacing: '-0.02em', color: '#0D0D0C' }}>
            Weekly Executive Digest
          </h2>
          <p style={{ fontSize: 13, color: 'rgba(13,13,12,0.56)', marginTop: 2 }}>
            {digest?.period ? `Coverage: ${digest.period} · ` : ''}
            {digest?.generated_at ? `Generated: ${fmtDate(digest.generated_at)}` : 'Live cross-meeting rollup for leadership'}
          </p>
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <button
            className="ws-btn ws-btn-sm"
            onClick={() => actions.loadDigest()}
            disabled={state.loading.digest}
          >
            {state.loading.digest ? 'Generating…' : '↻ Regenerate'}
          </button>
          <button
            className="ws-btn ws-btn-sm ws-btn-approve"
            onClick={handleCopy}
            disabled={!digest?.markdown}
          >
            {copied ? '✓ Copied!' : '📋 Copy Executive Digest'}
          </button>
        </div>
      </div>

      {state.loading.digest && !digest ? (
        <div className="ws-loading">
          <div className="ws-spinner" style={{ margin: '0 auto 12px' }} />
          Synthesizing cross-meeting weekly rollup...
        </div>
      ) : !digest || !digest.owners || digest.owners.length === 0 ? (
        <div className="ws-empty">
          <div className="ws-empty-icon">📊</div>
          <div className="ws-empty-text">No active commitments in this period.</div>
          <p style={{ fontSize: 12, color: 'rgba(13,13,12,0.4)', marginTop: 6 }}>
            Ingest meeting transcripts or load demo data to generate an automated executive summary.
          </p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)', gap: 24, alignItems: 'start' }}>
          {/* Left Column: Owner Progress Cards */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'rgba(13,13,12,0.6)' }}>
              Individual Accountability Matrix ({digest.owners.length} Owners)
            </div>

            {digest.owners.map((o) => {
              const initial = (o.owner || '?').charAt(0).toUpperCase();
              return (
                <div key={o.owner} className="ws-card ws-digest-owner-card" style={{ padding: 20 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
                    <div style={{
                      width: 34,
                      height: 34,
                      borderRadius: '50%',
                      background: '#F4EBC6',
                      border: '1.4px solid #0D0D0C',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontWeight: 600,
                      fontSize: 14,
                    }}>
                      {initial}
                    </div>
                    <div>
                      <div className="ws-digest-owner-name" style={{ marginBottom: 0 }}>{o.owner}</div>
                      <div style={{ fontSize: 11, color: 'rgba(13,13,12,0.46)' }}>
                        {o.completed_tasks?.length || 0} done · {o.newly_assigned?.length || 0} active · {o.upcoming_deadlines?.length || 0} upcoming
                      </div>
                    </div>
                  </div>

                  {/* Completed tasks */}
                  {o.completed_tasks && o.completed_tasks.length > 0 && (
                    <div>
                      <div className="ws-digest-section-label" style={{ color: '#3FB874' }}>✓ Completed</div>
                      {o.completed_tasks.map((t, idx) => (
                        <div key={idx} className="ws-digest-item">
                          • {t.title || t}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Newly assigned */}
                  {o.newly_assigned && o.newly_assigned.length > 0 && (
                    <div>
                      <div className="ws-digest-section-label" style={{ color: '#F2772F' }}>⚡ Newly Assigned</div>
                      {o.newly_assigned.map((t, idx) => (
                        <div key={idx} className="ws-digest-item">
                          • {t.title || t} {t.deadline_iso ? `(Due ${fmtDate(t.deadline_iso)})` : ''}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Upcoming deadlines */}
                  {o.upcoming_deadlines && o.upcoming_deadlines.length > 0 && (
                    <div>
                      <div className="ws-digest-section-label" style={{ color: '#A07A00' }}>⏰ Upcoming Deadlines</div>
                      {o.upcoming_deadlines.map((t, idx) => (
                        <div key={idx} className="ws-digest-item">
                          • {t.title || t} {t.deadline_iso ? `(${fmtDate(t.deadline_iso)})` : ''}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Resolved conflicts */}
                  {o.resolved_conflicts && o.resolved_conflicts.length > 0 && (
                    <div>
                      <div className="ws-digest-section-label" style={{ color: '#C564C4' }}>🛡 Resolved Conflicts</div>
                      {o.resolved_conflicts.map((c, idx) => (
                        <div key={idx} className="ws-digest-item">
                          • {c.title || c}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Right Column: Markdown Preview Box */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'rgba(13,13,12,0.6)' }}>
                Markdown Preview (Slack / Email Ready)
              </span>
              <button
                className="ws-btn ws-btn-sm"
                onClick={handleCopy}
                style={{ padding: '2px 8px', height: 24, fontSize: 11 }}
              >
                {copied ? 'Copied!' : 'Copy Text'}
              </button>
            </div>
            <pre className="ws-markdown-preview">
              {digest.markdown}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
