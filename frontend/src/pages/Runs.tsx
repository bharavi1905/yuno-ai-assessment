import { useState, useEffect, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { runsApi, type Run, type RunMessage } from "../lib/api";
import { relativeTime, truncateId, STATUS_COLORS } from "../lib/utils";
import MessageHistory from "../components/MessageHistory";
import TokenTracker from "../components/TokenTracker";
import { useToast } from "../components/Toast";

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

interface RunDetailProps {
  run: Run;
  onClose: () => void;
}

function RunDetail({ run, onClose }: RunDetailProps) {
  const [messages, setMessages] = useState<RunMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"events" | "tokens">("events");

  useEffect(() => {
    runsApi
      .messages(run.run_id)
      .then(setMessages)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [run.run_id]);

  const color = STATUS_COLORS[run.status] ?? "#7b7f9e";

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-5 py-4 border-b border-[#2e3149] flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-[#e8eaf0] text-sm">{run.run_id.slice(0, 16)}…</span>
            <StatusBadge status={run.status} />
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-[#7b7f9e]">
            <span>{run.workflow_type}</span>
            <span>·</span>
            <span>{relativeTime(run.started_at)}</span>
            <span>·</span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded hover:bg-[#252836] text-[#7b7f9e] hover:text-[#e8eaf0] flex-shrink-0"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        </button>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-3 px-5 py-3 border-b border-[#2e3149]">
        <div>
          <p className="text-[#7b7f9e] text-xs">Total Tokens</p>
          <p className="text-[#e8eaf0] text-sm font-semibold mt-0.5">
            {(run.total_input_tokens + run.total_output_tokens).toLocaleString()}
          </p>
        </div>
        <div>
          <p className="text-[#7b7f9e] text-xs">Input / Output</p>
          <p className="text-[#e8eaf0] text-sm font-semibold mt-0.5">
            {run.total_input_tokens.toLocaleString()} / {run.total_output_tokens.toLocaleString()}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[#2e3149] px-5">
        {(["events", "tokens"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-1 py-3 mr-5 text-sm border-b-2 transition-colors ${
              tab === t
                ? "border-[#6c63ff] text-[#e8eaf0]"
                : "border-transparent text-[#7b7f9e] hover:text-[#e8eaf0]"
            }`}
          >
            {t === "events" ? "Execution Events" : "Token Usage"}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-5">
        {tab === "events" ? (
          <MessageHistory messages={messages} loading={loading} />
        ) : (
          <TokenTracker
            tokenUsage={run.token_usage as Record<string, { input: number; output: number; cost_usd: number }>}
            totalCost={run.total_cost_usd}
          />
        )}
      </div>
    </div>
  );
}

export default function Runs() {
  const navigate = useNavigate();
  const { runId } = useParams<{ runId?: string }>();
  const toast = useToast();

  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [filterStatus, setFilterStatus] = useState("");
  const [filterType, setFilterType] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    runsApi
      .list({ limit: 100, status: filterStatus || undefined, workflow_type: filterType || undefined })
      .then(setRuns)
      .catch((e) => toast.error(e.message))
      .finally(() => setLoading(false));
  }, [toast, filterStatus, filterType]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (runId && runs.length > 0) {
      const run = runs.find((r) => r.run_id === runId);
      if (run) setSelectedRun(run);
    }
  }, [runId, runs]);

  const handleSelect = (run: Run) => {
    setSelectedRun(run);
    navigate(`/runs/${run.run_id}`, { replace: true });
  };

  const handleClose = () => {
    setSelectedRun(null);
    navigate("/runs", { replace: true });
  };

  return (
    <div className="flex h-full">
      {/* Table side */}
      <div className={`flex flex-col transition-all ${selectedRun ? "w-[480px] flex-shrink-0" : "flex-1"}`}>
        {/* Filter bar */}
        <div className="px-5 py-3 border-b border-[#2e3149] flex items-center gap-3">
          <h2 className="text-[#e8eaf0] font-medium mr-2">Workflow Runs</h2>
          <select
            className="bg-[#252836] border border-[#2e3149] rounded-lg px-3 py-1.5 text-xs text-[#e8eaf0] focus:outline-none focus:border-[#6c63ff]"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            <option value="">All types</option>
            <option value="food_ordering">food_ordering</option>
            <option value="complaint_resolution">complaint_resolution</option>
          </select>
          <select
            className="bg-[#252836] border border-[#2e3149] rounded-lg px-3 py-1.5 text-xs text-[#e8eaf0] focus:outline-none focus:border-[#6c63ff]"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="running">running</option>
            <option value="completed">completed</option>
            <option value="failed">failed</option>
            <option value="hitl_pending">hitl_pending</option>
            <option value="cancelled">cancelled</option>
          </select>
          <span className="ml-auto text-[#7b7f9e] text-xs">{runs.length} runs</span>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="p-4 space-y-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-10 bg-[#252836] rounded animate-pulse" />
              ))}
            </div>
          ) : runs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <p className="text-[#e8eaf0] font-medium mb-1">No runs yet</p>
              <p className="text-[#7b7f9e] text-sm">Trigger a workflow from the Workflows page to see runs here.</p>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-[#0f1117]">
                <tr className="border-b border-[#2e3149]">
                  {["Run ID", "Type", "Status", "Tokens", "Started"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-[#7b7f9e] font-medium text-xs uppercase tracking-wider">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => {
                  const isSelected = selectedRun?.id === r.id;
                  return (
                    <tr
                      key={r.id}
                      onClick={() => handleSelect(r)}
                      className={`border-b border-[#2e3149]/50 cursor-pointer transition-colors ${
                        isSelected ? "bg-[#1e1b4b]/40" : "hover:bg-[#252836]"
                      }`}
                    >
                      <td className="px-4 py-3 font-mono text-xs text-[#e8eaf0]">
                        {truncateId(r.run_id)}
                      </td>
                      <td className="px-4 py-3 text-[#7b7f9e] text-xs">{r.workflow_type}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={r.status} />
                      </td>
                      <td className="px-4 py-3 text-[#7b7f9e] text-xs font-mono">
                        {(r.total_input_tokens + r.total_output_tokens).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-[#7b7f9e] text-xs">{relativeTime(r.started_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Detail drawer */}
      {selectedRun && (
        <div className="flex-1 border-l border-[#2e3149] bg-[#0f1117] min-w-0">
          <RunDetail run={selectedRun} onClose={handleClose} />
        </div>
      )}
    </div>
  );
}
