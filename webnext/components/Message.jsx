import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion } from "framer-motion";
import { BookOpen, ShieldCheck, ShieldAlert } from "lucide-react";
import Sources from "./Sources.jsx";
import RunInspector from "./RunInspector.jsx";

export default function Message({ msg, live }) {
  const isUser = msg.role === "user";
  if (isUser) {
    return (
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
        className="flex justify-end">
        <div className="bubble-user text-white px-4 py-2.5 max-w-[80%] text-[14px] leading-relaxed shadow-lg">
          {msg.content}
        </div>
      </motion.div>
    );
  }

  const grounded = msg.trace?.is_grounded;
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      className="flex gap-2.5 items-start">
      <div className="w-8 h-8 rounded-xl bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center shrink-0 mt-0.5">
        <BookOpen size={16} className="text-indigo-300" />
      </div>
      <div className="bubble-ai px-4 py-3 max-w-[85%] min-w-0">
        <div className={`md text-[14px] text-[var(--text)] ${live ? "caret" : ""}`}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {msg.content || "…"}
          </ReactMarkdown>
        </div>

        {!live && msg.trace?.route === "rag" && grounded !== undefined && (
          <div className="mt-1.5 flex items-center gap-1.5 text-[11px]">
            {grounded
              ? <span className="flex items-center gap-1 text-emerald-400"><ShieldCheck size={13} /> Verified against sources</span>
              : <span className="flex items-center gap-1 text-amber-400"><ShieldAlert size={13} /> Could not fully verify</span>}
            {msg.trace?.retry_count > 0 && <span className="text-slate-500">· retried once</span>}
          </div>
        )}

        {!live && <Sources sources={msg.sources} />}
        {!live && <RunInspector record={msg.record || msg.trace} />}
      </div>
    </motion.div>
  );
}
