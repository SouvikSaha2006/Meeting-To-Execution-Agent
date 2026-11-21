/* ============================================================
   GrainOverlay — SVG feTurbulence noise layer
   ============================================================ */
export function GrainOverlay() {
  return (
    <svg
      className="hero-grain"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <filter id="vela-grain-filter" x="0%" y="0%" width="100%" height="100%">
        <feTurbulence
          type="fractalNoise"
          baseFrequency="0.68"
          numOctaves="4"
          stitchTiles="stitch"
          result="noiseOut"
        />
        <feColorMatrix
          type="saturate"
          values="0"
          in="noiseOut"
          result="grayNoise"
        />
        <feBlend in="SourceGraphic" in2="grayNoise" mode="multiply" />
      </filter>
      <rect
        x="0" y="0" width="100%" height="100%"
        filter="url(#vela-grain-filter)"
        fill="rgba(0,0,0,0.3)"
      />
    </svg>
  );
}
