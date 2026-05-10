import { useEffect, useState, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { agentsApi, runsApi, type Agent, type Run } from "../lib/api";
import { createMonitorStream, type LogEvent } from "../lib/websocket";
import { relativeTime, truncateId, STATUS_COLORS, NODE_COLORS } from "../lib/utils";

interface StatCardProps {
  label: string;
  value: string | number;
  sub?: string;
  accent: string;   // tailwind bg class for the top accent bar
  valueColor: string;
}

function StatCard({ label, value, sub, accent, valueColor }: StatCardProps) {
  return (
    <div className="bg-[#1a1d27] border border-[#2e3149] rounded-xl overflow-hidden">
      <div className={`h-1 ${accent}`} />
      <div className="p-5">
        <p className="text-[#9ca3bb] text-sm mb-1">{label}</p>
        <p className={`text-3xl font-bold ${valueColor}`}>{value}</p>
        {sub && <p className="text-[#6b7280] text-xs mt-1">{sub}</p>}
      </div>
    </div>
  );
}

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

function Skeleton({ className }: { className: string }) {
  return <div className={`bg-[#252836] animate-pulse rounded ${className}`} />;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [events, setEvents] = useState<(LogEvent & { _ts: number })[]>([]);
  const feedRef = useRef<HTMLDivElement>(null);
  const knownRunIds = useRef<Set<string>>(new Set());

  const fetchRuns = useCallback(() => {
    runsApi.list({ limit: 50 }).then((r) => {
      setRuns(r);
      knownRunIds.current = new Set(r.map((x) => x.run_id));
    }).catch(console.error);
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([agentsApi.list({ limit: 100 }), runsApi.list({ limit: 50 })])
      .then(([a, r]) => {
        setAgents(a);
        setRuns(r);
        knownRunIds.current = new Set(r.map((x) => x.run_id));
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const stop = createMonitorStream((ev) => {
      setEvents((prev) => [...prev, { ...ev, _ts: Date.now() }].slice(-20));

      // Refresh runs when a new run_id appears (workflow started) or notification
      // node completes (workflow finished — status needs updating in the table).
      const isNewRun = ev.run_id && !knownRunIds.current.has(ev.run_id);
      const isRunEnd = ev.node === "notification" && ev.type === "node_complete";
      if (isNewRun || isRunEnd) {
        fetchRuns();
      }
    });
    return stop;
  }, [fetchRuns]);

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [events]);

  const completedRuns = runs.filter((r) => r.status === "completed").length;
  const successRate = runs.length ? Math.round((completedRuns / runs.length) * 100) : 0;
  const recentRuns = runs.slice(0, 10);

  return (
    <div className="p-6 space-y-6 max-w-7xl">
      {/* Stat cards — 3 columns, no cost */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {loading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))
        ) : (
          <>
            <StatCard
              label="Total Agents"
              value={agents.length}
              sub="configured"
              accent="bg-[#6c63ff]"
              valueColor="text-[#a5b4fc]"
            />
            <StatCard
              label="Total Runs"
              value={runs.length}
              sub="all time"
              accent="bg-[#3b82f6]"
              valueColor="text-[#93c5fd]"
            />
            <StatCard
              label="Completed Runs"
              value={completedRuns}
              sub={`${successRate}% success rate`}
              accent="bg-[#22c55e]"
              valueColor="text-[#86efac]"
            />
          </>
        )}
      </div>

      {/* Recent runs + activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent runs */}
        <div className="bg-[#1a1d27] border border-[#2e3149] rounded-xl overflow-hidden">
          <div className="px-5 py-4 border-b border-[#2e3149] flex items-center justify-between">
            <h2 className="text-white font-semibold">Recent Runs</h2>
            <button
              onClick={() => navigate("/runs")}
              className="text-[#6c63ff] text-xs hover:underline"
            >
              View all
            </button>
          </div>
          {loading ? (
            <div className="p-4 space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-10 rounded" />
              ))}
            </div>
          ) : recentRuns.length === 0 ? (
            <div className="p-8 text-center text-[#7b7f9e] text-sm">
              No workflow runs yet.{" "}
              <button
                onClick={() => navigate("/workflows")}
                className="text-[#6c63ff] hover:underline"
              >
                Trigger a workflow
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#2e3149]">
                    {["Run ID", "Type", "Status", "Started"].map((h) => (
                      <th key={h} className="text-left px-4 py-2.5 text-[#6b7280] font-medium text-xs uppercase tracking-wider">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {recentRuns.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => navigate(`/runs/${r.run_id}`)}
                      className="border-b border-[#2e3149]/40 hover:bg-[#252836] cursor-pointer transition-colors group"
                    >
                      <td className="px-4 py-3 font-mono text-xs text-[#c4c8e0] group-hover:text-white transition-colors">
                        {truncateId(r.run_id)}
                      </td>
                      <td className="px-4 py-3 text-[#9ca3bb] text-xs">{r.workflow_type}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={r.status} />
                      </td>
                      <td className="px-4 py-3 text-[#9ca3bb] text-xs">{relativeTime(r.started_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Activity feed */}
        <div className="bg-[#1a1d27] border border-[#2e3149] rounded-xl overflow-hidden flex flex-col">
          <div className="px-5 py-4 border-b border-[#2e3149] flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#22c55e] animate-pulse" />
            <h2 className="text-white font-semibold">Live Activity</h2>
          </div>
          <div
            ref={feedRef}
            className="flex-1 overflow-y-auto p-4 space-y-1.5 min-h-[200px] max-h-[400px]"
          >
            {events.length === 0 ? (
              <p className="text-[#6b7280] text-sm text-center mt-8">
                Waiting for activity...
              </p>
            ) : (
              events.map((ev, i) => {
                const color = ev.node ? (NODE_COLORS[ev.node] ?? "#7b7f9e") : "#7b7f9e";
                return (
                  <div key={i} className="flex items-start gap-2 text-xs px-2 py-1.5 rounded hover:bg-[#252836] transition-colors">
                    <span
                      className="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0"
                      style={{ backgroundColor: color }}
                    />
                    <div className="flex-1 min-w-0">
                      <span className="font-semibold" style={{ color }}>
                        {ev.node ?? "system"}
                      </span>
                      {" "}
                      <span className="text-[#6b7280]">{ev.type}</span>
                      {ev.message && (
                        <p className="text-[#9ca3bb] truncate mt-0.5">{String(ev.message)}</p>
                      )}
                    </div>
                    <span className="text-[#4b5280] flex-shrink-0 tabular-nums">
                      {new Date(ev._ts).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
