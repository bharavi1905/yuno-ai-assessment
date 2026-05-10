import { useState, useEffect, useCallback } from "react";
import { agentsApi, workflowsApi, type Agent, type Workflow } from "../lib/api";
import AgentCard from "../components/AgentCard";
import AgentForm from "../components/AgentForm";
import { useToast } from "../components/Toast";

function Skeleton() {
  return (
    <div className="bg-[#1a1d27] border border-[#2e3149] rounded-xl p-5 space-y-3 animate-pulse">
      <div className="flex justify-between gap-2">
        <div className="h-4 bg-[#252836] rounded w-32" />
        <div className="h-5 bg-[#252836] rounded-full w-20" />
      </div>
      <div className="h-3 bg-[#252836] rounded w-full" />
      <div className="h-3 bg-[#252836] rounded w-3/4" />
      <div className="flex gap-1">
        <div className="h-5 bg-[#252836] rounded w-20" />
        <div className="h-5 bg-[#252836] rounded w-16" />
      </div>
    </div>
  );
}

export default function Agents() {
  const toast = useToast();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Agent | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Agent | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([agentsApi.list(), workflowsApi.list()])
      .then(([a, w]) => { setAgents(a); setWorkflows(w); })
      .catch((e) => toast.error(e.message))
      .finally(() => setLoading(false));
  }, [toast]);

  // For each agent, find which workflow template_types reference its role in config.nodes
  const workflowsForRole = useCallback(
    (role: string): string[] =>
      workflows
        .filter((w) => (w.config?.nodes ?? []).includes(role))
        .map((w) => w.template_type),
    [workflows],
  );

  useEffect(() => { load(); }, [load]);

  const handleEdit = (agent: Agent) => {
    setEditTarget(agent);
    setFormOpen(true);
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      await agentsApi.delete(confirmDelete.id);
      toast.success(`Deleted "${confirmDelete.name}"`);
      setConfirmDelete(null);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-[#e8eaf0] font-semibold text-lg">Agents</h2>
          <p className="text-[#7b7f9e] text-sm mt-0.5">
            {agents.length} agent{agents.length !== 1 ? "s" : ""} configured
          </p>
        </div>
        <button
          onClick={() => { setEditTarget(null); setFormOpen(true); }}
          className="flex items-center gap-2 px-4 py-2.5 bg-[#6c63ff] text-white text-sm font-medium rounded-lg hover:bg-[#574fd6] transition-colors"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
            <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
          </svg>
          New Agent
        </button>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} />)}
        </div>
      ) : agents.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-2xl bg-[#1a1d27] border border-[#2e3149] flex items-center justify-center mb-4">
            <svg viewBox="0 0 20 20" fill="#7b7f9e" className="w-8 h-8">
              <path d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" />
            </svg>
          </div>
          <p className="text-[#e8eaf0] font-medium mb-1">No agents yet</p>
          <p className="text-[#7b7f9e] text-sm mb-6">Create your first agent to get started</p>
          <button
            onClick={() => { setEditTarget(null); setFormOpen(true); }}
            className="px-4 py-2.5 bg-[#6c63ff] text-white text-sm font-medium rounded-lg hover:bg-[#574fd6] transition-colors"
          >
            Create your first agent
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {agents.map((a) => (
            <AgentCard
              key={a.id}
              agent={a}
              usedInWorkflows={workflowsForRole(a.role)}
              onEdit={handleEdit}
              onDelete={setConfirmDelete}
            />
          ))}
        </div>
      )}

      {/* Form slide-over */}
      <AgentForm
        open={formOpen}
        agent={editTarget}
        onClose={() => { setFormOpen(false); setEditTarget(null); }}
        onSaved={load}
      />

      {/* Delete confirm dialog */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-[#1a1d27] border border-[#2e3149] rounded-xl p-6 w-[400px] shadow-2xl">
            <h3 className="text-[#e8eaf0] font-semibold mb-2">Delete Agent</h3>
            <p className="text-[#7b7f9e] text-sm mb-6">
              Delete <span className="text-[#e8eaf0] font-medium">"{confirmDelete.name}"</span>?
              This cannot be undone.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setConfirmDelete(null)}
                className="flex-1 px-4 py-2.5 border border-[#2e3149] rounded-lg text-[#7b7f9e] text-sm hover:bg-[#252836] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="flex-1 px-4 py-2.5 bg-[#ef4444] text-white text-sm font-medium rounded-lg hover:bg-red-600 disabled:opacity-50 transition-colors"
              >
                {deleting ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
