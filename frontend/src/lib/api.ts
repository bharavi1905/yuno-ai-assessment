// Inside Docker with Vite dev server: use relative paths (Vite proxy handles /api → backend:8000)
// Outside Docker or in production builds: use explicit URL from env var
const BASE =
  typeof window !== "undefined" && window.location.port === "3000"
    ? ""
    : (import.meta.env.VITE_API_URL ?? "http://localhost:8000");

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Agent {
  id: string;
  name: string;
  role: string;
  system_prompt: string;
  model: string;
  tools: string[];
  channels: string[];
  schedule: string | null;
  memory_enabled: boolean;
  memory_window: number;
  skills: string[];
  interaction_rules: string | null;
  guardrails: object | null;
  created_at: string;
  updated_at: string | null;
}

export interface AgentCreate {
  name: string;
  role: string;
  system_prompt: string;
  model: string;
  tools: string[];
  channels: string[];
  schedule?: string;
  memory_enabled?: boolean;
  memory_window?: number;
  skills?: string[];
  interaction_rules?: string;
  guardrails?: object;
}

export interface Workflow {
  id: string;
  name: string;
  description: string;
  template_type: string;
  config: { nodes?: string[]; entry?: string };
  is_active: boolean;
  created_at: string;
}

export interface Run {
  id: string;
  run_id: string;
  workflow_type: string;
  status: string;
  triggered_by: string;
  telegram_chat_id: string | null;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  token_usage?: Record<string, { input: number; output: number; cost_usd: number }>;
  started_at: string;
  completed_at: string | null;
  error: string | null;
}

export interface RunMessage {
  id: string;
  run_id: string;
  node_name: string;
  event_type: string;
  payload: Record<string, unknown>;
  timestamp: string;
  created_at: string;  // alias exposed by some response shapes
}

export interface HITLState {
  hitl_action: "place_order" | "resolve_complaint";
  workflow_type: string;
  order_summary?: {
    restaurant_name?: string;
    item_name?: string;
    price?: number;
    rating?: number;
    delivery_time_mins?: number;
    cuisine?: string;
    city?: string;
    raw_response?: string;
  };
  fraud_result?: {
    decision?: string;
    fraud_score?: number;
    triggered_rules?: string[];
    reasoning?: string;
  };
  payment_result?: {
    gateway_name?: string;
    method?: string;
    success_rate?: number;
    fee_amount?: number;
    total_amount?: number;
    base_amount?: number;
  };
  resolution_result?: {
    resolution_type: "reorder" | "compensate";
    reason: string;
    compensation_amount: number;
    original_item: string;
    restaurant_name: string;
    order_id: string;
  };
  hitl_expires_at?: string;
}

export interface TriggerWorkflowRequest {
  workflow_type: string;
  telegram_chat_id: string;
  user_message: string;
  amount?: number;
  failed_gateway?: string;
  order_id?: string;
}

export interface TriggerWorkflowResponse {
  run_id: string;
  workflow_type: string;
  status: string;
  hitl_status: string;
  message: string;
}

// ── API clients ───────────────────────────────────────────────────────────────

export const agentsApi = {
  list: (params?: { role?: string; limit?: number; offset?: number }) => {
    const qs = params ? `?${new URLSearchParams(Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]))}` : "";
    return request<Agent[]>(`/api/agents${qs}`);
  },
  get:    (id: string) => request<Agent>(`/api/agents/${id}`),
  create: (body: AgentCreate) =>
    request<Agent>("/api/agents", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: Partial<AgentCreate>) =>
    request<Agent>(`/api/agents/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  delete: (id: string) => request<void>(`/api/agents/${id}`, { method: "DELETE" }),
};

export const workflowsApi = {
  list:    () => request<Workflow[]>("/api/workflows"),
  get:     (id: string) => request<Workflow>(`/api/workflows/${id}`),
  trigger: (_id: string, form: { user_message: string; telegram_chat_id: string; user_id?: string }, workflowType: string) =>
    request<TriggerWorkflowResponse>("/api/workflows/trigger", {
      method: "POST",
      body: JSON.stringify({
        workflow_type: workflowType,
        telegram_chat_id: form.telegram_chat_id || "",
        user_message: form.user_message,
      } satisfies TriggerWorkflowRequest),
    }),
  resume: (runId: string, approved: boolean, rawResponse?: string, reprompt?: boolean) =>
    request<TriggerWorkflowResponse>(`/api/workflows/${runId}/resume`, {
      method: "POST",
      body: JSON.stringify({
        approved,
        raw_response: rawResponse ?? (approved ? "YES" : "NO"),
        reprompt: reprompt ?? false,
      }),
    }),
};

export const runsApi = {
  list: (params?: { workflow_type?: string; status?: string; limit?: number }) => {
    const qs = params ? `?${new URLSearchParams(Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]))}` : "";
    return request<Run[]>(`/api/runs${qs}`);
  },
  get:       (runId: string) => request<Run>(`/api/runs/${runId}`),
  messages:  (runId: string) => request<RunMessage[]>(`/api/runs/${runId}/messages`),
  hitlState: (runId: string) => request<HITLState>(`/api/runs/${runId}/hitl`),
};

export const messagesApi = {
  list: (runId: string) => request<RunMessage[]>(`/api/messages?run_id=${runId}`),
};
