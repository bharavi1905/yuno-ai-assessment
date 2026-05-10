import { useState, useEffect, useCallback } from "react";
import { runsApi, workflowsApi, type HITLState } from "../lib/api";

interface HITLPanelProps {
  runId: string;
  onResolved: () => void;
}

function useCountdown(expiresAt?: string) {
  const [remaining, setRemaining] = useState<number | null>(null);

  useEffect(() => {
    if (!expiresAt) return;
    const update = () => {
      const diff = new Date(expiresAt).getTime() - Date.now();
      setRemaining(Math.max(0, Math.floor(diff / 1000)));
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [expiresAt]);

  if (remaining === null) return null;
  const m = Math.floor(remaining / 60);
  const s = remaining % 60;
  return remaining === 0 ? "Expired" : `${m}m ${String(s).padStart(2, "0")}s`;
}

function FraudBadge({ score, decision }: { score?: number; decision?: string }) {
  const s = score ?? 0;
  const blocked = decision === "block";
  const color = blocked ? "#ef4444" : s < 30 ? "#22c55e" : s < 70 ? "#f59e0b" : "#ef4444";
  const label = blocked ? "Blocked" : "Approved";
  const barWidth = Math.min(100, s);
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[#7b7f9e] text-xs">Fraud Risk Score</span>
        <span className="text-xs font-semibold" style={{ color }}>
          {s}/100 — {label}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-[#2e3149] overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${barWidth}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between py-1.5 border-b border-[#2e3149]/40 last:border-0">
      <span className="text-[#7b7f9e] text-xs w-32 flex-shrink-0">{label}</span>
      <span className="text-[#e8eaf0] text-xs font-medium text-right">{value}</span>
    </div>
  );
}

function parseOrderSummary(raw?: HITLState["order_summary"]) {
  if (!raw) return null;
  if (raw.restaurant_name) return raw;
  // Try to extract from raw_response markdown fences
  const text = raw.raw_response ?? "";
  try {
    const clean = text.replace(/```json\n?/g, "").replace(/```\n?/g, "").trim();
    const parsed = JSON.parse(clean);
    if (typeof parsed === "object" && parsed !== null) return parsed as typeof raw;
  } catch {}
  return null;
}

export default function HITLPanel({ runId, onResolved }: HITLPanelProps) {
  const [state, setState] = useState<HITLState | null>(null);
  const [loading, setLoading] = useState(true);
  const [deciding, setDeciding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showRePrompt, setShowRePrompt] = useState(false);
  const [rePromptText, setRePromptText] = useState("");
  const countdown = useCountdown(state?.hitl_expires_at);

  const load = useCallback(() => {
    setLoading(true);
    runsApi
      .hitlState(runId)
      .then(setState)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [runId]);

  useEffect(() => { load(); }, [load]);

  const decide = useCallback(
    async (approved: boolean, rawResponse?: string, reprompt?: boolean) => {
      setDeciding(true);
      try {
        const result = await workflowsApi.resume(runId, approved, rawResponse, reprompt);
        if (result.hitl_status === "pending") {
          // Agent looped back (e.g. "Other Options") and hit HITL again —
          // re-fetch the new checkpoint state and show the updated decision.
          setShowRePrompt(false);
          setRePromptText("");
          setDeciding(false);
          load();
        } else {
          onResolved();
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Decision failed");
        setDeciding(false);
      }
    },
    [runId, onResolved, load],
  );

  if (loading) {
    return (
      <div className="p-4 space-y-2 animate-pulse">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-8 rounded bg-[#252836]" />
        ))}
      </div>
    );
  }

  if (error || !state) {
    return (
      <div className="p-4 text-center">
        <p className="text-[#ef4444] text-sm">{error ?? "No HITL state found."}</p>
        <button onClick={load} className="mt-2 text-xs text-[#7b7f9e] underline">
          Retry
        </button>
      </div>
    );
  }

  const isOrder = state.hitl_action === "place_order";
  const isComplaint = state.hitl_action === "resolve_complaint";
  const isComplaintReorder = isOrder && state.workflow_type === "complaint_resolution";
  const resolution = state.resolution_result;
  const order = parseOrderSummary(state.order_summary);
  const noMatch = !order && (state.order_summary as Record<string, unknown> | undefined)?.no_match === true;
  const noMatchReason = (state.order_summary as Record<string, unknown> | undefined)?.reason as string | undefined;
  const payment = state.payment_result;
  const fraud = state.fraud_result;
  const isExpired = countdown === "Expired";

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#2e3149] flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-[#f59e0b] animate-pulse flex-shrink-0" />
        <span className="text-[#f59e0b] text-xs font-semibold uppercase tracking-wider">
          Awaiting Decision
        </span>
        <span className="text-[#e8eaf0] text-xs ml-1">
          — {isOrder ? "Order Confirmation" : "Complaint Resolution"}
        </span>
        {countdown !== null && (
          <span
            className="ml-auto text-xs font-mono flex-shrink-0"
            style={{ color: isExpired ? "#ef4444" : countdown.startsWith("0m") ? "#f59e0b" : "#7b7f9e" }}
          >
            ⏱ {countdown}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* No-match banner */}
        {isOrder && noMatch && (
          <div className="rounded-lg border border-[#f59e0b]/40 bg-[#f59e0b]/10 p-3 flex items-start gap-2">
            <span className="text-[#f59e0b] text-sm mt-0.5">⚠</span>
            <div>
              <p className="text-[#f59e0b] text-xs font-semibold mb-0.5">No matching restaurant found</p>
              <p className="text-[#7b7f9e] text-xs">{noMatchReason ?? "Try relaxing your constraints using Other Options below."}</p>
            </div>
          </div>
        )}

        {/* Food ordering: order + payment */}
        {isOrder && order && (
          <div className="rounded-lg border border-[#2e3149] bg-[#141621] p-3">
            <p className="text-[#6c63ff] text-xs font-semibold uppercase tracking-wider mb-2">Order Details</p>
            <Row label="Restaurant" value={<>{order.restaurant_name} {order.rating ? <span className="text-[#f59e0b]">★ {order.rating}</span> : null}</>} />
            <Row label="Item" value={order.item_name ?? "—"} />
            <Row label="Price" value={order.price != null ? `Rs ${order.price}` : "—"} />
            <Row label="Cuisine" value={order.cuisine ?? "—"} />
            <Row label="City" value={order.city ?? "—"} />
            <Row label="Delivery" value={order.delivery_time_mins != null ? `~${order.delivery_time_mins} min` : "—"} />
          </div>
        )}

        {isOrder && !order && !noMatch && state.order_summary?.raw_response && (
          <div className="rounded-lg border border-[#2e3149] bg-[#141621] p-3">
            <p className="text-[#6c63ff] text-xs font-semibold uppercase tracking-wider mb-2">Order Details</p>
            <p className="text-[#e8eaf0] text-xs whitespace-pre-wrap break-words">{state.order_summary.raw_response}</p>
          </div>
        )}

        {/* Fallback: order_summary missing entirely — agent search likely failed */}
        {isOrder && !order && !noMatch && !state.order_summary?.raw_response && !state.order_summary && (
          <div className="rounded-lg border border-[#2e3149] bg-[#141621] p-4 flex items-center gap-3">
            <span className="text-[#7b7f9e] text-lg">⏳</span>
            <div>
              <p className="text-[#e8eaf0] text-xs font-medium">Waiting for agent results</p>
              <p className="text-[#7b7f9e] text-xs mt-0.5">The ordering agent is still running. Try refreshing in a moment.</p>
            </div>
          </div>
        )}

        {/* Payment */}
        {payment && payment.gateway_name && (
          <div className="rounded-lg border border-[#2e3149] bg-[#141621] p-3">
            <p className="text-[#6c63ff] text-xs font-semibold uppercase tracking-wider mb-2">Payment</p>
            <Row label="Gateway" value={`${payment.gateway_name} · ${payment.method ?? ""}`} />
            {payment.success_rate != null && <Row label="Success Rate" value={`${payment.success_rate}%`} />}
            <Row label="Fee" value={payment.fee_amount != null ? `Rs ${payment.fee_amount}` : "—"} />
            <Row label="Total" value={payment.total_amount != null ? <span className="text-[#22c55e] font-bold">Rs {payment.total_amount}</span> : "—"} />
          </div>
        )}

        {/* Complaint resolution */}
        {isComplaint && resolution && (
          <div className="rounded-lg border border-[#2e3149] bg-[#141621] p-3">
            <p className="text-[#6c63ff] text-xs font-semibold uppercase tracking-wider mb-2">Resolution</p>
            <Row label="Type" value={
              resolution.resolution_type === "reorder"
                ? <span className="text-[#6c63ff]">Re-order</span>
                : <span className="text-[#f59e0b]">Compensate</span>
            } />
            {resolution.resolution_type === "reorder" && (
              <>
                <Row label="Item to order" value={resolution.original_item} />
                <Row label="Restaurant" value={resolution.restaurant_name} />
              </>
            )}
            {resolution.resolution_type === "compensate" && resolution.compensation_amount > 0 && (
              <Row label="Refund amount" value={<span className="text-[#22c55e] font-bold">Rs {resolution.compensation_amount}</span>} />
            )}
            <Row label="Reason" value={<span className="text-[#7b7f9e]">{resolution.reason}</span>} />
          </div>
        )}

        {/* Fraud score */}
        {fraud && (
          <div className="rounded-lg border border-[#2e3149] bg-[#141621] p-3">
            <p className="text-[#6c63ff] text-xs font-semibold uppercase tracking-wider mb-2">Risk Assessment</p>
            <FraudBadge score={fraud.fraud_score} decision={fraud.decision} />
            {fraud.triggered_rules && fraud.triggered_rules.length > 0 && (
              <p className="text-[#7b7f9e] text-xs mt-2">
                Rules: {fraud.triggered_rules.join(", ")}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Decision buttons */}
      <div className="border-t border-[#2e3149] px-4 py-3 space-y-2">
        {/* Re-prompt panel — food ordering: search with new constraints */}
        {isOrder && !isComplaintReorder && showRePrompt && (
          <div className="space-y-2 pb-1">
            <textarea
              rows={2}
              placeholder="Describe what you're looking for… e.g. paneer butter masala under Rs350, 4+ stars, Bangalore"
              value={rePromptText}
              onChange={(e) => setRePromptText(e.target.value)}
              className="w-full bg-[#252836] border border-[#2e3149] rounded-lg px-3 py-2 text-xs text-[#e8eaf0] placeholder-[#7b7f9e] focus:outline-none focus:border-[#6c63ff] resize-none"
            />
            <div className="flex gap-2">
              <button
                onClick={() => decide(false, rePromptText.trim() || "show_other_options")}
                disabled={deciding}
                className="flex-1 py-1.5 rounded-lg text-xs font-semibold transition-colors disabled:opacity-40"
                style={{ background: "#6c63ff20", color: "#6c63ff", border: "1px solid #6c63ff40" }}
              >
                {deciding ? "Searching…" : "↻ Search Again"}
              </button>
              <button
                onClick={() => setShowRePrompt(false)}
                disabled={deciding}
                className="px-3 py-1.5 rounded-lg text-xs text-[#7b7f9e] border border-[#2e3149] hover:bg-[#252836] transition-colors"
              >
                Back
              </button>
            </div>
          </div>
        )}

        {/* Re-prompt panel — complaint: change resolution request */}
        {isComplaint && showRePrompt && (
          <div className="space-y-2 pb-1">
            <textarea
              rows={2}
              placeholder="e.g. I'd prefer compensation instead, or reorder from a different restaurant"
              value={rePromptText}
              onChange={(e) => setRePromptText(e.target.value)}
              className="w-full bg-[#252836] border border-[#2e3149] rounded-lg px-3 py-2 text-xs text-[#e8eaf0] placeholder-[#7b7f9e] focus:outline-none focus:border-[#22c55e] resize-none"
            />
            <div className="flex gap-2">
              <button
                onClick={() => decide(false, rePromptText.trim() || "Change the resolution", true)}
                disabled={deciding || !rePromptText.trim()}
                className="flex-1 py-1.5 rounded-lg text-xs font-semibold transition-colors disabled:opacity-40"
                style={{ background: "#22c55e20", color: "#22c55e", border: "1px solid #22c55e40" }}
              >
                {deciding ? "Updating…" : "↻ Update Request"}
              </button>
              <button
                onClick={() => setShowRePrompt(false)}
                disabled={deciding}
                className="px-3 py-1.5 rounded-lg text-xs text-[#7b7f9e] border border-[#2e3149] hover:bg-[#252836] transition-colors"
              >
                Back
              </button>
            </div>
          </div>
        )}

        <div className="flex gap-2">
          <button
            onClick={() => decide(true, "YES")}
            disabled={deciding || isExpired}
            className="flex-1 py-2 rounded-lg text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ background: "#22c55e20", color: "#22c55e", border: "1px solid #22c55e40" }}
          >
            {deciding ? "Processing…" : isOrder ? "✓ Confirm Order" : isComplaint ? "✓ Approve Resolution" : "✓ Retry Payment"}
          </button>

          {/* Other Options — food ordering only (not complaint reorder) */}
          {isOrder && !isComplaintReorder && !showRePrompt && (
            <button
              onClick={() => { setShowRePrompt(true); setRePromptText(""); }}
              disabled={deciding || isExpired}
              className="flex-1 py-2 rounded-lg text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ background: "#6c63ff20", color: "#6c63ff", border: "1px solid #6c63ff40" }}
            >
              ↻ Other Options
            </button>
          )}

          {/* Change Request — complaint resolution only */}
          {isComplaint && !showRePrompt && (
            <button
              onClick={() => { setShowRePrompt(true); setRePromptText(""); }}
              disabled={deciding || isExpired}
              className="flex-1 py-2 rounded-lg text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ background: "#6c63ff20", color: "#6c63ff", border: "1px solid #6c63ff40" }}
            >
              ↻ Change Request
            </button>
          )}

          <button
            onClick={() => decide(false, "NO")}
            disabled={deciding}
            className="flex-1 py-2 rounded-lg text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ background: "#ef444420", color: "#ef4444", border: "1px solid #ef444440" }}
          >
            ✕ {isOrder ? "Cancel Order" : "Escalate to Support"}
          </button>
        </div>
      </div>
    </div>
  );
}
