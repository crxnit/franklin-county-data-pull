// Tiny API client. The shared secret (if the server is gated) is kept in
// localStorage and sent as a Bearer token.

const TOKEN_KEY = "fh_token";

// Tunable result limits for the read endpoints.
const SEARCH_LIMIT = 8;   // address autocomplete suggestions
const REPORT_COMPS = 12;  // comps returned with a pricing report

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}
export function setToken(t) {
  localStorage.setItem(TOKEN_KEY, t || "");
}

async function req(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (opts.body) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api${path}`, { ...opts, headers });
  if (res.status === 401) throw new ApiError("Unauthorized — check the access password.", 401);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
    throw new ApiError(detail, res.status);
  }
  return res.json();
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export const api = {
  health: () => req("/health"),
  meta: () => req("/meta"),
  searchAddress: (q) => req(`/address/search?q=${encodeURIComponent(q)}&limit=${SEARCH_LIMIT}`),
  report: (address) => req(`/report?address=${encodeURIComponent(address)}&comps=${REPORT_COMPS}`),
  comps: (body) => req("/comps", { method: "POST", body: JSON.stringify(body) }),
  neighborhoods: () => req("/neighborhoods"),
  neighborhood: (nbhdcd) => req(`/neighborhoods/${encodeURIComponent(nbhdcd)}`),
  trendDimensions: () => req("/trends/dimensions"),
  trend: (params) => req(`/trends?${new URLSearchParams(params)}`),
};
