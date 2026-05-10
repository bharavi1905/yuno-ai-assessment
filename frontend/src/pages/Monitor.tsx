import { useState, useEffect, useRef } from "react";
import { runsApi, type Run } from "../lib/api";
import { createLogStream, createMonitorStream, type LogEvent } from "../lib/websocket";
import { relativeTime, formatCost, truncateId, STATUS_COLORS, NODE_COLORS } from "../lib/utils";
import WorkflowCanvas from "../components/WorkflowCanvas";
import HITLPanel from "../components/HITLPanel";

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? "#7b7f9e";
  return (
    <span
      className="px-2 py-0.5 rounded-full text-xs font-medium"
      style={{ color, background: color + "20", border: `1px solid ${color}40` }}
    >
      {status}
    </span>
  );
}

export default function Monitor() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [nodeStatuses, setNodeStatuses] = useState<Record<string, "idle" | "active" | "completed" | "error">>({});
  const [runEvents, setRunEvents] = useState<(LogEvent & { _ts: number })[]>([]);
  const [globalEvents, setGlobalEvents] = useState<(LogEvent & { _ts: number })[]>([]);
  const [connected, setConnected] = useState(false);

  const runFeedRef = useRef<HTMLDivElement>(null);
  const globalFeedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    runsApi.list({ limit: 20 }).then(setRuns).catch(console.error);
    const interval = setInterval(() => {
      runsApi.list({ limit: 20 }).then(setRuns).catch(console.error);
    }, 10_000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const stop = createMonitorStream(
      (ev) => setGlobalEvents((prev) => [...prev, { ...ev, _ts: Date.now() }].slice(-50)),
      setConnected,
    );
    return stop;
  }, []);

  useEffect(() => {
    if (globalFeedRef.current) {
      globalFeedRef.current.scrollTop = globalFeedRef.current.scrollHeight;
    }
  }, [globalEvents]);

  useEffect(() => {
    if (!selectedRun) return;
    setRunEvents([]);
    setNodeStatuses({});

    const stop = createLogStream(selectedRun.run_id, (ev) => {
      setRunEvents((prev) => [...prev, { ...ev, _ts: Date.now() }].slice(-100));
      if (ev.node) {
        if (ev.type === "node_start") {
          setNodeStatuses((prev) => ({ ...prev, [ev.node!]: "active" }));
        } else if (ev.type === "node_complete") {
          setNodeStatuses((prev) => ({ ...prev, [ev.node!]: "completed" }));
        } else if (ev.type === "node_error") {
          setNodeStatuses((prev) => ({ ...prev, [ev.node!]: "error" }));
        }
      }
    });

    return stop;
  }, [selectedRun?.run_id]);

  useEffect(() => {
    if (runFeedRef.current) {
      runFeedRef.current.scrollTop = runFeedRef.current.scrollHeight;
    }
  }, [runEvents]);

  const activeRuns = runs.filter((r) => r.status === "running" || r.status === "hitl_pending");
  const recentRuns = runs.slice(0, 20);

  return (
    <div className="flex h-full">
      {/* Column 1 — run list */}
      <div className="w-[280px] flex-shrink-0 border-r border-[#2e3149] flex flex-col">
        <div className="px-4 py-3 border-b border-[#2e3149]">
          <div className="flex items-center justify-between">
            <h2 className="text-[#e8eaf0] font-medium text-sm">Active Runs</h2>
            <span
              className={`px-2 py-0.5 rounded-full text-xs ${
                connected ? "bg-[#22c55e]/20 text-[#22c55e]" : "bg-[#ef4444]/20 text-[#ef4444]"
              }`}
            >
              {connected ? "● Live" : "○ Offline"}
            </span>
          </div>
        </div>

        {activeRuns.length > 0 && (
          <div className="px-3 py-2 border-b border-[#2e3149] space-y-1">
            {activeRuns.map((r) => (
              <button
                key={r.id}
                onClick={() => setSelectedRun(r)}
                className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-colors ${
                  selectedRun?.id === r.id
                    ? "bg-[#6c63ff]/20 border border-[#6c63ff]/40"
                    : "hover:bg-[#252836] border border-transparent"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse flex-shrink-0" />
                  <span className="font-mono text-[#e8eaf0]">{truncateId(r.run_id)}</span>
                </div>
                <div className="mt-0.5 text-[#7b7f9e]">{r.workflow_type}</div>
              </button>
            ))}
          </div>
        )}

        <div className="px-4 py-2 border-b border-[#2e3149]">
          <p className="text-[#7b7f9e] text-xs font-medium uppercase tracking-wider">Recent</p>
        </div>

        <div className="flex-1 overflow-y-auto">
          {recentRuns.length === 0 ? (
            <p className="text-[#7b7f9e] text-xs text-center py-6">No runs yet.</p>
          ) : (
            recentRuns.map((r) => (
              <button
                key={r.id}
                onClick={() => setSelectedRun(r)}
                className={`w-full text-left px-4 py-2.5 border-b border-[#2e3149]/40 transition-colors ${
                  selectedRun?.id === r.id
                    ? "bg-[#252836]"
                    : "hover:bg-[#1a1d27]"
                }`}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="font-mono text-[#e8eaf0] text-xs">{truncateId(r.run_id)}</span>
                  <StatusBadge status={r.status} />
                </div>
                <div className="flex items-center justify-between mt-1">
                  <span className="text-[#7b7f9e] text-xs">{r.workflow_type}</span>
                  <span className="text-[#7b7f9e] text-xs">{formatCost(r.total_cost_usd)}</span>
                </div>
                <div className="text-[#7b7f9e] text-xs mt-0.5">{relativeTime(r.started_at)}</div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Column 2 — canvas */}
      <div className="flex-1 flex flex-col border-r border-[#2e3149] min-w-0">
        <div className="px-4 py-3 border-b border-[#2e3149] flex items-center justify-between">
          <h2 className="text-[#e8eaf0] font-medium text-sm">
            {selectedRun
              ? `${selectedRun.workflow_type} — ${truncateId(selectedRun.run_id)}`
              : "Workflow Canvas"}
          </h2>
          {selectedRun && (
            <div className="flex items-center gap-3 text-xs text-[#7b7f9e]">
              {Object.values(nodeStatuses).some((v) => v === "active") && (
                <span className="flex items-center gap-1.5 text-[#6c63ff]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#6c63ff] animate-pulse" />
                  Executing
                </span>
              )}
              <StatusBadge status={selectedRun.status} />
            </div>
          )}
        </div>

        <div className="flex-1">
          {selectedRun ? (
            <WorkflowCanvas
              workflowType={selectedRun.workflow_type as "food_ordering" | "complaint_resolution"}
              nodeStatuses={nodeStatuses}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center text-[#7b7f9e]">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" className="w-12 h-12 mb-3 opacity-30">
                <rect x="3" y="3" width="7" height="7" rx="1" strokeWidth="1.5" />
                <rect x="14" y="3" width="7" height="7" rx="1" strokeWidth="1.5" />
                <rect x="3" y="14" width="7" height="7" rx="1" strokeWidth="1.5" />
                <rect x="14" y="14" width="7" height="7" rx="1" strokeWidth="1.5" />
              </svg>
              <p className="text-sm">Select a run to view its execution graph</p>
            </div>
          )}
        </div>

        {/* Run-specific log strip / HITL panel */}
        {selectedRun && (
          selectedRun.status === "hitl_pending" ? (
            <div className="border-t border-[#2e3149]" style={{ height: "280px" }}>
              <HITLPanel
                runId={selectedRun.run_id}
                onResolved={() => {
                  runsApi.list({ limit: 20 }).then(setRuns).catch(console.error);
                  // Refresh again after a short delay to pick up updated status
                  setTimeout(() => {
                    runsApi.list({ limit: 20 }).then((updated) => {
                      setRuns(updated);
                      const refreshed = updated.find((r) => r.id === selectedRun.id);
                      if (refreshed) setSelectedRun(refreshed);
                    }).catch(console.error);
                  }, 1500);
                }}
              />
            </div>
          ) : (
            <div className="border-t border-[#2e3149]" style={{ height: "180px" }}>
              <div className="px-4 py-2 border-b border-[#2e3149] flex items-center gap-2">
                <span className="text-[#7b7f9e] text-xs font-medium">Run Log</span>
                <span className="text-[#7b7f9e] text-xs ml-auto">{runEvents.length} events</span>
              </div>
              <div ref={runFeedRef} className="overflow-y-auto p-3 space-y-1" style={{ height: "140px" }}>
                {runEvents.length === 0 ? (
                  <p className="text-[#7b7f9e] text-xs text-center py-4">Waiting for events…</p>
                ) : (
                  runEvents.map((ev, i) => {
                    const color = ev.node ? (NODE_COLORS[ev.node] ?? "#7b7f9e") : "#7b7f9e";
                    return (
                      <div key={i} className="flex items-start gap-2 text-xs">
                        <span className="text-[#7b7f9e] flex-shrink-0 font-mono">
                          {new Date(ev._ts).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                        </span>
                        <span className="font-medium flex-shrink-0" style={{ color }}>
                          {ev.node ?? "sys"}
                        </span>
                        <span className="text-[#7b7f9e]">{ev.type}</span>
                        {ev.message && (
                          <span className="text-[#7b7f9e] truncate">{String(ev.message)}</span>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )
        )}
      </div>

      {/* Column 3 — global activity */}
      <div className="w-[300px] flex-shrink-0 flex flex-col">
        <div className="px-4 py-3 border-b border-[#2e3149] flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-[#22c55e] animate-pulse" />
          <h2 className="text-[#e8eaf0] font-medium text-sm">Live Activity</h2>
          <span className="text-[#7b7f9e] text-xs ml-auto">{globalEvents.length}</span>
        </div>

        <div ref={globalFeedRef} className="flex-1 overflow-y-auto p-3 space-y-1.5">
          {globalEvents.length === 0 ? (
            <p className="text-[#7b7f9e] text-sm text-center py-8">Waiting for activity…</p>
          ) : (
            globalEvents.map((ev, i) => {
              const color = ev.node ? (NODE_COLORS[ev.node] ?? "#7b7f9e") : "#7b7f9e";
              return (
                <div key={i} className="px-2 py-1.5 rounded-lg hover:bg-[#252836] transition-colors">
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                    <span className="text-xs font-medium" style={{ color }}>{ev.node ?? "system"}</span>
                    <span className="text-[#7b7f9e] text-xs">{ev.type}</span>
                    <span className="text-[#7b7f9e] text-xs ml-auto flex-shrink-0">
                      {new Date(ev._ts).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                    </span>
                  </div>
                  {ev.message && (
                    <p className="text-[#7b7f9e] text-xs mt-0.5 pl-3.5 truncate">{String(ev.message)}</p>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Legend */}
        <div className="border-t border-[#2e3149] px-4 py-3">
          <p className="text-[#7b7f9e] text-xs font-medium mb-2">Node Legend</p>
          <div className="grid grid-cols-2 gap-1">
            {Object.entries(NODE_COLORS).map(([node, color]) => (
              <div key={node} className="flex items-center gap-1.5 text-xs">
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                <span className="text-[#7b7f9e]">{node}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
