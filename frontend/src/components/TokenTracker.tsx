import { formatCost } from "../lib/utils";

interface TokenEntry {
  input: number;
  output: number;
  cost_usd: number;
}

interface Props {
  tokenUsage: Record<string, TokenEntry> | null | undefined;
  totalCost?: number;
}

const AGENT_COLORS: Record<string, string> = {
  router:       "#7b7f9e",
  ordering:     "#3b82f6",
  fraud:        "#f59e0b",
  payment:      "#22c55e",
  hitl:         "#6c63ff",
  notification: "#06b6d4",
};

export default function TokenTracker({ tokenUsage, totalCost }: Props) {
  if (!tokenUsage || Object.keys(tokenUsage).length === 0) {
    return (
      <div className="text-[#7b7f9e] text-sm text-center py-6">
        No token data available.
      </div>
    );
  }

  const entries = Object.entries(tokenUsage);
  const grandTotal = entries.reduce((s, [, v]) => s + (v.cost_usd ?? 0), 0);

  return (
    <div className="space-y-3">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[#2e3149]">
            {["Agent", "Input", "Output", "Total Tokens", "Cost"].map((h) => (
              <th
                key={h}
                className="text-left px-3 py-2 text-[#7b7f9e] text-xs font-medium uppercase tracking-wider"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {entries.map(([agent, usage]) => {
            const color = AGENT_COLORS[agent] ?? "#7b7f9e";
            const total = (usage.input ?? 0) + (usage.output ?? 0);
            return (
              <tr key={agent} className="border-b border-[#2e3149]/40">
                <td className="px-3 py-2.5">
                  <span className="font-medium text-xs" style={{ color }}>
                    {agent}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-[#7b7f9e] text-xs font-mono">
                  {(usage.input ?? 0).toLocaleString()}
                </td>
                <td className="px-3 py-2.5 text-[#7b7f9e] text-xs font-mono">
                  {(usage.output ?? 0).toLocaleString()}
                </td>
                <td className="px-3 py-2.5 text-xs font-mono">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 bg-[#252836] rounded-full h-1.5 max-w-[80px]">
                      <div
                        className="h-1.5 rounded-full"
                        style={{
                          width: `${Math.min(100, (total / 4000) * 100)}%`,
                          backgroundColor: color,
                        }}
                      />
                    </div>
                    <span className="text-[#7b7f9e]">{total.toLocaleString()}</span>
                  </div>
                </td>
                <td className="px-3 py-2.5 text-[#e8eaf0] text-xs font-mono">
                  {formatCost(usage.cost_usd ?? 0)}
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={4} className="px-3 py-2.5 text-[#7b7f9e] text-xs font-medium text-right">
              Total Cost
            </td>
            <td className="px-3 py-2.5 text-[#6c63ff] text-sm font-bold font-mono">
              {formatCost(totalCost ?? grandTotal)}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
