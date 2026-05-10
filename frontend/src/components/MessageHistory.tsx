import { formatTime } from "../lib/utils";
import { type RunMessage } from "../lib/api";

interface Props {
  messages: RunMessage[];
  loading?: boolean;
}

const NODE_COLORS: Record<string, string> = {
  router:       "#7b7f9e",
  ordering:     "#3b82f6",
  fraud:        "#f59e0b",
  payment:      "#22c55e",
  hitl:         "#6c63ff",
  notification: "#06b6d4",
  system:       "#7b7f9e",
};

const EVENT_ICONS: Record<string, string> = {
  node_start:        "▶",
  node_complete:     "✓",
  node_error:        "✕",
  hitl_pending:      "⏸",
  hitl_confirmed:    "✓",
  hitl_rejected:     "✕",
  hitl_expired:      "⏱",
  workflow_start:    "▶",
  workflow_complete: "✓",
  workflow_error:    "✕",
  tool_call:         "⚙",
};

function extractMessage(payload: Record<string, unknown>): string {
  if (typeof payload.message === "string") return payload.message;
  if (typeof payload.result === "string") return payload.result;
  if (payload.result && typeof payload.result === "object") {
    return JSON.stringify(payload.result).slice(0, 120);
  }
  if (payload.error) return `Error: ${payload.error}`;
  return "";
}

export default function MessageHistory({ messages, loading }: Props) {
  if (loading) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex gap-3 animate-pulse">
            <div className="w-6 h-6 rounded-full bg-[#252836] flex-shrink-0" />
            <div className="flex-1 space-y-1.5">
              <div className="h-3 bg-[#252836] rounded w-32" />
              <div className="h-2.5 bg-[#252836] rounded w-full" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="text-[#7b7f9e] text-sm text-center py-8">
        No execution events recorded.
      </div>
    );
  }

  return (
    <div className="relative">
      {/* Vertical line */}
      <div className="absolute left-[19px] top-0 bottom-0 w-px bg-[#2e3149]" />

      <div className="space-y-1">
        {messages.map((msg, idx) => {
          const color = NODE_COLORS[msg.node_name] ?? "#7b7f9e";
          const icon = EVENT_ICONS[msg.event_type] ?? "•";
          const detail = extractMessage(msg.payload);
          const isLast = idx === messages.length - 1;

          return (
            <div key={msg.id} className="flex gap-3 pl-1 pr-3 py-1.5 hover:bg-[#252836]/40 rounded-lg transition-colors">
              {/* Icon */}
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 z-10"
                style={{ backgroundColor: color + "20", border: `1px solid ${color}40`, color }}
              >
                {icon}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0 py-1">
                <div className="flex items-baseline gap-2">
                  <span className="text-xs font-semibold" style={{ color }}>
                    {msg.node_name}
                  </span>
                  <span className="text-[#7b7f9e] text-xs">{msg.event_type.replace(/_/g, " ")}</span>
                  <span className="text-[#7b7f9e] text-xs ml-auto flex-shrink-0">
                    {formatTime(msg.timestamp ?? msg.created_at ?? "")}
                  </span>
                </div>
                {detail && (
                  <p className="text-[#7b7f9e] text-xs mt-0.5 line-clamp-2 leading-relaxed">
                    {detail}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
