// JS-side chart palette. Mirrors the CSS custom properties in styles.css (:root);
// keep these in sync — they are the single source for Recharts colors, which can't
// read CSS variables directly.
export const COLORS = {
  accent: "#4c8bf5",   // --accent
  accent2: "#dd8452",  // --accent-2
  line: "#2a2f3a",     // --line
  muted: "#9aa3b2",    // --muted
  panel2: "#20242e",   // --panel-2
};

// Shared dark tooltip styling for every chart.
export const TOOLTIP_STYLE = { background: COLORS.panel2, border: `1px solid ${COLORS.line}` };
