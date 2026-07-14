"use client";
import React, { useState } from "react";
import { ScanSearch, ChevronDown, ShieldCheck, ShieldAlert } from "lucide-react";

function Row({ label, value, mono }) {
  if (!value) return null;
  return (
    <div className="flex gap-2 text-[11.5px] py-0.5">
      <span className="text-slate-500 shrink-0 w-[74px]">{label}</span>
      <span className={`text-[var(--text)] ${mono ? "font-mono text-[10.5px]" : ""}`}>{value}</span>
    </div>
  );
}

function Draft({ attempt, index, total }) {
  const [open, setOpen] = useState(false);
  const g = attempt.is_grounded;
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--card2)] p-2">
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center gap-2 text-[11px]">
        <ChevronDown size={12} className={`transition ${open ? "rotate-180" : ""} text-slate-500`} />
        <span className="font-semibold">Draft {index + 1}{total > 1 ? ` / ${total}` : ""}</span>
        <span className="text-slate-500">(before grounding)</span>
        <span className="ml-auto flex items-center gap-1">
          {g === false
            ? <span className="text-amber-400 flex items-center gap-1"><ShieldAlert size={11} /> rejected</span>
            : g === true
            ? <span className="text-emerald-400 flex items-center gap-1"><ShieldCheck size={11} /> passed</span>
            : <span className="text-slate-500">—</span>}
        </span>
      </button>
      {attempt.reason && <div className="mt-1 text-[10.5px] text-slate-500 pl-5">{attempt.reason}</div>}
      {open && (
        <div className="mt-2 pl-5 text-[11px] text-slate-300 whitespace-pre-wrap max-h-48 overflow-y-auto">
          {attempt.draft || "(empty)"}
        </div>
      )}
    </div>
  );
}

export default function RunInspector({ record }) {
  const [open, setOpen] = useState(false);
  if (!record || (!record.attempts && !record.rewritten_query)) return null;

  const attempts = record.attempts || [];
  const timings = record.timings || {};
  const order = ["rewrite_and_route", "retrieve", "generate", "evaluate_grounding",
    "expand_query", "general_answer", "build_final_answer"];
  const timingEntries = order.filter((k) => k in timings).map((k) => [k, timings[k]]);

  return (
    <div className="mt-2">
      <button onClick={() => setOpen((o) => !o)}
        className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center gap-1 transition">
        <ScanSearch size={13} /> Run details
        <ChevronDown size={12} className={`transition ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="mt-2 rounded-xl border border-[var(--border)] bg-[var(--card)] p-3 space-y-3">
          {/* query evolution */}
          <div>
            <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">Query evolution</div>
            <Row label="Original" value={record.raw_query} />
            {record.rewritten_query && record.rewritten_query !== record.raw_query &&
              <Row label="Rewritten" value={record.rewritten_query} />}
            {record.expanded_query && <Row label="Expanded" value={record.expanded_query} />}
            <Row label="Route" value={{
              general: "💬 general chat", tool: "🔧 tool / function call",
              search: "🌐 internet search", rag: "📚 knowledge base",
            }[record.route] || record.route} />
          </div>

          {/* drafts before grounding */}
          {attempts.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
                Generation attempts (pre-grounding)
              </div>
              <div className="space-y-1.5">
                {attempts.map((a, i) => <Draft key={i} attempt={a} index={i} total={attempts.length} />)}
              </div>
            </div>
          )}

          {/* tool calls */}
          {(record.tool_calls || []).length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">Tool calls</div>
              <div className="space-y-1">
                {record.tool_calls.map((t, i) => (
                  <div key={i} className="rounded-lg border border-[var(--border)] bg-[var(--card2)] p-2 text-[11px]">
                    <div className="font-mono text-indigo-300">{t.name}({JSON.stringify(t.args)})</div>
                    <div className="font-mono text-[10.5px] text-emerald-300 mt-1 break-words">
                      → {JSON.stringify(t.result)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* web search results */}
          {(record.search_results || []).length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">Web results</div>
              <div className="space-y-1">
                {record.search_results.map((r, i) => (
                  <a key={i} href={r.url} target="_blank" rel="noreferrer"
                    className="block rounded-lg border border-[var(--border)] bg-[var(--card2)] p-2 hover:border-indigo-500/50 transition">
                    <div className="text-[11px] text-sky-300 truncate">[{i + 1}] {r.title}</div>
                    <div className="text-[10px] text-slate-500 truncate">{r.url}</div>
                  </a>
                ))}
              </div>
            </div>
          )}

          {/* grounding + timings */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">Grounding</div>
              <div className="text-[11.5px] flex items-center gap-1">
                {record.is_grounded
                  ? <span className="text-emerald-400 flex items-center gap-1"><ShieldCheck size={12} /> verified</span>
                  : <span className="text-amber-400 flex items-center gap-1"><ShieldAlert size={12} /> unverified</span>}
                {record.retry_count > 0 && <span className="text-slate-500">· retried {record.retry_count}×</span>}
              </div>
              {record.grounding_reason && <div className="text-[10.5px] text-slate-500 mt-1">{record.grounding_reason}</div>}
              {record.model && <Row label="Model" value={record.model} mono />}
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
                Timings · {(record.total_ms / 1000).toFixed(2)}s total
              </div>
              {timingEntries.map(([k, ms]) => (
                <div key={k} className="flex justify-between text-[10.5px] py-0.5">
                  <span className="text-slate-400 font-mono">{k}</span>
                  <span className="text-[var(--text)] tabular-nums">{ms} ms</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
