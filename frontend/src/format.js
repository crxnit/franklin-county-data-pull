export const usd = (v) =>
  v == null ? "—" : v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
export const usd0 = usd;
export const num = (v) => (v == null ? "—" : v.toLocaleString("en-US"));
export const ppsf = (v) => (v == null ? "—" : `$${v.toFixed(0)}`);
