export function relativeTime(iso: string): string {
  // Backend stores UTC without Z suffix — force UTC interpretation
  const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + "Z";
  const diff = Date.now() - new Date(normalized).getTime();
  if (diff < 60_000)     return "just now";
  if (diff < 3_600_000)  return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(normalized).toLocaleDateString();
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function truncateId(id: string, length = 8): string {
  return id.slice(0, length);
}

export function formatCost(usd: number): string {
  return `$${usd.toFixed(4)}`;
}

export const NODE_COLORS: Record<string, string> = {
  router:       "#6c63ff",
  ordering:     "#3b82f6",
  fraud:        "#f59e0b",
  payment:      "#22c55e",
  hitl:         "#ec4899",
  notification: "#06b6d4",
};

export const STATUS_COLORS: Record<string, string> = {
  running:      "#3b82f6",
  completed:    "#22c55e",
  failed:       "#ef4444",
  hitl_pending: "#ec4899",
  cancelled:    "#7b7f9e",
  archived:     "#7b7f9e",
  pending:      "#f59e0b",
};
