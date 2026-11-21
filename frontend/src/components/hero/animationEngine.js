/* ============================================================
   VELA — Unified Web Animations Clock
   Single-clock architecture driving all hero motion
   ============================================================ */

export const VERBS = [
  {
    id: 'capture',
    label: 'Capture',
    iconUrl: 'https://d2ol7oe51mr4n9.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/83de7c35-dd91-4e56-bfb8-0ffafc83d0e0.webp',
    tint: '#E9C22E',
    bgBase1: '#F2ECDF',
    bgBase2: '#F4EBC6',
    glowBR:  'rgb(246, 222, 104)',
    glowBL:  'rgb(246, 222, 104)',
  },
  {
    id: 'verify',
    label: 'Verify',
    iconUrl: 'https://d2ol7oe51mr4n9.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/4d952211-0474-48cc-af48-58f68b3b7525.webp',
    tint: '#F2772F',
    bgBase1: '#F8DCC7',
    bgBase2: '#F9CBA9',
    glowBR:  'rgb(249, 150, 84)',
    glowBL:  'rgb(249, 150, 84)',
  },
  {
    id: 'resolve',
    label: 'Resolve',
    iconUrl: 'https://d2ol7oe51mr4n9.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/e2e91fca-5b3f-4e0e-a437-8a581592e407.webp',
    tint: '#3FB874',
    bgBase1: '#E9EBE0',
    bgBase2: '#DFE9D4',
    glowBR:  'rgb(150, 206, 150)',
    glowBL:  'rgb(150, 206, 150)',
  },
  {
    id: 'execute',
    label: 'Execute',
    iconUrl: 'https://d2ol7oe51mr4n9.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/6b32bb47-4ad6-4938-a637-c997b373c68b.webp',
    tint: '#C564C4',
    bgBase1: '#F0E4E6',
    bgBase2: '#ECD6E2',
    glowBR:  'rgb(222, 150, 200)',
    glowBL:  'rgb(222, 150, 200)',
  },
];

export function buildGradient(verb) {
  return `
    linear-gradient(180deg, ${verb.bgBase1} 0%, ${verb.bgBase2} 100%),
    radial-gradient(ellipse 60% 55% at 86% 76%, ${verb.glowBR} 0%, transparent 70%),
    radial-gradient(ellipse 50% 45% at 32% 105%, ${verb.glowBL} 0%, transparent 65%)
  `.trim();
}

/* ─────────────────────────────────────────────────────────
   AnimationEngine class
   - One master requestAnimationFrame loop
   - Pauses on visibilitychange (tab hidden)
   - Respects prefers-reduced-motion
   ───────────────────────────────────────────────────────── */

const SLOT_DURATION   = 1750;   // ms per verb slot
const ENTER_DURATION  = 500;    // ms
const LEAVE_DURATION  = 420;    // ms
const CROSSFADE_MS    = 770;    // panel bg crossfade window (ms)

const EASE_OUT_EXPO = (t) => (t === 1 ? 1 : 1 - Math.pow(2, -10 * t));
const EASE_SPRING   = (t) => {
  // Approximates cubic-bezier(0.22, 1, 0.36, 1)
  const c4 = (2 * Math.PI) / 3;
  if (t === 0) return 0;
  if (t === 1) return 1;
  return Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * c4) + 1;
};

export class AnimationEngine {
  constructor({ refs, onVerbChange, onExecuteHighlight }) {
    this.refs             = refs;             // { bgLayers[], iconWrap, iconImg, tintLayer, verbText, primaryBtn }
    this.onVerbChange     = onVerbChange;     // (verbIndex) => void
    this.onExecuteHighlight = onExecuteHighlight; // (bool) => void

    this.currentIndex     = 0;
    this.startTime        = null;
    this.rafId            = null;
    this.paused           = false;
    this.pausedAt         = null;             // time paused
    this.totalPaused      = 0;               // accumulated pause ms
    this.reducedMotion    = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    this._handleVisibility = this._handleVisibility.bind(this);
    this._tick             = this._tick.bind(this);

    document.addEventListener('visibilitychange', this._handleVisibility);

    // Float animation state
    this._floatPhase = 0;
  }

  start() {
    if (this.reducedMotion) {
      // Static fallback: show "Verify every meeting" (index 1)
      if (this.onVerbChange) this.onVerbChange(1);
      this._applyStaticState(1);
      return;
    }
    this.startTime = performance.now();
    this.rafId = requestAnimationFrame(this._tick);
  }

  destroy() {
    if (this.rafId) cancelAnimationFrame(this.rafId);
    document.removeEventListener('visibilitychange', this._handleVisibility);
  }

  _handleVisibility() {
    if (document.hidden) {
      this.paused = true;
      this.pausedAt = performance.now();
      if (this.rafId) cancelAnimationFrame(this.rafId);
    } else {
      if (this.paused && this.pausedAt != null) {
        this.totalPaused += performance.now() - this.pausedAt;
        this.pausedAt = null;
      }
      this.paused = false;
      this.rafId = requestAnimationFrame(this._tick);
    }
  }

