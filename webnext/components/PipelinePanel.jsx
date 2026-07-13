"use client";
import React, { useEffect, useMemo } from "react";
import {
  ReactFlow, Background, Handle, Position, useNodesState, useEdgesState, useReactFlow, ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Compass, Search, PenLine, ShieldCheck, RefreshCw, MessageCircle, Package, Check, Loader2, GitBranch,
} from "lucide-react";
import PanelControls from "./PanelControls.jsx";

const ICONS = { compass: Compass, search: Search, pen: PenLine, shield: ShieldCheck,
  refresh: RefreshCw, chat: MessageCircle, package: Package };

const POS = {
  rewrite_and_route: { x: 40, y: 15 },
  general_answer:    { x: 225, y: 15 },
  retrieve:          { x: 40, y: 110 },
  generate:          { x: 40, y: 200 },
  evaluate_grounding:{ x: 40, y: 290 },
  expand_query:      { x: 225, y: 290 },
  build_final_answer:{ x: 40, y: 390 },
};

// target handles available: Top (default), "l" (Left). source handles: Bottom (default), "r" (Right).
const EDGES = [
  { id: "e1", source: "rewrite_and_route", target: "retrieve" },
  { id: "e2", source: "rewrite_and_route", target: "general_answer", sourceHandle: "r", targetHandle: "l" },
  { id: "e3", source: "retrieve", target: "generate" },
  { id: "e4", source: "generate", target: "evaluate_grounding" },
  { id: "e5", source: "evaluate_grounding", target: "build_final_answer" },
  { id: "e6", source: "evaluate_grounding", target: "expand_query", sourceHandle: "r", targetHandle: "l" },
  { id: "e7", source: "expand_query", target: "retrieve", targetHandle: "l" },
  { id: "e8", source: "general_answer", target: "build_final_answer", targetHandle: "l" },
];

function PipeNode({ data }) {
  const Icon = ICONS[data.meta.icon] || GitBranch;
  const st = data.status;
  const ring = st === "active" ? "border-indigo-400 pulse"
    : st === "done" ? "border-emerald-500/60"
    : "border-[var(--border2)]";
  const sel = data.selected ? "ring-2 ring-cyan-400/70" : "";
  return (
    <div onClick={data.onSelect}
      className={`w-[150px] rounded-xl border ${ring} ${sel} bg-[var(--card)] px-2.5 py-2 cursor-pointer transition
        ${st === "idle" ? "opacity-55" : "opacity-100"}`}>
      <Handle type="target" position={Position.Top} className="!bg-slate-500" />
      <Handle id="l" type="target" position={Position.Left} className="!bg-slate-500" />
      <div className="flex items-center gap-2">
        <div className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0
          ${st === "active" ? "bg-indigo-500/25 text-indigo-300"
            : st === "done" ? "bg-emerald-500/20 text-emerald-300" : "bg-white/5 text-slate-400"}`}>
          {st === "active" ? <Loader2 size={13} className="animate-spin" />
            : st === "done" ? <Check size={13} /> : <Icon size={13} />}
        </div>
        <div className="min-w-0">
          <div className="text-[11.5px] font-semibold leading-tight truncate">{data.meta.label}</div>
          {st === "done" && data.durMs != null
            ? <div className="text-[9.5px] text-emerald-300/80 tabular-nums">{data.durMs} ms</div>
            : <div className="text-[9.5px] text-slate-500 truncate">{data.meta.short}</div>}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-slate-500" />
      <Handle id="r" type="source" position={Position.Right} className="!bg-slate-500" />
    </div>
  );
}

const nodeTypes = { pipe: PipeNode };

function Flow({ nodesMeta, nodeState, selectedNode, onSelect, theme }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState(EDGES.map((e) => ({ ...e, type: "smoothstep" })));
  const { fitView } = useReactFlow();
  const offStroke = theme === "light" ? "#c4cee0" : "#2a3654";
  const dotColor = theme === "light" ? "#d3dae8" : "#1b2540";

  useEffect(() => {
    setNodes(
      nodesMeta.map((m) => ({
        id: m.id,
        type: "pipe",
        position: POS[m.id] || { x: 40, y: 15 },
        data: {
          meta: m,
          status: nodeState[m.id]?.status || "idle",
          durMs: nodeState[m.id]?.durMs,
          selected: selectedNode === m.id,
          onSelect: () => onSelect(m.id),
        },
      }))
    );
  }, [nodesMeta, nodeState, selectedNode, onSelect, setNodes]);

  useEffect(() => {
    setEdges((eds) => eds.map((e) => {
      const s = nodeState[e.source]?.status, t = nodeState[e.target]?.status;
      const on = s === "done" && (t === "active" || t === "done");
      return { ...e, animated: on, style: { stroke: on ? "#6366f1" : offStroke, strokeWidth: 2 } };
    }));
  }, [nodeState, setEdges, offStroke]);

  useEffect(() => { setTimeout(() => fitView({ padding: 0.18, duration: 300 }), 60); }, [nodesMeta, fitView]);

  return (
    <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes}
      onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
      fitView proOptions={{ hideAttribution: true }}
      minZoom={0.4} maxZoom={1.6} panOnScroll zoomOnScroll
      nodesConnectable={false} nodesDraggable
      className="rounded-xl">
      <Background color={dotColor} gap={18} size={1} />
    </ReactFlow>
  );
}

export default function PipelinePanel({ nodesMeta, nodeState, activeNode, selectedNode, onSelect, theme, onMin, maxed, onToggleMax }) {
  const display = useMemo(
    () => nodesMeta.find((n) => n.id === (selectedNode || activeNode)) || nodesMeta[0],
    [nodesMeta, selectedNode, activeNode]
  );

  return (
    <div className="glass flex flex-col min-w-0 min-h-0 overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--border)] flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[13px] font-bold flex items-center gap-2">
            <GitBranch size={15} className="text-indigo-300" /> RAG Pipeline
          </div>
          <div className="text-[10px] text-slate-400">Live graph · drag, zoom & click nodes</div>
        </div>
        <PanelControls onMin={onMin} maxed={maxed} onToggleMax={onToggleMax} />
      </div>

      <div className="flex-1 min-h-0">
        <ReactFlowProvider>
          <Flow nodesMeta={nodesMeta} nodeState={nodeState} selectedNode={selectedNode} onSelect={onSelect} theme={theme} />
        </ReactFlowProvider>
      </div>

      {display && (
        <div className="m-2 p-3 rounded-xl bg-[var(--card2)] border border-[var(--border)]">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[12px] font-semibold text-indigo-200">{display.label}</span>
            {activeNode === display.id && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300">running</span>
            )}
          </div>
          <div className="text-[11.5px] leading-snug text-slate-400">{display.desc}</div>
        </div>
      )}
    </div>
  );
}
