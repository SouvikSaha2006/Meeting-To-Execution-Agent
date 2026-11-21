/* ============================================================
   App.jsx — Root with hero + placeholder workspace
   ============================================================ */
import { useState }   from 'react';
import { VelaHero }   from './components/hero/index.js';
import './design-tokens.css';
import './App.css';

function WorkspacePlaceholder({ demoMode, conflictMode }) {
  return (
    <section
      id="workspace"
      style={{
        minHeight: '100vh',
        background: '#FBF6EF',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '80px 24px',
        gap: '24px',
      }}
    >
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '16px',
        maxWidth: 520,
        textAlign: 'center',
      }}>
        <span style={{
          fontFamily: 'Inter Tight, sans-serif',
          fontSize: 13,
          fontWeight: 500,
          color: 'rgba(13,13,12,0.42)',
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
        }}>
          {conflictMode ? '⚡ Conflict Guard Active' : demoMode ? '▶ Live Demo Mode' : 'Workspace'}
        </span>
        <h2 style={{
          fontFamily: 'Inter Tight, sans-serif',
          fontSize: 'clamp(28px, 4vw, 48px)',
          fontWeight: 600,
          color: '#0D0D0C',
          letterSpacing: '-0.03em',
          lineHeight: 1.1,
        }}>
          {conflictMode
            ? 'Cross-Meeting Conflict Detection'
            : demoMode
              ? 'Sample Meeting Pipeline'
              : 'Your meeting workspace'}
        </h2>
        <p style={{
          fontFamily: 'Inter Tight, sans-serif',
          fontSize: 17,
          fontWeight: 400,
          color: 'rgba(13,13,12,0.56)',
          lineHeight: 1.5,
        }}>
          {conflictMode
            ? 'Vela is scanning cross-meeting decisions for contradictions, ownership gaps, and date collisions.'
            : demoMode
              ? 'Upload a meeting transcript or paste a summary — Vela will capture actions, verify owners, resolve conflicts, and execute tasks autonomously.'
              : 'Mount your interactive workspace components here — the hero scrolls directly into this section.'}
        </p>
        <div style={{
          marginTop: 8,
          padding: '16px 24px',
          background: 'rgba(13,13,12,0.04)',
          border: '1.4px solid rgba(13,13,12,0.12)',
          borderRadius: 10,
          fontFamily: 'Inter Tight, sans-serif',
          fontSize: 13,
          color: 'rgba(13,13,12,0.42)',
          fontStyle: 'italic',
        }}>
          {'// '}Replace this section with your{' '}
          <code style={{ fontStyle: 'normal', background: 'rgba(13,13,12,0.07)', padding: '1px 5px', borderRadius: 4 }}>
            #workspace
          </code>{' '}
          interactive components
        </div>
      </div>

      {/* Additional anchor sections for nav links */}
      <div id="conflict-guard" style={{ position: 'absolute', top: 0 }} aria-hidden="true" />
      <div id="decision-log"   style={{ position: 'absolute', top: 0 }} aria-hidden="true" />
      <div id="weekly-digest"  style={{ position: 'absolute', top: 0 }} aria-hidden="true" />
    </section>
  );
}

export default function App() {
  const [demoMode,     setDemoMode]     = useState(false);
  const [conflictMode, setConflictMode] = useState(false);

  return (
    <>
      <VelaHero
        onTryDemo={()      => { setDemoMode(true);     setConflictMode(false); }}
        onConflictTest={() => { setConflictMode(true); setDemoMode(false);     }}
      />
      <WorkspacePlaceholder demoMode={demoMode} conflictMode={conflictMode} />
    </>
  );
}
