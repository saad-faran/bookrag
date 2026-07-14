import React, { useState } from "react";
import { FileText, Table2, ChevronDown, ExternalLink, Globe } from "lucide-react";
import { openRawFile } from "../lib/api.js";

export default function Sources({ sources }) {
  const [open, setOpen] = useState(false);
  if (!sources?.length) return null;

  // de-dup by title+page
  const seen = new Set();
  const uniq = sources.filter((s) => {
    const k = `${s.title}|${s.page}|${s.element_type}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });

  const openSource = (s) => {
    if (s.source === "project" && s.project_id && s.doc_id) openRawFile(s.project_id, s.doc_id);
    else if (s.source === "web" && s.url) window.open(s.url, "_blank");
  };

  return (
    <div className="mt-2">
      <button onClick={() => setOpen((o) => !o)}
        className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center gap-1 transition">
        <ChevronDown size={13} className={`transition ${open ? "rotate-180" : ""}`} />
        {uniq.length} sources
      </button>
      {open && (
        <div className="mt-2 grid gap-1.5">
          {uniq.map((s, i) => {
            const clickable = (s.source === "project" && s.doc_id) || (s.source === "web" && s.url);
            const Icon = s.source === "web" ? Globe
              : s.element_type === "table" ? Table2 : FileText;
            return (
              <div key={i} onClick={() => clickable && openSource(s)}
                className={`glass !rounded-xl px-3 py-2 flex items-center gap-2 ${clickable ? "cursor-pointer hover:border-indigo-500/50 transition" : ""}`}>
                <Icon size={14} className={`shrink-0 ${s.source === "web" ? "text-cyan-300" : s.element_type === "table" ? "text-rose-300" : "text-sky-300"}`} />
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] font-medium truncate">{s.title || "document"}</div>
                  <div className="text-[10px] text-slate-500">
                    {s.source === "project" ? "📎 uploaded" : s.source}
                    {s.page ? ` · p.${s.page}` : ""}{s.rrf_score ? ` · ${s.rrf_score}` : ""}
                  </div>
                </div>
                {clickable && <ExternalLink size={12} className="text-slate-500 shrink-0" />}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