  _tick(now) {
    this.rafId = requestAnimationFrame(this._tick);

    const elapsed = now - this.startTime - this.totalPaused;
    // Which slot are we in?
    const slotIndex  = Math.floor(elapsed / SLOT_DURATION) % VERBS.length;
    const slotElapsed = elapsed % SLOT_DURATION;

    // If verb changed, notify React
    if (slotIndex !== this.currentIndex) {
      this.currentIndex = slotIndex;
      if (this.onVerbChange) this.onVerbChange(slotIndex);
    }

    // Execute-slot button highlight
    const isExecute = slotIndex === 3;
    if (this.onExecuteHighlight) this.onExecuteHighlight(isExecute);

    // ── Background crossfade ───────────────────────────────
    this._animateBgLayers(slotIndex, slotElapsed);

    // ── Verb text + icon enter / idle / leave ─────────────
    this._animateSlot(slotElapsed);

    // ── Gradient idle drift ────────────────────────────────
    this._animateBgDrift(elapsed);
  }

  _animateBgLayers(slotIndex, slotElapsed) {
    const { bgLayers } = this.refs;
    if (!bgLayers) return;

    bgLayers.forEach((el, i) => {
      if (!el) return;
      if (i === slotIndex) {
        // Fade IN during first CROSSFADE_MS of slot
        const tIn = Math.min(slotElapsed / CROSSFADE_MS, 1);
        el.style.opacity = EASE_OUT_EXPO(tIn).toFixed(4);
      } else {
        // Fade out everything else
        const prevSlot = (slotIndex - 1 + VERBS.length) % VERBS.length;
        if (i === prevSlot) {
          const tOut = Math.min(slotElapsed / CROSSFADE_MS, 1);
          el.style.opacity = (1 - EASE_OUT_EXPO(tOut)).toFixed(4);
        } else {
          el.style.opacity = '0';
        }
      }
    });
  }

  _animateSlot(slotElapsed) {
    const { iconWrap, verbText } = this.refs;

    if (slotElapsed < ENTER_DURATION) {
      // ── Enter phase ──────────────────────────────────────
      const t = slotElapsed / ENTER_DURATION;
      const e = EASE_SPRING(t);

      if (verbText) {
        const oy = (1 - e) * 0.32;
        const blur = (1 - e) * 10;
        const scale = 0.96 + e * 0.04;
        verbText.style.transform  = `translateY(${oy}em) scale(${scale})`;
        verbText.style.filter     = `blur(${blur}px)`;
        verbText.style.opacity    = e.toFixed(4);
      }

      // Icon enters 60ms later
      if (iconWrap) {
        const tIcon = Math.max(0, (slotElapsed - 60) / ENTER_DURATION);
        const eIcon = EASE_SPRING(Math.min(tIcon, 1));
        const scaleI = 0.7 + eIcon * 0.3;
        const rotI   = -14 + eIcon * 14;
        iconWrap.style.transform = `scale(${scaleI}) rotate(${rotI}deg)`;
        iconWrap.style.opacity   = eIcon.toFixed(4);
      }

    } else if (slotElapsed > SLOT_DURATION - LEAVE_DURATION) {
      // ── Leave phase ──────────────────────────────────────
      const tLeave = (slotElapsed - (SLOT_DURATION - LEAVE_DURATION)) / LEAVE_DURATION;
      const e = EASE_OUT_EXPO(tLeave);

      if (verbText) {
        const oy   = -e * 0.16;
        const blur = e * 8;
        verbText.style.transform = `translateY(${oy}em)`;
        verbText.style.filter    = `blur(${blur}px)`;
        verbText.style.opacity   = (1 - e).toFixed(4);
      }

      if (iconWrap) {
        iconWrap.style.opacity = (1 - e * 0.5).toFixed(4);
      }

    } else {
      // ── Idle float phase ─────────────────────────────────
      const idleT = (slotElapsed - ENTER_DURATION) / (SLOT_DURATION - ENTER_DURATION - LEAVE_DURATION);
      const bob   = Math.sin(idleT * Math.PI * 2) * 0.028;
      const sway  = Math.sin(idleT * Math.PI * 1.3) * 3;

      if (verbText) {
        verbText.style.transform = `translateY(${bob}em)`;
        verbText.style.filter    = 'blur(0px)';
        verbText.style.opacity   = '1';
      }

      if (iconWrap) {
        iconWrap.style.transform = `scale(1) rotate(${sway * 0.5}deg)`;
        iconWrap.style.opacity   = '1';
      }
    }
  }

  _animateBgDrift(elapsed) {
    const { bgLayers } = this.refs;
    if (!bgLayers) return;
    const driftX = Math.sin(elapsed / 4200) * 2.2;
    const driftY = Math.cos(elapsed / 3600) * 1.6;
    bgLayers.forEach(el => {
      if (el) {
        el.style.transformOrigin = '50% 50%';
        el.style.transform = `scale(1.08) translate(${driftX}%, ${driftY}%)`;
      }
    });
  }

  _applyStaticState(verbIndex) {
    const { bgLayers, iconWrap, verbText } = this.refs;
    if (bgLayers) {
      bgLayers.forEach((el, i) => {
        if (el) el.style.opacity = i === verbIndex ? '1' : '0';
      });
    }
    if (verbText) {
      verbText.style.opacity   = '1';
      verbText.style.transform = 'none';
      verbText.style.filter    = 'none';
    }
    if (iconWrap) {
      iconWrap.style.opacity   = '1';
      iconWrap.style.transform = 'none';
    }
  }
}
