export const usd = (v) =>
  v == null ? "—" : v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
export const num = (v) => (v == null ? "—" : v.toLocaleString("en-US"));
export const ppsf = (v) => (v == null ? "—" : `$${v.toFixed(0)}`);
// "Name (code)" for an appraiser neighborhood, falling back to the bare code.
export const nbhdLabel = (name, code) => (name ? `${name} (${code})` : code);
