"use client";
import React, { useEffect, useState } from "react";
import { Activity, AlertTriangle, BarChart3, Clock, Cpu, Globe, MessageSquare,
  RefreshCw, ShieldCheck, Users, Wrench, X } from "lucide-react";
import * as api from "../lib/api.js";

function Tile({ icon: Icon, label, value, tone = "indigo" }) {
  const tones = {
    indigo: "text-indigo-300 bg-indigo-500/15 border-indigo-500/30",
    emerald: "text-emerald-300 bg-emerald-500/15 border-emerald-500/30",
    cyan: "text-cyan-300 bg-cyan-500/15 border-cyan-500/30",
    rose: "text-rose-300 bg-rose-500/15 border-rose-500/30",
    fuchsia: "text-fuchsia-300 bg-fuchsia-500/15 border-fuchsia-500/30",
  };
  return (
    <div className="glass !rounded-xl px-3 py-2.5 flex items-center gap-3">
      <div className={`w-8 h-8 rounded-lg border flex items-center justify-center shrink-0 ${tones[tone]}`}>
        <Icon size={15} />
      </div>
      <div className="min-w-0">
        <div className="text-[10.5px] text-slate-400">{label}</div>
        <div className="text-[17px] font-bold tabular-nums leading-tight">{value}</div>
      </div>
    </div>
  );
}

function Bars({ title, data, unit = "", color = "from-indigo-500 to-cyan-400" }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="glass !rounded-xl p-3">
      <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-2">{title}</div>
      {data.length === 0 && <div className="text-[11px] text-slate-500">No data yet.</div>}
      <div className="space-y-1.5">
        {data.map((d) => (
          <div key={d.label}>
            <div className="flex justify-between text-[11px] mb-0.5">
              <span className="font-mono text-slate-300">{d.label}</span>
              <span className="tabular-nums text-slate-400">{d.value}{unit}</span>
            </div>
            <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
              <div className={`h-full rounded-full bg-gradient-to-r ${color}`}
                style={{ width: `${Math.max(4, (d.value / max) * 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const LEVEL_COLOR = { error: "text-rose-400", warn: "text-amber-400", info: "text-slate-400" };

export default function Analytics({ onClose }) {
  const [a, setA] = useState(null);
  const [mcp, setMcp] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    const [an, mc] = await Promise.all([
      api.getAnalytics().catch(() => null), api.getMcp().catch(() => null),
    ]);
    setA(an); setMcp(mc); setLoading(false);
  };
  useEffect(() => { load(); const iv = setInterval(load, 5000); return () => clearInterval(iv); }, []);

  const t = a?.totals || {};
  const routes = Object.entries(a?.routes || {}).map(([label, value]) => ({ label, value }));
  const nodes = (a?.node_latency || []).map((n) => ({ label: n.step, value: n.avg_ms }));
  const tools = (a?.top_tools || []).map((x) => ({ label: x.name, value: x.count }));
  const g = a?.grounding || {};
  const groundRate = (g.verified + g.unverified) ? Math.round((g.verified / (g.verified + g.unverified)) * 100) : 0;

  return (
    <div className="glass flex flex-col min-w-0 min-h-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--border)] flex items-center justify-between">
        <div>
          <div className="text-[15px] font-bold flex items-center gap-2">
            <BarChart3 size={16} className="text-cyan-300" /> Observability
          </div>
          <div className="text-[11px] text-slate-400">
            Every pipeline step is logged to the database · live from <span className="font-mono">event_logs</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="icon-btn" title="Refresh"><RefreshCw size={14} /></button>
          <button onClick={onClose} className="icon-btn" title="Close"><X size={15} /></button>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
        {loading && <div className="text-[12px] text-slate-500">Loading…</div>}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Tile icon={MessageSquare} label="Queries" value={t.queries ?? 0} />
          <Tile icon={Clock} label="Avg latency" value={`${((t.avg_latency_ms ?? 0) / 1000).toFixed(2)}s`} tone="cyan" />
          <Tile icon={ShieldCheck} label="Grounded" value={`${groundRate}%`} tone="emerald" />
          <Tile icon={AlertTriangle} label="Errors" value={t.errors ?? 0} tone={t.errors ? "rose" : "indigo"} />
          <Tile icon={Wrench} label="Tool calls" value={t.tool_calls ?? 0} />
          <Tile icon={Cpu} label="MCP calls" value={t.mcp_calls ?? 0} tone="fuchsia" />
          <Tile icon={Globe} label="Web searches" value={t.web_searches ?? 0} tone="cyan" />
          <Tile icon={Users} label="Users" value={t.users ?? 0} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Bars title="Route distribution" data={routes} />
          <Bars title="Avg latency per node" data={nodes} unit=" ms" color="from-fuchsia-500 to-indigo-400" />
          <Bars title="Top tools" data={tools} color="from-emerald-500 to-cyan-400" />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="glass !rounded-xl p-3">
            <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-2">Grounding gate</div>
            <div className="text-[12px] space-y-1">
              <div className="flex justify-between"><span className="text-emerald-400">✓ verified</span><span className="tabular-nums">{g.verified ?? 0}</span></div>
              <div className="flex justify-between"><span className="text-amber-400">⚠ unverified</span><span className="tabular-nums">{g.unverified ?? 0}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">↻ retried</span><span className="tabular-nums">{g.retried ?? 0}</span></div>
            </div>
          </div>
          <div className="glass !rounded-xl p-3">
            <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-2">MCP servers</div>
            {mcp?.servers?.length ? mcp.servers.map((s) => (
              <div key={s.name} className="text-[12px] mb-1">
                <span className="text-fuchsia-300 font-medium">{s.name}</span>
                <span className="text-slate-500"> · {s.tools.length} tools</span>
                <div className="text-[10px] text-slate-500 font-mono truncate">
                  {s.tools.map((x) => x.name).join(", ")}
                </div>
              </div>
            )) : <div className="text-[11px] text-slate-500">No MCP servers connected.</div>}
          </div>
          <div className="glass !rounded-xl p-3">
            <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-2">Volume</div>
            <div className="text-[12px] space-y-1">
              <div className="flex justify-between"><span className="text-slate-400">events logged</span><span className="tabular-nums">{t.events ?? 0}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">queries</span><span className="tabular-nums">{t.queries ?? 0}</span></div>
            </div>
          </div>
        </div>

        <div className="glass !rounded-xl p-3">
          <div className="text-[11px] uppercase tracking-wide text-slate-500 mb-2 flex items-center gap-1.5">
            <Activity size={12} /> Recent events (live)
          </div>
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-[11px]">
              <thead className="text-slate-500 sticky top-0 bg-[var(--card)]">
                <tr className="text-left">
                  <th className="py-1 font-medium">time</th>
                  <th className="font-medium">step</th>
                  <th className="font-medium">latency</th>
                  <th className="font-medium">detail</th>
                </tr>
              </thead>
              <tbody>
                {(a?.recent || []).map((r) => (
                  <tr key={r.id} className="border-t border-[var(--border)]">
                    <td className="py-1 text-slate-500 tabular-nums whitespace-nowrap">
                      {new Date(r.ts * 1000).toLocaleTimeString()}
                    </td>
                    <td className={`font-mono ${LEVEL_COLOR[r.level] || "text-slate-300"}`}>{r.step}</td>
                    <td className="tabular-nums text-slate-400">{r.latency_ms ? `${r.latency_ms} ms` : "—"}</td>
                    <td className="text-slate-500 truncate max-w-[380px]">
                      {r.payload?.summary || r.payload?.route || r.payload?.message || r.payload?.email || ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
