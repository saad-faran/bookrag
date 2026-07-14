// Auth client — talks to the auth microservice. Tokens in localStorage (Bearer).
// NOTE: for production, httpOnly cookies are stronger against XSS; Bearer-in-localStorage
// is used here because cross-port cookies don't work cleanly on http://localhost.

const AUTH_BASE = process.env.NEXT_PUBLIC_AUTH_BASE || "http://localhost:8001";
const TOKEN_KEY = "bookrag_access";
const REFRESH_KEY = "bookrag_refresh";
const USER_KEY = "bookrag_user";

export function getToken() {
  return typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;
}
export function getUser() {
  try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; }
}
export function authHeader() {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

function save(data) {
  if (data.access_token) localStorage.setItem(TOKEN_KEY, data.access_token);
  if (data.refresh_token) localStorage.setItem(REFRESH_KEY, data.refresh_token);
  if (data.user) localStorage.setItem(USER_KEY, JSON.stringify(data.user));
}

async function post(path, body) {
  const r = await fetch(`${AUTH_BASE}${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(d.detail || `request failed (${r.status})`);
  }
  return r.json();
}

export async function login(email, password) {
  const d = await post("/auth/login", { email, password });
  save(d);
  return d.user;
}
export async function register(email, password, name) {
  const d = await post("/auth/register", { email, password, name });
  save(d);
  return d.user;
}
export async function refreshToken() {
  const rt = localStorage.getItem(REFRESH_KEY);
  if (!rt) return false;
  try {
    const d = await post("/auth/refresh", { refresh_token: rt });
    localStorage.setItem(TOKEN_KEY, d.access_token);
    return true;
  } catch {
    return false;
  }
}
export function logout() {
  const rt = localStorage.getItem(REFRESH_KEY);
  if (rt) post("/auth/logout", { refresh_token: rt }).catch(() => {});
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USER_KEY);
}
