import { useState, useEffect, useCallback } from "react";
import { workflowsApi, agentsApi, type Workflow, type Agent } from "../lib/api";
import WorkflowCanvas from "../components/WorkflowCanvas";
import HITLPanel from "../components/HITLPanel";
import { useToast } from "../components/Toast";
import { createLogStream, type LogEvent } from "../lib/websocket";
import { STATUS_COLORS } from "../lib/utils";

const TEMPLATE_META: Record<string, { color: string; icon: string; description: string }> = {
  food_ordering: {
    color: "#6c63ff",
    icon: "🍽️",
    description: "Smart food ordering with fraud check, payment routing, and HITL confirmation via Telegram.",
  },
  complaint_resolution: {
    color: "#22c55e",
    icon: "🎧",
    description: "Customer complaint workflow: AI looks up order, decides re-order or refund, routes to HITL approval.",
  },
};

interface TriggerModalProps {
  workflow: Workflow;
  agents: Agent[];
  onClose: () => void;
  onTriggered: (runId: string) => void;
}

type ModalPhase = "form" | "running" | "hitl_pending" | "done";

function TriggerModal({ workflow, agents, onClose, onTriggered }: TriggerModalProps) {
  const toast = useToast();
  const [phase, setPhase] = useState<ModalPhase>("form");
  const [pendingRunId, setPendingRunId] = useState<string | null>(null);
  const [form, setForm] = useState({
    user_message: workflow.template_type === "complaint_resolution"
      ? "I received the wrong order — I got veg biryani but I ordered chicken biryani"
      : "Order chicken biryani under Rs300, 4+ stars, Hyderabad",
    telegram_chat_id: "",
    user_id: "user_001",
  });

  const handleTrigger = async () => {
    setPhase("running");
    try {
      const run = await workflowsApi.trigger(workflow.id, form, workflow.template_type);
      onTriggered(run.run_id);
      if (run.hitl_status === "pending") {
        setPendingRunId(run.run_id);
        setPhase("hitl_pending");
      } else {
        toast.success(`Workflow completed — run ${run.run_id.slice(0, 8)}`);
        setPhase("done");
        setTimeout(onClose, 1500);
      }
    } catch (e) {
      toast.error((e as Error).message);
      setPhase("form");
    }
  };

  const meta = TEMPLATE_META[workflow.template_type] ?? TEMPLATE_META.food_ordering;
  const isHitl = phase === "hitl_pending";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div
        className="bg-[#1a1d27] border border-[#2e3149] rounded-xl shadow-2xl overflow-hidden"
        style={{ width: isHitl ? 560 : 480 }}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-6 pt-6 pb-4">
          <span className="text-2xl">{meta.icon}</span>
          <div>
            <h3 className="text-[#e8eaf0] font-semibold">{workflow.name}</h3>
            <p className="text-[#7b7f9e] text-xs mt-0.5">{meta.description}</p>
          </div>
          {isHitl && (
            <button onClick={onClose} className="ml-auto p-1 rounded text-[#7b7f9e] hover:text-[#e8eaf0] hover:bg-[#252836]">
              ✕
            </button>
          )}
        </div>

        {/* Body */}
        {phase === "done" ? (
          <div className="flex flex-col items-center gap-3 py-10 px-6 pb-8">
            <span className="text-4xl">✅</span>
            <p className="text-[#e8eaf0] font-medium">Workflow completed</p>
          </div>
        ) : isHitl && pendingRunId ? (
          <div style={{ height: 460 }} className="border-t border-[#2e3149]">
            <HITLPanel
              runId={pendingRunId}
              onResolved={() => { setPhase("done"); setTimeout(onClose, 1800); }}
            />
          </div>
        ) : (
          <div className="px-6 pb-6 space-y-4">
            <div>
              <label className="block text-[#7b7f9e] text-xs font-medium mb-1.5">User Message / Trigger Input</label>
              <textarea
                rows={3}
                className="w-full bg-[#252836] border border-[#2e3149] rounded-lg px-3 py-2.5 text-sm text-[#e8eaf0] placeholder-[#7b7f9e] focus:outline-none focus:border-[#6c63ff] resize-none"
                value={form.user_message}
                onChange={(e) => setForm((f) => ({ ...f, user_message: e.target.value }))}
              />
            </div>

            <div>
              <label className="block text-[#7b7f9e] text-xs font-medium mb-1.5">
                Telegram Chat ID{" "}
                <span className="font-normal">(optional — for HITL via Telegram)</span>
              </label>
              <input
                className="w-full bg-[#252836] border border-[#2e3149] rounded-lg px-3 py-2.5 text-sm text-[#e8eaf0] placeholder-[#7b7f9e] focus:outline-none focus:border-[#6c63ff]"
                placeholder="e.g. 123456789"
                value={form.telegram_chat_id}
                onChange={(e) => setForm((f) => ({ ...f, telegram_chat_id: e.target.value }))}
              />
            </div>

            {agents.length > 0 && (
              <div>
                <p className="text-[#7b7f9e] text-xs font-medium mb-2">Configured Agents</p>
                <div className="flex flex-wrap gap-1.5">
                  {agents.slice(0, 6).map((a) => (
                    <span
                      key={a.id}
                      className="px-2 py-0.5 rounded text-xs bg-[#252836] border border-[#2e3149] text-[#7b7f9e]"
                    >
                      {a.name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <button
                onClick={onClose}
                className="flex-1 px-4 py-2.5 rounded-lg border border-[#2e3149] text-[#7b7f9e] text-sm hover:bg-[#252836] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleTrigger}
                disabled={phase === "running" || !form.user_message.trim()}
                className="flex-1 px-4 py-2.5 rounded-lg text-white text-sm font-medium disabled:opacity-50 transition-colors"
                style={{ backgroundColor: meta.color }}
              >
                {phase === "running" ? "Running agents…" : "Run Workflow"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Workflows() {
  const toast = useToast();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Workflow | null>(null);
  const [triggerModal, setTriggerModal] = useState<Workflow | null>(null);
  const [nodeStatuses, setNodeStatuses] = useState<Record<string, "idle" | "active" | "completed" | "error">>({});
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [liveEvents, setLiveEvents] = useState<(LogEvent & { _ts: number })[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [wf, ag] = await Promise.all([workflowsApi.list(), agentsApi.list()]);
      setWorkflows(wf);
      setAgents(ag);
      if (wf.length > 0 && !selected) setSelected(wf[0]);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [toast, selected]);

  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!activeRunId) return;
    setLiveEvents([]);
    setNodeStatuses({});

    const stop = createLogStream(activeRunId, (ev) => {
      setLiveEvents((prev) => [...prev, { ...ev, _ts: Date.now() }].slice(-50));

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
  }, [activeRunId]);

  const handleTriggered = (runId: string) => {
    setActiveRunId(runId);
  };

  const selectedMeta = selected ? TEMPLATE_META[selected.template_type] ?? TEMPLATE_META.food_ordering : null;

  return (
    <div className="flex h-full">
      {/* Left panel — template list */}
      <div className="w-[360px] flex-shrink-0 border-r border-[#2e3149] flex flex-col">
        <div className="px-5 py-4 border-b border-[#2e3149]">
          <h2 className="text-[#e8eaf0] font-medium">Workflow Templates</h2>
          <p className="text-[#7b7f9e] text-xs mt-0.5">{workflows.length} templates available</p>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {loading ? (
            Array.from({ length: 2 }).map((_, i) => (
              <div key={i} className="h-28 bg-[#1a1d27] rounded-xl border border-[#2e3149] animate-pulse" />
            ))
          ) : workflows.length === 0 ? (
            <p className="text-[#7b7f9e] text-sm text-center py-8">No templates found.</p>
          ) : (
            workflows.map((wf) => {
              const meta = TEMPLATE_META[wf.template_type] ?? TEMPLATE_META.food_ordering;
              const isSelected = selected?.id === wf.id;
              return (
                <div
                  key={wf.id}
                  onClick={() => setSelected(wf)}
                  className={`p-4 rounded-xl border cursor-pointer transition-all ${
                    isSelected
                      ? "border-[#6c63ff] bg-[#1e1b4b]/30"
                      : "border-[#2e3149] bg-[#1a1d27] hover:border-[#3e4269]"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xl">{meta.icon}</span>
                      <div>
                        <h3 className="text-[#e8eaf0] font-medium text-sm">{wf.name}</h3>
                        <span className="text-[#7b7f9e] text-xs">{wf.template_type}</span>
                      </div>
                    </div>
                    <span
                      className="px-2 py-0.5 rounded-full text-xs font-medium border flex-shrink-0"
                      style={{
                        color: STATUS_COLORS[wf.is_active ? "completed" : "failed"] ?? "#7b7f9e",
                        background: (STATUS_COLORS[wf.is_active ? "completed" : "failed"] ?? "#7b7f9e") + "20",
                        borderColor: (STATUS_COLORS[wf.is_active ? "completed" : "failed"] ?? "#7b7f9e") + "40",
                      }}
                    >
                      {wf.is_active ? "active" : "inactive"}
                    </span>
                  </div>
                  <p className="text-[#7b7f9e] text-xs mt-2 line-clamp-2">{meta.description}</p>
                  <button
                    onClick={(e) => { e.stopPropagation(); setTriggerModal(wf); }}
                    className="mt-3 w-full px-3 py-2 rounded-lg text-xs font-medium text-white transition-colors"
                    style={{ backgroundColor: meta.color + "cc" }}
                  >
                    Trigger Workflow
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* Live run log */}
        {activeRunId && (
          <div className="border-t border-[#2e3149] flex flex-col" style={{ maxHeight: "220px" }}>
            <div className="px-4 py-2 border-b border-[#2e3149] flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e] animate-pulse" />
              <span className="text-[#7b7f9e] text-xs">Run: {activeRunId.slice(0, 8)}…</span>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-1">
              {liveEvents.length === 0 ? (
                <p className="text-[#7b7f9e] text-xs text-center py-4">Waiting for events…</p>
              ) : (
                liveEvents.map((ev, i) => (
                  <div key={i} className="flex items-start gap-1.5 text-xs">
                    <span className="text-[#7b7f9e] flex-shrink-0">{new Date(ev._ts).toLocaleTimeString("en-US", { hour12: false })}</span>
                    <span className="text-[#6c63ff] font-medium flex-shrink-0">{ev.node ?? "sys"}</span>
                    <span className="text-[#7b7f9e] truncate">{ev.message ?? ev.type}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {/* Right panel — canvas */}
      <div className="flex-1 flex flex-col min-w-0">
        {selected && selectedMeta ? (
          <>
            <div className="px-5 py-4 border-b border-[#2e3149] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-xl">{selectedMeta.icon}</span>
                <div>
                  <h2 className="text-[#e8eaf0] font-medium">{selected.name}</h2>
                  <p className="text-[#7b7f9e] text-xs mt-0.5">{selected.template_type} topology</p>
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs text-[#7b7f9e]">
                {Object.entries(nodeStatuses).some(([, v]) => v === "active") && (
                  <span className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#6c63ff] animate-pulse" />
                    Executing
                  </span>
                )}
                <div className="flex items-center gap-3 ml-4">
                  {(["idle", "active", "completed", "error"] as const).map((s) => (
                    <span key={s} className="flex items-center gap-1">
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{ backgroundColor: { idle: "#2e3149", active: "#6c63ff", completed: "#22c55e", error: "#ef4444" }[s] }}
                      />
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            </div>
            <div className="flex-1">
              <WorkflowCanvas
                key={selected.template_type}
                workflowType={selected.template_type as "food_ordering" | "complaint_resolution"}
                nodeStatuses={nodeStatuses}
              />
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center text-[#7b7f9e] text-sm">
            Select a workflow template to view its topology
          </div>
        )}
      </div>

      {triggerModal && (
        <TriggerModal
          workflow={triggerModal}
          agents={agents}
          onClose={() => setTriggerModal(null)}
          onTriggered={handleTriggered}
        />
      )}
    </div>
  );
}
