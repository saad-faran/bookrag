import React, { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { Activity, Check, Loader2 } from "lucide-react";
import PanelControls from "./PanelControls.jsx";

export default function TracePanel({ traceLog, nodesMeta, streaming, elapsed, selectedNode, onSelect, onMin, maxed, onToggleMax }) {
  const scrollRef = useRef(null);
  const metaOf = (id) => nodesMeta.find((n) => n.id === id) || { label: id };
  const maxDur = Math.max(1, ...traceLog.map((t) => t.durMs || 0));
  const totalMs = traceLog.reduce((a, t) => a + (t.durMs || 0), 0);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [traceLog.length]);

  return (
    <div className="glass flex flex-col min-w-0 min-h-0 overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--border)] flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[13px] font-bold flex items-center gap-2">
            <Activity size={15} className="text-cyan-300" /> Pipeline Trace
          </div>
          <div className="text-[10px] text-slate-400">Real-time execution · click to inspect</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <div className="text-right">
            <div className="text-[15px] font-bold tabular-nums gradient-text">
              {streaming ? (elapsed / 1000).toFixed(1) : (totalMs / 1000).toFixed(2)}s
            </div>
            <div className="text-[9px] text-slate-500">{streaming ? "elapsed" : "total"}</div>
          </div>
          <PanelControls onMin={onMin} maxed={maxed} onToggleMax={onToggleMax} />
        </div>
      </div>

      {streaming && (
        <div className="h-1 bg-white/5 overflow-hidden shimmer">
          <div className="h-full w-1/2 bg-gradient-to-r from-indigo-500 to-cyan-400" />
        </div>
      )}

      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto p-2.5 space-y-1.5">
        {traceLog.length === 0 && (
          <div className="h-full flex items-center justify-center text-center text-[12px] text-slate-500 px-4">
            Send a message to watch each node execute here with timings.
          </div>
        )}

        {traceLog.map((t, i) => {
          const m = metaOf(t.node);
          const active = t.status === "active";
          const sel = selectedNode === t.node;
          const pct = t.durMs ? Math.max(6, (t.durMs / maxDur) * 100) : 40;
          return (
            <motion.div key={i} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }}
              onClick={() => onSelect(t.node)}
              className={`rounded-xl px-3 py-2 cursor-pointer border transition
                ${sel ? "border-cyan-400/60 bg-cyan-400/5" : "border-[var(--border)] hover:border-indigo-500/40 bg-[var(--card2)]"}`}>
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-1.5 text-[12px] font-medium">
                  <span className="text-slate-500 tabular-nums text-[10px]">{i + 1}</span>
                  {active ? <Loader2 size={12} className="animate-spin text-indigo-300" />
                    : <Check size={12} className="text-emerald-400" />}
                  {m.label}
                </div>
                <span className="text-[10px] tabular-nums text-slate-400">
                  {active ? "…" : `${t.durMs} ms`}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${active ? "bg-indigo-400/70 shimmer" : "bg-gradient-to-r from-indigo-500 to-cyan-400"}`}
                  initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.4 }} />
              </div>
              {t.summary && <div className="mt-1.5 text-[10.5px] text-slate-400 leading-snug">{t.summary}</div>}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
