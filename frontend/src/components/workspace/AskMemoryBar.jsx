import React, { useState, useRef } from 'react';
import { askMemory } from '../../api/client.js';

const STARTER_CHIPS = [
  'Why did our DB choice change?',
  'Who has tasks due soon?',
  'What decisions were superseded?',
];

export function AskMemoryBar() {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [isOpen, setIsOpen] = useState(false);
  const [expandedCitationIdx, setExpandedCitationIdx] = useState(null);
  const inputRef = useRef(null);

  async function handleAsk(q) {
    const queryText = (q ?? question).trim();
    if (!queryText) return;
    setQuestion(queryText);
    setLoading(true);
    setError(null);
    setIsOpen(true);
    setExpandedCitationIdx(null);

    try {
      const data = await askMemory(queryText);
      setResult({
        question: queryText,
        answer: data.answer,
        citations: data.citations || [],
        relatedTaskIds: data.related_task_ids || [],
      });
    } catch (err) {
      console.error('Failed to query organizational memory:', err);
      setError(err?.detail || err?.message || 'Could not query meeting memory. Please check if backend is running.');
    } finally {
      setLoading(false);
    }
  }

  function handleFormSubmit(e) {
    e.preventDefault();
    handleAsk(question);
  }

  function handleClose() {
    setIsOpen(false);
    setError(null);
  }

  return (
    <div className="ws-memory-floating-wrap">
      {/* Expanded Answer Drawer / Popover */}
      {isOpen && (
        <div className="ws-memory-answer-drawer">
          <div className="ws-memory-drawer-header">
            <div className="ws-memory-drawer-title-row">
              <span className="ws-memory-sparkle">✦</span>
              <span className="ws-memory-drawer-heading">Cross-Meeting Memory Synthesis</span>
              {loading && <span className="ws-memory-loading-badge">Querying memory…</span>}
            </div>
            <button
              className="ws-memory-close-btn"
              onClick={handleClose}
              title="Close Answer Drawer"
              type="button"
            >
              ✕
            </button>
          </div>

          <div className="ws-memory-drawer-body">
            {loading ? (
              <div className="ws-memory-loading-state">
                <div className="ws-memory-pulse-bar" />
                <p style={{ margin: '8px 0 0', fontSize: 13, color: 'rgba(13,13,12,0.6)' }}>
                  Searching decisions, transcripts, and commitments for "{question}"…
                </p>
              </div>
            ) : error ? (
              <div className="ws-memory-error-box">
                <strong>Memory Search Alert:</strong> {error}
              </div>
            ) : result ? (
              <div className="ws-memory-result-content">
                <div className="ws-memory-q-badge">
                  <strong>Q:</strong> {result.question}
                </div>

                <div className="ws-memory-answer-text">
                  {result.answer}
                </div>

                {/* Citations Section */}
                {result.citations && result.citations.length > 0 && (
                  <div className="ws-memory-citations-section">
                    <div className="ws-memory-citations-header">
                      <span>Source Citations ({result.citations.length})</span>
                      <span className="ws-memory-citation-hint">Click citation chip to view quote</span>
                    </div>

                    <div className="ws-memory-citation-chips-grid">
                      {result.citations.map((cite, idx) => {
                        const isExpanded = expandedCitationIdx === idx;
                        return (
                          <div
                            key={idx}
                            className={`ws-memory-citation-chip ${isExpanded ? 'active' : ''}`}
                            onClick={() => setExpandedCitationIdx(isExpanded ? null : idx)}
                            title="Click to toggle verbatim quote"
                          >
                            <div className="ws-memory-citation-chip-header">
                              <span className="ws-cite-pin">📌</span>
                              <span className="ws-cite-meeting">{cite.meeting_title}</span>
                              <span className="ws-cite-dot">•</span>
                              <span className="ws-cite-date">{cite.meeting_date}</span>
                              <span className="ws-cite-dot">•</span>
                              <span className="ws-cite-speaker">{cite.speaker}</span>
                            </div>

                            {/* Clickable quote snippet / expanded */}
                            <div className="ws-cite-quote-preview">
                              "{cite.quote}"
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Related Tasks */}
                {result.relatedTaskIds && result.relatedTaskIds.length > 0 && (
                  <div className="ws-memory-related-tasks">
                    <span className="ws-related-label">Related Execution Tasks:</span>
                    <div className="ws-related-pills">
                      {result.relatedTaskIds.map((tid) => (
                        <span key={tid} className="ws-related-task-pill">
                          Task #{tid}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* Floating Bottom Pill Bar */}
      <div className="ws-memory-pill-bar">
        {/* Starters Row */}
        <div className="ws-memory-starters-row">
          <span className="ws-memory-starters-label">Ask Memory:</span>
          {STARTER_CHIPS.map((chip, idx) => (
            <button
              key={idx}
              type="button"
              className="ws-memory-starter-chip"
              onClick={() => handleAsk(chip)}
              disabled={loading}
            >
              {chip}
            </button>
          ))}
        </div>

        {/* Input Bar */}
        <form className="ws-memory-input-form" onSubmit={handleFormSubmit}>
          <div className="ws-memory-input-wrap">
            <span className="ws-memory-input-icon">🔍</span>
            <input
              ref={inputRef}
              type="text"
              className="ws-memory-input"
              placeholder="Ask anything across meeting history (e.g. 'When is the product launch?')..."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={loading}
            />
          </div>
          <button
            type="submit"
            className="ws-memory-submit-btn"
            disabled={loading || !question.trim()}
          >
            {loading ? 'Searching…' : 'Ask ↵'}
          </button>
        </form>
      </div>
    </div>
  );
}

export default AskMemoryBar;
