"use client";
import React, { useRef, useState } from "react";
import { FolderPlus, Folder, FolderOpen, Upload, FileText, Image, Music,
  Loader2, Check, AlertCircle, Trash2, X } from "lucide-react";

function fileIcon(kind) {
  if (kind === "image") return Image;
  if (kind === "audio") return Music;
  return FileText;
}

export default function Projects({ projects, activeId, files, uploading, onSelect,
  onCreate, onUpload, onDeleteProject }) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const inputRef = useRef(null);

  const submit = () => {
    const n = name.trim();
    if (n) { onCreate(n); setName(""); setCreating(false); }
  };

  return (
    <div className="mb-2">
      <div className="flex items-center justify-between px-1 mb-1">
        <div className="text-[11px] uppercase tracking-wide text-slate-500">Projects</div>
        <button onClick={() => setCreating((c) => !c)} title="New project"
          className="text-slate-400 hover:text-indigo-300 transition">
          {creating ? <X size={14} /> : <FolderPlus size={14} />}
        </button>
      </div>

      {creating && (
        <div className="px-1 mb-2">
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Project name…"
            className="w-full glass !rounded-lg px-2.5 py-1.5 text-[12px] bg-transparent outline-none focus:border-indigo-500/60" />
        </div>
      )}

      <div className="space-y-1 max-h-40 overflow-y-auto pr-1">
        {projects.length === 0 && !creating && (
          <div className="text-[11px] text-slate-500 px-1 py-1">
            Create a project to upload your own docs.
          </div>
        )}
        {projects.map((p) => {
          const active = p.id === activeId;
          return (
            <div key={p.id}>
              <div onClick={() => onSelect(active ? null : p.id)}
                className={`group flex items-center gap-2 px-2.5 py-1.5 rounded-lg cursor-pointer transition
                  ${active ? "bg-indigo-500/20 border border-indigo-500/40" : "hover:bg-white/5 border border-transparent"}`}>
                {active ? <FolderOpen size={14} className="text-indigo-300 shrink-0" />
                  : <Folder size={14} className="text-slate-400 shrink-0" />}
                <div className="flex-1 min-w-0">
                  <div className="text-[12.5px] truncate">{p.name}</div>
                  <div className="text-[10px] text-slate-500">{p.n_files} file{p.n_files === 1 ? "" : "s"}</div>
                </div>
                <button onClick={(e) => { e.stopPropagation(); onDeleteProject(p.id); }}
                  className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-rose-400 transition">
                  <Trash2 size={13} />
                </button>
              </div>

              {active && (
                <div className="mt-1 ml-2 pl-2 border-l border-[var(--border)] space-y-1">
                  {(files || []).map((f) => {
                    const Icon = fileIcon(f.kind);
                    return (
                      <div key={f.id} className="flex items-center gap-1.5 text-[11px] text-slate-300 py-0.5">
                        <Icon size={11} className="text-slate-400 shrink-0" />
                        <span className="flex-1 truncate">{f.filename}</span>
                        {f.status === "processing" ? <Loader2 size={11} className="animate-spin text-indigo-300" />
                          : f.status === "error" ? <AlertCircle size={11} className="text-rose-400" />
                          : <Check size={11} className="text-emerald-400" />}
                      </div>
                    );
                  })}
                  <button onClick={() => inputRef.current?.click()} disabled={uploading}
                    className="w-full mt-1 flex items-center justify-center gap-1.5 text-[11px] text-indigo-300
                               border border-dashed border-indigo-500/40 rounded-lg py-1.5 hover:bg-indigo-500/10 transition disabled:opacity-50">
                    {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
                    {uploading ? "Uploading…" : "Upload files"}
                  </button>
                  <input ref={inputRef} type="file" multiple hidden
                    accept=".pdf,.txt,.md,.csv,.docx,.htm,.html,.png,.jpg,.jpeg,.webp,.gif,.mp3,.wav,.m4a,.flac,.ogg"
                    onChange={(e) => { onUpload([...e.target.files]); e.target.value = ""; }} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
