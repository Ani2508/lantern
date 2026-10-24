import type { SiteType } from "../api/types";

/** Small glyphs drawn on a 24 px grid, centred at 0,0. */
export function SiteGlyph({ type }: { type: SiteType }) {
  const common = { className: "glyph", transform: "translate(-12 -12)" };
  switch (type) {
    case "shelter":
      return (
        <g {...common}>
          <path d="M4 11.5L12 5l8 6.5M6.5 10v8.5h11V10" />
          <path d="M10 18.5v-4.5h4v4.5" />
        </g>
      );
    case "clinic":
      return (
        <g {...common}>
          <path d="M10 5h4v5h5v4h-5v5h-4v-5H5v-4h5z" />
        </g>
      );
    case "pharmacy":
      return (
        <g {...common}>
          <rect x="4.5" y="8.5" width="15" height="7" rx="3.5" transform="rotate(-35 12 12)" />
          <path d="M9.7 8.8l4.6 6.5" />
        </g>
      );
    case "food_bank":
      return (
        <g {...common}>
          <path d="M5 9l7-3.5L19 9v8.5l-7 3.5-7-3.5z" />
          <path d="M5 9l7 3.5L19 9M12 12.5v8.5" />
        </g>
      );
  }
}

export function LanternMark({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="lantern-mark">
      <path d="M12 6h8M16 3v3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M10 9h12l1.5 3v12l-1.5 3H10l-1.5-3V12z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M16 13c2.2 2.4 2.6 4.6 0 8-2.6-3.4-2.2-5.6 0-8z" fill="var(--gold)" />
    </svg>
  );
}
