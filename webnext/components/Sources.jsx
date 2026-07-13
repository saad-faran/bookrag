import React, { useState } from "react";
import { FileText, Table2, ChevronDown } from "lucide-react";

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

  return (
    <div className="mt-2">
      <button onClick={() => setOpen((o) => !o)}
        className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center gap-1 transition">
        <ChevronDown size={13} className={`transition ${open ? "rotate-180" : ""}`} />
        {uniq.length} sources
      </button>
      {open && (
        <div className="mt-2 grid gap-1.5">
          {uniq.map((s, i) => (
            <div key={i} className="glass !rounded-xl px-3 py-2 flex items-center gap-2">
              {s.element_type === "table"
                ? <Table2 size={14} className="text-rose-300 shrink-0" />
                : <FileText size={14} className="text-sky-300 shrink-0" />}
              <div className="min-w-0 flex-1">
                <div className="text-[12px] font-medium truncate">{s.title || "document"}</div>
                <div className="text-[10px] text-slate-500">
                  {s.source}{s.page ? ` · p.${s.page}` : ""} · fusion {s.rrf_score}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
