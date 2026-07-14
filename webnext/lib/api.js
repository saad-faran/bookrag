// API client. Talks DIRECTLY to the FastAPI backend (no dev proxy) so SSE streams
// aren't buffered. All calls carry the Bearer token and auto-refresh once on 401.

import { authHeader, refreshToken, logout } from "./auth.js";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

async function req(path, opts = {}, retry = true) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: { ...(opts.headers || {}), ...authHeader() },
  });
  if (res.status === 401 && retry && (await refreshToken())) {
    return req(path, opts, false);           // retry once with a fresh token
  }
  if (res.status === 401) {
    logout();
    if (typeof window !== "undefined") window.location.reload();
  }
  return res;
}

export async function getHealth() { return (await req("/api/health")).json(); }
export async function getNodes() { return (await req("/api/nodes")).json(); }
export async function getCorpus() { return (await req("/api/corpus")).json(); }
export async function listChats() { return (await req("/api/chats")).json(); }
export async function createChat(projectId = "") {
  return (await req("/api/chats", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(projectId ? { project_id: projectId } : {}),
  })).json();
}
export async function getChat(id) { return (await req(`/api/chats/${id}`)).json(); }
export async function deleteChat(id) { return req(`/api/chats/${id}`, { method: "DELETE" }); }

// ---- projects ----
export async function listProjects() { return (await req("/api/projects")).json(); }
export async function createProject(name, description = "") {
  return (await req("/api/projects", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  })).json();
}
export async function getProject(pid) { return (await req(`/api/projects/${pid}`)).json(); }
export async function deleteProject(pid) { return req(`/api/projects/${pid}`, { method: "DELETE" }); }
export async function uploadFile(pid, file) {
  const fd = new FormData();
  fd.append("file", file);
  return (await req(`/api/projects/${pid}/files`, { method: "POST", body: fd })).json();
}
export async function openRawFile(pid, fid) {
  const r = await req(`/api/projects/${pid}/files/${fid}/raw`);
  if (!r.ok) return;
  const url = URL.createObjectURL(await r.blob());
  window.open(url, "_blank");
}

// Streams pipeline events. Calls onEvent(evt) for each parsed JSON event.
export async function streamChat(chatId, message, onEvent, signal) {
  const res = await req(`/api/chats/${chatId}/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`stream failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split(/\r?\n\r?\n/);  // SSE frames (sse-starlette uses CRLF)
    buf = parts.pop() || "";
    for (const part of parts) {
      const line = part.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      try { onEvent(JSON.parse(line.slice(5).trim())); } catch { /* ignore */ }
    }
  }
}
