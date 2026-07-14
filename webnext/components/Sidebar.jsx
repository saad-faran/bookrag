import React from "react";
import { Plus, MessageSquare, Trash2, BookOpen, Database, Table, Layers, Sun, Moon, LogOut, FolderOpen } from "lucide-react";
import Projects from "./Projects.jsx";

function Stat({ icon: Icon, label, value }) {
  return (
    <div className="glass !rounded-xl px-3 py-2 flex items-center gap-2">
      <Icon size={15} className="text-indigo-300" />
      <div className="leading-tight">
        <div className="text-[11px] text-slate-400">{label}</div>
        <div className="text-sm font-semibold">{value ?? "—"}</div>
      </div>
    </div>
  );
}

export default function Sidebar({ chats, activeId, corpus, health, onOpen, onNew, onDelete,
  theme, onToggleTheme, user, onLogout, projects, activeProjectId, projectFiles, uploading,
  onSelectProject, onCreateProject, onUploadFiles, onDeleteProject }) {
  const activeProject = projects?.find((p) => p.id === activeProjectId);
  return (
    <div className="w-[236px] shrink-0 glass flex flex-col p-3">
      <div className="flex items-center gap-2 px-1 pb-3">
        <BookOpen className="text-indigo-400" size={22} />
        <div>
          <div className="text-lg font-extrabold tracking-tight">
            Book<span className="gradient-text">RAG</span>
          </div>
          <div className="text-[10px] text-slate-400 -mt-1">Finance Intelligence</div>
        </div>
      </div>

      <button onClick={onNew}
        className="gradient-btn text-white text-sm font-semibold rounded-xl py-2.5 flex items-center justify-center gap-2 mb-3">
        <Plus size={16} /> New chat{activeProject ? ` · ${activeProject.name}` : ""}
      </button>

      <Projects projects={projects || []} activeId={activeProjectId} files={projectFiles}
        uploading={uploading} onSelect={onSelectProject} onCreate={onCreateProject}
        onUpload={onUploadFiles} onDeleteProject={onDeleteProject} />

      <div className="text-[11px] uppercase tracking-wide text-slate-500 px-1 mb-1">Chats</div>
      <div className="flex-1 overflow-y-auto space-y-1 pr-1">
        {chats.length === 0 && <div className="text-xs text-slate-500 px-1 py-2">No chats yet.</div>}
        {chats.map((c) => (
          <div key={c.id}
            onClick={() => onOpen(c.id)}
            className={`group flex items-center gap-2 px-2.5 py-2 rounded-xl cursor-pointer transition
              ${activeId === c.id ? "bg-indigo-500/20 border border-indigo-500/40" : "hover:bg-white/5 border border-transparent"}`}>
            <MessageSquare size={14} className="text-slate-400 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-[13px] truncate">{c.title}</div>
              <div className="text-[10px] text-slate-500">{c.n} msgs</div>
            </div>
            <button onClick={(e) => { e.stopPropagation(); onDelete(c.id); }}
              className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-rose-400 transition">
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <Stat icon={Database} label="Docs" value={corpus?.documents} />
        <Stat icon={Layers} label="Chunks" value={corpus?.chunks?.toLocaleString?.()} />
        <Stat icon={Table} label="Tables" value={corpus?.table_chunks?.toLocaleString?.()} />
        <Stat icon={BookOpen} label="Sources" value={corpus?.by_source ? Object.keys(corpus.by_source).length : "—"} />
      </div>

      <div className="mt-3 flex items-center gap-2">
        <div className="flex-1 glass !rounded-xl px-3 py-2 text-[11px] flex items-center justify-between">
          <span className="text-slate-400">Engine</span>
          <span className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${health?.ok ? "bg-emerald-400" : "bg-slate-500"}`} />
            {health?.mock ? "mock" : health?.provider || "…"}
          </span>
        </div>
        <button onClick={onToggleTheme} title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          className="glass !rounded-xl px-3 py-2 hover:border-indigo-500/50 transition">
          {theme === "dark" ? <Sun size={15} className="text-amber-300" /> : <Moon size={15} className="text-indigo-400" />}
        </button>
      </div>

      {user && (
        <div className="mt-2 glass !rounded-xl px-3 py-2 flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center text-[12px] font-bold text-indigo-200 shrink-0">
            {(user.name || user.email || "?")[0].toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[12px] font-medium truncate">{user.name || user.email}</div>
            <div className="text-[10px] text-slate-500 truncate">{user.email}</div>
          </div>
          <button onClick={onLogout} title="Sign out"
            className="text-slate-400 hover:text-rose-400 transition shrink-0">
            <LogOut size={15} />
          </button>
        </div>
      )}
    </div>
  );
}
