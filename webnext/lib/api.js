// API client. Talks DIRECTLY to the FastAPI backend (no dev proxy) so SSE streams
// aren't buffered. Override the base with NEXT_PUBLIC_API_BASE if the backend moves.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function getHealth() { return (await fetch(`${API_BASE}/api/health`)).json(); }
export async function getNodes() { return (await fetch(`${API_BASE}/api/nodes`)).json(); }
export async function getCorpus() { return (await fetch(`${API_BASE}/api/corpus`)).json(); }
export async function listChats() { return (await fetch(`${API_BASE}/api/chats`)).json(); }
export async function createChat() { return (await fetch(`${API_BASE}/api/chats`, { method: "POST" })).json(); }
export async function getChat(id) { return (await fetch(`${API_BASE}/api/chats/${id}`)).json(); }
export async function deleteChat(id) { return fetch(`${API_BASE}/api/chats/${id}`, { method: "DELETE" }); }

// Streams pipeline events. Calls onEvent(evt) for each parsed JSON event.
export async function streamChat(chatId, message, onEvent, signal) {
  const res = await fetch(`${API_BASE}/api/chats/${chatId}/stream`, {
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
