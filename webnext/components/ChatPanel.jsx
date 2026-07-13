import React, { useEffect, useRef, useState } from "react";
import { Send, Sparkles } from "lucide-react";
import Message from "./Message.jsx";
import PanelControls from "./PanelControls.jsx";

const SUGGESTIONS = [
  "What are NVIDIA's main risk factors?",
  "How should a beginner build long-term wealth?",
  "Summarize World Bank rural finance objectives",
];

// Relative cost of each node (drives the progress bar) and a rough expected duration
// (ms) used to creep the bar smoothly *within* a long-running node.
const NODE_WEIGHT = { rewrite_and_route: 1, retrieve: 2, generate: 5, evaluate_grounding: 4,
  general_answer: 4, expand_query: 1, build_final_answer: 0.3 };
const NODE_EXPECT_MS = { rewrite_and_route: 700, retrieve: 1000, generate: 4500,
  evaluate_grounding: 3000, general_answer: 2500, expand_query: 700, build_final_answer: 150 };

export default function ChatPanel({ messages, liveAnswer, streaming, activeNode, nodeState = {}, nodesMeta, elapsed, onSend, health, maxed, onToggleMax }) {
  const [text, setText] = useState("");
  const scrollRef = useRef(null);
  const activeMeta = nodesMeta.find((n) => n.id === activeNode);

  // Track when the current node became active (set during render for correctness).
  const activeSince = useRef(0);
  const prevActive = useRef(null);
  if (activeNode !== prevActive.current) { prevActive.current = activeNode; activeSince.current = Date.now(); }

  // Progress 0..1 based on completed node weights + a time-based creep for the active node.
  const isGeneral = "general_answer" in nodeState;
  const totalW = isGeneral ? 5.3 : 12.3;
  let doneW = 0;
  for (const id in nodeState) if (nodeState[id]?.status === "done") doneW += NODE_WEIGHT[id] || 0;
  let activeW = 0;
  if (activeNode && nodeState[activeNode]?.status === "active") {
    const ae = Date.now() - activeSince.current;
    const frac = Math.min(0.92, ae / (NODE_EXPECT_MS[activeNode] || 2000));
    activeW = (NODE_WEIGHT[activeNode] || 1) * frac;
  }
  const progress = Math.max(0.05, Math.min(0.97, (doneW + activeW) / totalW));
  const pct = Math.round(progress * 100);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, liveAnswer, streaming]);

  const submit = () => { if (text.trim() && !streaming) { onSend(text); setText(""); } };

  const empty = messages.length === 0 && !streaming;

  return (
    <div className="glass flex flex-col min-w-0 min-h-0">
      <div className="px-5 py-3 border-b border-[var(--border)] flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[15px] font-bold flex items-center gap-2">
            <Sparkles size={16} className="text-cyan-300" /> Assistant
          </div>
          <div className="text-[11px] text-slate-400">Grounded answers over a multimodal finance corpus</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {health?.mock && (
            <span className="text-[10px] px-2 py-1 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
              mock mode — add GROQ_API_KEY
            </span>
          )}
          <PanelControls maxed={maxed} onToggleMax={onToggleMax} />
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto px-5 py-4 space-y-4">
        {empty && (
          <div className="h-full flex flex-col items-center justify-center text-center gap-4">
            <div className="w-14 h-14 rounded-2xl gradient-btn flex items-center justify-center">
              <Sparkles className="text-white" />
            </div>
            <div>
              <div className="text-lg font-semibold">Ask about markets, filings & wealth</div>
              <div className="text-sm text-slate-400">Watch the RAG pipeline execute live on both sides.</div>
            </div>
            <div className="flex flex-wrap gap-2 justify-center max-w-md">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => onSend(s)}
                  className="text-[12px] px-3 py-1.5 rounded-full border border-[var(--border2)] hover:border-indigo-500/60 hover:bg-indigo-500/10 transition">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => <Message key={i} msg={m} />)}

        {streaming && (
          <div>
            {!liveAnswer && (
              <div className="flex gap-2.5 items-center">
                <div className="w-8 h-8 rounded-xl bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center shrink-0">
                  <Sparkles size={15} className="text-indigo-300 animate-pulse" />
                </div>
                <div className="bubble-ai px-4 py-3 flex-1 max-w-[70%]">
                  <div className="flex items-center justify-between text-[12px] mb-2">
                    <span className="text-indigo-200">{activeMeta?.label || "Thinking…"}</span>
                    <span className="text-slate-500 tabular-nums">{pct}% · {(elapsed / 1000).toFixed(1)}s</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-indigo-500 to-cyan-400 rounded-full transition-[width] duration-300 ease-out"
                         style={{ width: `${pct}%` }} />
                  </div>
                </div>
              </div>
            )}
            {liveAnswer && <Message msg={{ role: "assistant", content: liveAnswer }} live />}
          </div>
        )}
      </div>

      <div className="p-3 border-t border-[var(--border)]">
        <div className="flex items-end gap-2 glass !rounded-2xl px-3 py-2">
          <textarea
            value={text} rows={1}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
            placeholder="Ask about a company, filing, or wealth-building…"
            className="flex-1 bg-transparent resize-none outline-none text-[14px] max-h-32 py-1.5 placeholder:text-slate-500"
          />
          <button onClick={submit} disabled={streaming || !text.trim()}
            className="gradient-btn disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl p-2.5">
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
