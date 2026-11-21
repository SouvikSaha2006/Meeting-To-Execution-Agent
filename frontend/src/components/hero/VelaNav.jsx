/* ============================================================
   VelaNav — Top navigation bar (VeriFlow)
   ============================================================ */
export function VelaNav({ onNavigateTab }) {
  const scrollTo = (id, tabId, filterId) => {
    const el = document.getElementById(id || 'workspace');
    if (el) el.scrollIntoView({ behavior: 'smooth' });
    if (onNavigateTab && tabId) {
      onNavigateTab(tabId, filterId);
    }
  };

  const handleLaunch = () => scrollTo('workspace', 'ingest');

  return (
    <nav className="vela-nav" aria-label="VeriFlow main navigation">
      {/* Left: brand */}
      <div className="nav-left">
        <div className="nav-logo-dot" aria-hidden="true" />
        <span className="nav-wordmark">veriflow</span>
        <span className="nav-badge">VeriFlow&nbsp;·&nbsp;PS&nbsp;03</span>
      </div>

      {/* Right: links + CTA */}
      <div className="nav-right">
        <ul className="nav-links" role="list">
          {[
            ['Workspace',       'workspace',      'ingest',    'all'],
            ['Conflict Guard',  'workspace',      'ingest',    'conflicts'],
            ['Decision Log',    'workspace',      'decisions', null],
            ['Weekly Digest',   'workspace',      'digest',    null],
          ].map(([label, anchorId, tabId, filterId]) => (
            <li key={label}>
              <a
                href={`#${anchorId}`}
                onClick={(e) => {
                  e.preventDefault();
                  scrollTo(anchorId, tabId, filterId);
                }}
              >
                {label}
              </a>
            </li>
          ))}
        </ul>
        <button className="nav-cta" onClick={handleLaunch} type="button">
          Launch&nbsp;Agent
        </button>
      </div>
    </nav>
  );
}
