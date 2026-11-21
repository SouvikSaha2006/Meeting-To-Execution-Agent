/* ============================================================
   BotanicalSprout — Thin line-art SVG
   ============================================================ */
export function BotanicalSprout({ size = 64 }) {
  return (
    <svg
      className="strip-sprout"
      width={size}
      height={size * 1.3}
      viewBox="0 0 48 62"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      {/* Ground line */}
      <line x1="8" y1="56" x2="40" y2="56" stroke="#0D0D0C" strokeWidth="1.4" strokeLinecap="round" />
      {/* Main stem */}
      <path d="M24 56 C24 56 24 36 24 24" stroke="#0D0D0C" strokeWidth="1.4" strokeLinecap="round" />
      {/* Left leaf */}
      <path
        d="M24 38 C24 38 14 34 10 26 C10 26 20 24 24 32"
        stroke="#0D0D0C" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round"
        fill="none"
      />
      {/* Left leaf vein */}
      <line x1="24" y1="38" x2="13" y2="29" stroke="#0D0D0C" strokeWidth="0.7" strokeLinecap="round" opacity="0.5" />
      {/* Right leaf */}
      <path
        d="M24 30 C24 30 34 26 38 18 C38 18 28 16 24 24"
        stroke="#0D0D0C" strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round"
        fill="none"
      />
      {/* Right leaf vein */}
      <line x1="24" y1="30" x2="35" y2="21" stroke="#0D0D0C" strokeWidth="0.7" strokeLinecap="round" opacity="0.5" />
      {/* Tip bud */}
      <circle cx="24" cy="22" r="2.2" stroke="#0D0D0C" strokeWidth="1.4" fill="none" />
      <circle cx="24" cy="22" r="0.7" fill="#0D0D0C" />
    </svg>
  );
}
