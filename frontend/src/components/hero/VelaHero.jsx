/* ============================================================
   VelaHero — Landing Hero Component
   Single-clock Web Animation architecture
   ============================================================ */
import { useRef, useState, useEffect, useCallback } from 'react';

import { VERBS, buildGradient, AnimationEngine } from './animationEngine.js';
import { GrainOverlay }  from './GrainOverlay.jsx';
import { VelaNav }       from './VelaNav.jsx';
import { CreamStrip }    from './CreamStrip.jsx';

import './VelaHero.css';

/* ── Icon with CSS-mask tint overlay ──────────────────────────── */
function VerbIcon({ verb, iconWrapRef, iconImgRef, tintRef }) {
  const currentVerb = verb || VERBS[0];
  return (
    <span
      className="verb-icon-wrap"
      ref={iconWrapRef}
      aria-hidden="true"
    >
      <img
        ref={iconImgRef}
        className="verb-icon-img"
        src={currentVerb.iconUrl}
        alt=""
        draggable="false"
      />
      <span
        ref={tintRef}
        className="verb-icon-tint"
        style={{
          backgroundColor: currentVerb.tint,
          mask: `url(${currentVerb.iconUrl}) center / contain no-repeat`,
          WebkitMask: `url(${currentVerb.iconUrl}) center / contain no-repeat`,
        }}
      />
    </span>
  );
}

/* ── Play icon SVG ───────────────────────────────────────────── */
function IconPlay({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 18 18" fill="none"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="9" cy="9" r="7.5" />
      <polygon points="7.5,6 13,9 7.5,12" fill="currentColor" stroke="none" />
    </svg>
  );
}

/* ── Shield/Alert icon SVG ───────────────────────────────────── */
function IconShield({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 18 18" fill="none"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 2 L15.5 5 L15.5 9.5 C15.5 13 12.5 15.5 9 17 C5.5 15.5 2.5 13 2.5 9.5 L2.5 5 Z" />
      <line x1="9" y1="7" x2="9" y2="10.5" strokeWidth="1.6" />
      <circle cx="9" cy="12.5" r="0.75" fill="currentColor" stroke="none" />
    </svg>
  );
}

/* ── Main Component ──────────────────────────────────────────── */
export function VelaHero({ onTryDemo, onConflictTest, onNavigateTab }) {
  const [verbIndex, setVerbIndex]           = useState(0);
  const [executeHighlight, setExecuteHighlight] = useState(false);

  /* Refs for DOM animation targets */
  const bgLayerRefs = useRef([]);
  const iconWrapRef = useRef(null);
  const iconImgRef  = useRef(null);
  const tintRef     = useRef(null);
  const verbTextRef = useRef(null);
  const primaryBtnRef = useRef(null);
  const engineRef   = useRef(null);

  /* Active verb data */
  const verb = (VERBS && VERBS[verbIndex]) ? VERBS[verbIndex] : (VERBS ? VERBS[0] : null);

  /* Callback when engine advances the verb */
  const handleVerbChange = useCallback((idx) => {
    if (!VERBS || VERBS.length === 0) return;
    const validIdx = idx >= 0 && idx < VERBS.length ? idx : 0;
    setVerbIndex(validIdx);
    const newVerb = VERBS[validIdx];
    if (!newVerb) return;
    if (iconImgRef.current && newVerb.iconUrl) {
      iconImgRef.current.src = newVerb.iconUrl;
    }
    if (tintRef.current && newVerb.tint) {
      tintRef.current.style.backgroundColor = newVerb.tint;
      tintRef.current.style.mask            = `url(${newVerb.iconUrl}) center / contain no-repeat`;
      tintRef.current.style.WebkitMask      = `url(${newVerb.iconUrl}) center / contain no-repeat`;
    }
    if (verbTextRef.current && newVerb.label) {
      verbTextRef.current.textContent = newVerb.label;
    }
  }, []);

  /* Boot engine on mount */
  useEffect(() => {
    const engine = new AnimationEngine({
      refs: {
        bgLayers:   bgLayerRefs.current,
        iconWrap:   iconWrapRef.current,
        iconImg:    iconImgRef.current,
        tintLayer:  tintRef.current,
        verbText:   verbTextRef.current,
        primaryBtn: primaryBtnRef.current,
      },
      onVerbChange:     handleVerbChange,
      onExecuteHighlight: setExecuteHighlight,
    });
    engineRef.current = engine;
    engine.start();
    return () => engine.destroy();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /* Scroll helpers */
  const scrollToWorkspace = () => {
    document.getElementById('workspace')?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleTryDemo = () => {
    scrollToWorkspace();
    onTryDemo?.();
  };

  const handleConflictTest = () => {
    scrollToWorkspace();
    onConflictTest?.();
  };

  return (
    <header className="vela-hero">
      {/* ── Gradient Panel (top 75%) ──────────────────── */}
      <div className="hero-panel">
        {/* Background gradient layers */}
        {VERBS.map((v, i) => (
          <div
            key={v.id}
            className="hero-bg-layer"
            ref={(el) => { bgLayerRefs.current[i] = el; }}
            style={{ background: buildGradient(v) }}
            aria-hidden="true"
          />
        ))}

        {/* Grain noise overlay */}
        <GrainOverlay />

        {/* Navigation */}
        <VelaNav onNavigateTab={onNavigateTab} />

        {/* ── Headline ─────────────────────────────── */}
        <div className="hero-headline-wrap">
          <h1 className="hero-headline">
            {/* Line 1: [Icon] [Verb] */}
            <span className="headline-line1" aria-live="polite" aria-atomic="true">
              <VerbIcon
                verb={verb}
                iconWrapRef={iconWrapRef}
                iconImgRef={iconImgRef}
                tintRef={tintRef}
              />
              <span
                ref={verbTextRef}
                className="verb-text-slot"
              >
                {verb?.label || 'Verify'}
              </span>
            </span>

            {/* Line 2: static */}
            <span className="headline-line2" aria-hidden="false">
              every meeting
            </span>
          </h1>
        </div>

        {/* ── Action Row ───────────────────────────── */}
        <div className="hero-action-row">
          <button
            ref={primaryBtnRef}
            type="button"
            className={`hero-btn hero-btn-primary${executeHighlight ? ' execute-highlight' : ''}`}
            onClick={handleTryDemo}
            aria-label="Try Live Demo — loads sample meeting in workspace"
          >
            <IconPlay />
            Try Live Demo
          </button>

          <button
            type="button"
            className="hero-btn hero-btn-secondary"
            onClick={handleConflictTest}
            aria-label="Load Conflict Test — demonstrates cross-meeting contradiction detection"
          >
            <IconShield />
            Load Conflict Test
          </button>

          <p className="hero-caption">
            VeriFlow is an autonomous meeting-to-execution agent that<br />
            catches cross-meeting conflicts before tasks ship.
          </p>
        </div>
      </div>

      {/* ── Cream Stats Strip (bottom 25%) ───────────── */}
      <CreamStrip />
    </header>
  );
}
