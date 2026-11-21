/* ============================================================
   VelaNav — Top navigation bar
   ============================================================ */
export function VelaNav() {
  const scrollTo = (id) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  };

  const handleLaunch = () => scrollTo('workspace');

  return (
    <nav className="vela-nav" aria-label="Vela main navigation">
      {/* Left: brand */}
      <div className="nav-left">
        <div className="nav-logo-dot" aria-hidden="true" />
        <span className="nav-wordmark">vela</span>
        <span className="nav-badge">Agentic AI&nbsp;PS&nbsp;03</span>
      </div>

      {/* Right: links + CTA */}
      <div className="nav-right">
        <ul className="nav-links" role="list">
          {[
            ['Workspace',       'workspace'],
            ['Conflict Guard',  'conflict-guard'],
            ['Decision Log',    'decision-log'],
            ['Weekly Digest',   'weekly-digest'],
          ].map(([label, id]) => (
            <li key={id}>
              <a
                href={`#${id}`}
                onClick={(e) => { e.preventDefault(); scrollTo(id); }}
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
