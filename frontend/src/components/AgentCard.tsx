import { type Agent } from "../lib/api";
import { relativeTime } from "../lib/utils";

const ROLE_COLORS: Record<string, string> = {
  ordering:     "text-[#3b82f6] bg-[#0a1628] border-[#3b82f6]/30",
  fraud:        "text-[#f59e0b] bg-[#1c1500] border-[#f59e0b]/30",
  payment:      "text-[#22c55e] bg-[#052e16] border-[#22c55e]/30",
  notification: "text-[#06b6d4] bg-[#001e26] border-[#06b6d4]/30",
  complaint:    "text-[#ec4899] bg-[#2d001a] border-[#ec4899]/30",
  custom:       "text-[#7b7f9e] bg-[#252836] border-[#2e3149]",
};

// Roles whose DB config (model, system_prompt, tools) is actually loaded at runtime.
// Nodes for other roles run with hardcoded defaults and ignore DB config edits.
const CONFIG_APPLIED_ROLES = new Set(["ordering", "complaint"]);

function workflowLabel(templateType: string): string {
  return templateType
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

interface Props {
  agent: Agent;
  usedInWorkflows: string[];   // workflow template_type values that reference this role
  onEdit: (agent: Agent) => void;
  onDelete: (agent: Agent) => void;
}

export default function AgentCard({ agent, usedInWorkflows, onEdit, onDelete }: Props) {
  const roleColor = ROLE_COLORS[agent.role] ?? ROLE_COLORS.custom;
  const visibleTools = agent.tools.slice(0, 3);
  const extraTools = agent.tools.length - 3;
  const configApplied = CONFIG_APPLIED_ROLES.has(agent.role);
  const isUsed = usedInWorkflows.length > 0;

  return (
    <div className="bg-[#1a1d27] border border-[#2e3149] rounded-xl p-5 flex flex-col gap-3 hover:border-[#3e4269] transition-colors">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-[#e8eaf0] font-semibold truncate">{agent.name}</h3>
          <p className="text-[#7b7f9e] text-xs mt-0.5">{agent.model}</p>
        </div>
        <span className={`px-2.5 py-1 rounded-full text-xs font-medium border flex-shrink-0 ${roleColor}`}>
          {agent.role}
        </span>
      </div>

      {/* Prompt preview */}
      <p className="text-[#7b7f9e] text-xs leading-relaxed line-clamp-2">
        {agent.system_prompt}
      </p>

      {/* Tools */}
      {agent.tools.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {visibleTools.map((t) => (
            <span
              key={t}
              className="px-2 py-0.5 rounded text-xs bg-[#252836] text-[#7b7f9e] border border-[#2e3149]"
            >
              {t}
            </span>
          ))}
          {extraTools > 0 && (
            <span className="px-2 py-0.5 rounded text-xs bg-[#252836] text-[#7b7f9e] border border-[#2e3149]">
              +{extraTools} more
            </span>
          )}
        </div>
      )}

      {/* Workflow usage */}
      <div className="flex flex-wrap gap-1.5 items-center">
        {isUsed ? (
          <>
            {usedInWorkflows.map((wf) => (
              <span
                key={wf}
                className="px-2 py-0.5 rounded text-xs bg-[#1e1b4b] text-[#a5b4fc] border border-[#6c63ff]/30 flex items-center gap-1"
              >
                <svg viewBox="0 0 12 12" fill="currentColor" className="w-2.5 h-2.5 flex-shrink-0">
                  <path d="M6 0a6 6 0 100 12A6 6 0 006 0zm1 8.5l-3-2V3h1v3l2.5 1.5L7 8.5z" />
                </svg>
                {workflowLabel(wf)}
              </span>
            ))}
            {configApplied ? (
              <span className="px-2 py-0.5 rounded text-xs bg-[#052e16] text-[#22c55e] border border-[#22c55e]/30 flex items-center gap-1">
                <svg viewBox="0 0 12 12" fill="currentColor" className="w-2.5 h-2.5 flex-shrink-0">
                  <path fillRule="evenodd" d="M10.293 3.293a1 1 0 010 1.414l-5 5a1 1 0 01-1.414 0l-2-2a1 1 0 011.414-1.414L4.586 7.586l4.293-4.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                Config applied
              </span>
            ) : (
              <span
                className="px-2 py-0.5 rounded text-xs bg-[#1c1500] text-[#9ca3af] border border-[#374151] flex items-center gap-1"
                title="This agent's role runs in the workflow, but its model/prompt config is not loaded from the database at runtime."
              >
                <svg viewBox="0 0 12 12" fill="currentColor" className="w-2.5 h-2.5 flex-shrink-0">
                  <path fillRule="evenodd" d="M6 1a5 5 0 100 10A5 5 0 006 1zm0 3a.75.75 0 01.75.75v2.5a.75.75 0 01-1.5 0v-2.5A.75.75 0 016 4zm0 5.5a.75.75 0 100-1.5.75.75 0 000 1.5z" clipRule="evenodd" />
                </svg>
                Fixed behavior
              </span>
            )}
          </>
        ) : (
          <span className="px-2 py-0.5 rounded text-xs bg-[#252836] text-[#6b7280] border border-[#374151]">
            Not used in any workflow
          </span>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-1 border-t border-[#2e3149]">
        <span className="text-[#7b7f9e] text-xs">{relativeTime(agent.created_at)}</span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onEdit(agent)}
            className="p-1.5 rounded hover:bg-[#252836] text-[#7b7f9e] hover:text-[#e8eaf0] transition-colors"
            title="Edit agent"
          >
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
              <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
            </svg>
          </button>
          <button
            onClick={() => onDelete(agent)}
            className="p-1.5 rounded hover:bg-[#2d0a0a] text-[#7b7f9e] hover:text-[#ef4444] transition-colors"
            title="Delete agent"
          >
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
              <path
                fillRule="evenodd"
                d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
