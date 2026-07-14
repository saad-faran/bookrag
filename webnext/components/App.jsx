"use client";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { GitBranch, Activity } from "lucide-react";
import Sidebar from "./Sidebar.jsx";
import ChatPanel from "./ChatPanel.jsx";
import PipelinePanel from "./PipelinePanel.jsx";
import TracePanel from "./TracePanel.jsx";
import * as api from "../lib/api.js";

function CollapsedStrip({ icon: Icon, label, onExpand }) {
  return (
    <div className="glass flex flex-col items-center py-3 gap-3 min-h-0 overflow-hidden">
      <button className="icon-btn" onClick={onExpand} title={`Expand ${label}`}>
        <Icon size={16} className="text-indigo-300" />
      </button>
      <div className="text-[10px] text-[var(--muted)] tracking-wide"
           style={{ writingMode: "vertical-rl" }}>
        {label}
      </div>
    </div>
  );
}

export default function App({ user, onLogout }) {
  const [health, setHealth] = useState(null);
  const [nodesMeta, setNodesMeta] = useState([]);
  const [corpus, setCorpus] = useState({});
  const [chats, setChats] = useState([]);
  const [activeChat, setActiveChat] = useState(null);
  const [messages, setMessages] = useState([]);

  // projects
  const [projects, setProjects] = useState([]);
  const [activeProjectId, setActiveProjectId] = useState(null);
  const [projectFiles, setProjectFiles] = useState([]);
  const [uploading, setUploading] = useState(false);

  // theme + layout
  const [theme, setTheme] = useState("dark");
  const [maxed, setMaxed] = useState(null);               // null | 'pipeline' | 'chat' | 'trace'
  const [minimized, setMinimized] = useState({ pipeline: false, trace: false });

  // live run state
  const [nodeState, setNodeState] = useState({});
  const [activeNode, setActiveNode] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [traceLog, setTraceLog] = useState([]);
  const [liveAnswer, setLiveAnswer] = useState("");
  const [streaming, setStreaming] = useState(false);
  const runStart = useRef(0);
  const [elapsed, setElapsed] = useState(0);

  // ---- theme init + apply ----
  useEffect(() => {
    const saved = localStorage.getItem("bookrag-theme") || "dark";
    setTheme(saved);
  }, []);
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("bookrag-theme", theme);
  }, [theme]);

  // Load pipeline nodes + corpus stats, retrying until the backend finishes warming up
  // (loading the vector index + models can take 10-20s; a single failed fetch used to
  // leave the flowchart and stats permanently empty).
  useEffect(() => {
    let cancelled = false;
    async function loadMeta() {
      try {
        const [h, n, c] = await Promise.all([api.getHealth(), api.getNodes(), api.getCorpus()]);
        if (cancelled) return;
        if (h) setHealth(h);
        const nodesOk = Array.isArray(n) && n.length > 0;
        const corpusOk = c && Object.keys(c).length > 0;
        if (nodesOk) setNodesMeta(n);
        if (corpusOk) setCorpus(c);
        if (!nodesOk || !corpusOk) throw new Error("backend not ready");
      } catch {
        if (!cancelled) setTimeout(loadMeta, 1500);
      }
    }
    loadMeta();
    refreshChats();
    refreshProjects();
    return () => { cancelled = true; };
  }, []);

  const refreshChats = useCallback(async () => {
    const c = await api.listChats().catch(() => []);
    setChats(c);
    return c;
  }, []);

  const refreshProjects = useCallback(async () => {
    const p = await api.listProjects().catch(() => []);
    setProjects(p);
    return p;
  }, []);

  const loadProjectFiles = useCallback(async (pid) => {
    if (!pid) { setProjectFiles([]); return; }
    const { files } = await api.getProject(pid).catch(() => ({ files: [] }));
    setProjectFiles(files || []);
  }, []);

  const selectProject = useCallback((pid) => {
    setActiveProjectId(pid);
    loadProjectFiles(pid);
  }, [loadProjectFiles]);

  const createProject = useCallback(async (name) => {
    const p = await api.createProject(name);
    await refreshProjects();
    setActiveProjectId(p.id);
    setProjectFiles([]);
  }, [refreshProjects]);

  const deleteProjectById = useCallback(async (pid) => {
    await api.deleteProject(pid);
    await refreshProjects();
    if (activeProjectId === pid) { setActiveProjectId(null); setProjectFiles([]); }
  }, [refreshProjects, activeProjectId]);

  const uploadFiles = useCallback(async (files) => {
    if (!activeProjectId || !files.length) return;
    setUploading(true);
    try {
      for (const f of files) {
        await api.uploadFile(activeProjectId, f).catch(() => {});
      }
      await loadProjectFiles(activeProjectId);
      await refreshProjects();
    } finally {
      setUploading(false);
    }
  }, [activeProjectId, loadProjectFiles, refreshProjects]);

  useEffect(() => {
    if (!streaming) return;
    const iv = setInterval(() => setElapsed(Date.now() - runStart.current), 100);
    return () => clearInterval(iv);
  }, [streaming]);

  const openChat = useCallback(async (id) => {
    const { chat, messages } = await api.getChat(id);
    setActiveChat(chat);
    setMessages(messages);
    resetRun();
  }, []);

  const newChat = useCallback(async () => {
    const c = await api.createChat(activeProjectId || "");
    await refreshChats();
    setActiveChat(c);
    setMessages([]);
    resetRun();
  }, [refreshChats, activeProjectId]);

  const removeChat = useCallback(async (id) => {
    await api.deleteChat(id);
    await refreshChats();
    if (activeChat?.id === id) { setActiveChat(null); setMessages([]); }
  }, [activeChat, refreshChats]);

  function resetRun() {
    setNodeState({});
    setActiveNode(null);
    setSelectedNode(null);
    setTraceLog([]);
    setLiveAnswer("");
  }

  const send = useCallback(async (text) => {
    if (!text.trim() || streaming) return;
    let chat = activeChat;
    if (!chat) { chat = await api.createChat(activeProjectId || ""); setActiveChat(chat); }
    setMessages((m) => [...m, { role: "user", content: text }]);
    resetRun();
    setStreaming(true);
    runStart.current = Date.now();

    let pendingSources = [];
    let pendingTrace = {};
    let pendingRecord = null;
    let answer = "";

    try {
      await api.streamChat(chat.id, text, (ev) => {
        if (ev.type === "node_start") {
          setActiveNode(ev.node);
          setNodeState((s) => ({ ...s, [ev.node]: { status: "active" } }));
          setTraceLog((t) => [...t, { node: ev.node, status: "active", t: Date.now() - runStart.current }]);
        } else if (ev.type === "node_end") {
          setNodeState((s) => ({ ...s, [ev.node]: { status: "done", durMs: ev.dur_ms, summary: ev.summary } }));
          setTraceLog((t) => {
            const copy = [...t];
            for (let i = copy.length - 1; i >= 0; i--) {
              if (copy[i].node === ev.node && copy[i].status === "active") {
                copy[i] = { ...copy[i], status: "done", durMs: ev.dur_ms, summary: ev.summary };
                break;
              }
            }
            return copy;
          });
        } else if (ev.type === "sources") {
          pendingSources = ev.sources || [];
        } else if (ev.type === "trace") {
          pendingTrace = ev.trace || {};
        } else if (ev.type === "record") {
          pendingRecord = ev.record || null;
        } else if (ev.type === "token") {
          answer += ev.text;
          setLiveAnswer(answer);
        } else if (ev.type === "error") {
          answer = `⚠️ ${ev.message}`;
          setLiveAnswer(answer);
        } else if (ev.type === "done") {
          answer = ev.answer;
        }
      });
    } catch (e) {
      answer = answer || `⚠️ Connection error: ${e.message}. Is the backend running on :8000?`;
    }

    setActiveNode(null);
    setStreaming(false);
    setLiveAnswer("");
    setMessages((m) => [...m, { role: "assistant", content: answer, sources: pendingSources,
                                trace: pendingTrace, record: pendingRecord }]);
    refreshChats();
  }, [activeChat, streaming, refreshChats, activeProjectId]);

  // ---- layout helpers ----
  const toggleMax = (panel) => setMaxed((m) => (m === panel ? null : panel));
  const setMin = (panel, v) => { setMinimized((s) => ({ ...s, [panel]: v })); if (v && maxed === panel) setMaxed(null); };

  const showPipeline = !maxed || maxed === "pipeline";
  const showChat = !maxed || maxed === "chat";
  const showTrace = !maxed || maxed === "trace";

  let gridCols;
  if (maxed) {
    gridCols = "minmax(0,1fr)";
  } else {
    const left = minimized.pipeline ? "46px" : "300px";
    const right = minimized.trace ? "46px" : "320px";
    gridCols = `${left} minmax(0,1fr) ${right}`;
  }

  const pipelineEl = maxed && maxed !== "pipeline" ? null
    : minimized.pipeline
      ? <CollapsedStrip key="pipe" icon={GitBranch} label="RAG Pipeline" onExpand={() => setMin("pipeline", false)} />
      : <PipelinePanel key="pipe"
          nodesMeta={nodesMeta} nodeState={nodeState} activeNode={activeNode}
          selectedNode={selectedNode} onSelect={setSelectedNode} theme={theme}
          onMin={() => setMin("pipeline", true)} maxed={maxed === "pipeline"} onToggleMax={() => toggleMax("pipeline")} />;

  const traceEl = maxed && maxed !== "trace" ? null
    : minimized.trace
      ? <CollapsedStrip key="trace" icon={Activity} label="Pipeline Trace" onExpand={() => setMin("trace", false)} />
      : <TracePanel key="trace"
          traceLog={traceLog} nodesMeta={nodesMeta} streaming={streaming}
          elapsed={elapsed} selectedNode={selectedNode} onSelect={setSelectedNode}
          onMin={() => setMin("trace", true)} maxed={maxed === "trace"} onToggleMax={() => toggleMax("trace")} />;

  return (
    <div className="h-full w-full flex gap-3 p-3">
      <Sidebar
        chats={chats} activeId={activeChat?.id} corpus={corpus} health={health}
        onOpen={openChat} onNew={newChat} onDelete={removeChat}
        theme={theme} onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        user={user} onLogout={onLogout}
        projects={projects} activeProjectId={activeProjectId} projectFiles={projectFiles}
        uploading={uploading} onSelectProject={selectProject} onCreateProject={createProject}
        onUploadFiles={uploadFiles} onDeleteProject={deleteProjectById}
      />

      <div className="flex-1 grid gap-3 min-w-0 min-h-0" style={{ gridTemplateColumns: gridCols }}>
        {showPipeline && pipelineEl}
        {showChat && (
          <ChatPanel key="chat"
            messages={messages} liveAnswer={liveAnswer} streaming={streaming}
            activeNode={activeNode} nodeState={nodeState} nodesMeta={nodesMeta} elapsed={elapsed}
            onSend={send} health={health}
            maxed={maxed === "chat"} onToggleMax={() => toggleMax("chat")} />
        )}
        {showTrace && traceEl}
      </div>
    </div>
  );
}
