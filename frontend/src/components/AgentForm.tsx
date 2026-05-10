import { useState, useEffect } from "react";
import { agentsApi, type Agent, type AgentCreate } from "../lib/api";
import { useToast } from "./Toast";

const AVAILABLE_TOOLS = [
  "restaurant_search",
  "menu_retrieval",
  "payment_routing",
  "fraud_scoring",
  "telegram_notify",
];

const ROLES = ["ordering", "fraud", "payment", "notification", "complaint", "custom"];
const MODELS = ["gpt-4o-mini", "gpt-4o"];

interface Props {
  open: boolean;
  agent?: Agent | null;
  onClose: () => void;
  onSaved: () => void;
}

export default function AgentForm({ open, agent, onClose, onSaved }: Props) {
  const toast = useToast();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const blank: AgentCreate = {
    name: "", role: "ordering", system_prompt: "", model: "gpt-4o-mini",
    tools: [], channels: [], memory_enabled: false, memory_window: 10, skills: [],
  };
  const [form, setForm] = useState<AgentCreate>(blank);

  useEffect(() => {
    if (open) {
      setError(null);
      setShowAdvanced(false);
      setForm(
        agent
          ? {
              name: agent.name, role: agent.role, system_prompt: agent.system_prompt,
              model: agent.model, tools: agent.tools, channels: agent.channels,
              schedule: agent.schedule ?? undefined,
              memory_enabled: agent.memory_enabled, memory_window: agent.memory_window,
              skills: agent.skills, interaction_rules: agent.interaction_rules ?? undefined,
            }
          : blank
      );
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, agent]);

  const set = <K extends keyof AgentCreate>(k: K, v: AgentCreate[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  const toggleTool = (tool: string) =>
    set("tools", form.tools.includes(tool) ? form.tools.filter((t) => t !== tool) : [...form.tools, tool]);

  const toggleChannel = (ch: string) =>
    set("channels", form.channels.includes(ch) ? form.channels.filter((c) => c !== ch) : [...form.channels, ch]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() || !form.role || !form.system_prompt.trim()) {
      setError("Name, role, and system prompt are required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (agent) {
        await agentsApi.update(agent.id, form);
        toast.success("Agent updated.");
      } else {
        await agentsApi.create(form);
        toast.success("Agent created.");
      }
      onSaved();
      onClose();
    } catch (err) {
      const msg = (err as Error).message;
      if (msg.includes("already exists")) {
        setError("An agent with this name already exists.");
      } else {
        setError(msg);
      }
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex">
      {/* Overlay */}
      <div
        className="flex-1 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="w-[480px] flex-shrink-0 bg-[#1a1d27] border-l border-[#2e3149] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-[#2e3149]">
          <h2 className="text-[#e8eaf0] font-semibold">
            {agent ? "Edit Agent" : "New Agent"}
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:bg-[#252836] text-[#7b7f9e] hover:text-[#e8eaf0]"
          >
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {error && (
            <div className="bg-[#2d0a0a] border border-[#ef4444]/30 rounded-lg px-4 py-3 text-sm text-[#ef4444]">
              {error}
            </div>
          )}

          {/* Name */}
          <div>
            <label className="block text-[#7b7f9e] text-xs font-medium mb-1.5">
              Name <span className="text-[#ef4444]">*</span>
            </label>
            <input
              className="w-full bg-[#252836] border border-[#2e3149] rounded-lg px-3 py-2.5 text-sm text-[#e8eaf0] placeholder-[#7b7f9e] focus:outline-none focus:border-[#6c63ff]"
              placeholder="e.g. Hyderabad Ordering Agent"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
            />
          </div>

          {/* Role + Model */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[#7b7f9e] text-xs font-medium mb-1.5">
                Role <span className="text-[#ef4444]">*</span>
              </label>
              <select
                className="w-full bg-[#252836] border border-[#2e3149] rounded-lg px-3 py-2.5 text-sm text-[#e8eaf0] focus:outline-none focus:border-[#6c63ff]"
                value={form.role}
                onChange={(e) => set("role", e.target.value)}
              >
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-[#7b7f9e] text-xs font-medium mb-1.5">Model</label>
              <select
                className="w-full bg-[#252836] border border-[#2e3149] rounded-lg px-3 py-2.5 text-sm text-[#e8eaf0] focus:outline-none focus:border-[#6c63ff]"
                value={form.model}
                onChange={(e) => set("model", e.target.value)}
              >
                {MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </div>

          {/* System Prompt */}
          <div>
            <label className="block text-[#7b7f9e] text-xs font-medium mb-1.5">
              System Prompt <span className="text-[#ef4444]">*</span>
            </label>
            <textarea
              rows={6}
              className="w-full bg-[#252836] border border-[#2e3149] rounded-lg px-3 py-2.5 text-sm text-[#e8eaf0] placeholder-[#7b7f9e] focus:outline-none focus:border-[#6c63ff] font-mono resize-none"
              placeholder="You are a restaurant search specialist..."
              value={form.system_prompt}
              onChange={(e) => set("system_prompt", e.target.value)}
            />
          </div>

          {/* Tools */}
          <div>
            <label className="block text-[#7b7f9e] text-xs font-medium mb-2">Tools</label>
            <div className="space-y-1.5">
              {AVAILABLE_TOOLS.map((tool) => (
                <label key={tool} className="flex items-center gap-2.5 cursor-pointer group">
                  <input
                    type="checkbox"
                    className="w-4 h-4 rounded border-[#2e3149] bg-[#252836] accent-[#6c63ff]"
                    checked={form.tools.includes(tool)}
                    onChange={() => toggleTool(tool)}
                  />
                  <span className="text-sm text-[#7b7f9e] group-hover:text-[#e8eaf0]">{tool}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Channels */}
          <div>
            <label className="block text-[#7b7f9e] text-xs font-medium mb-2">Channels</label>
            <div className="space-y-1.5">
              {["Telegram", "None"].map((ch) => (
                <label key={ch} className="flex items-center gap-2.5 cursor-pointer group">
                  <input
                    type="checkbox"
                    className="w-4 h-4 rounded border-[#2e3149] bg-[#252836] accent-[#6c63ff]"
                    checked={form.channels.includes(ch)}
                    onChange={() => toggleChannel(ch)}
                  />
                  <span className="text-sm text-[#7b7f9e] group-hover:text-[#e8eaf0]">{ch}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Advanced toggle */}
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="flex items-center gap-2 text-[#7b7f9e] text-sm hover:text-[#e8eaf0] transition-colors"
          >
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className={`w-4 h-4 transition-transform ${showAdvanced ? "rotate-90" : ""}`}
            >
              <path fillRule="evenodd" d="M7.293 4.293a1 1 0 011.414 0L13 8.586l-4.293 4.293a1 1 0 01-1.414-1.414L10.172 8 7.293 5.121a1 1 0 010-1.414L7.293 4.293z" clipRule="evenodd" />
            </svg>
            Advanced options
          </button>

          {showAdvanced && (
            <div className="space-y-4 pl-2 border-l-2 border-[#2e3149]">
              <div>
                <label className="block text-[#7b7f9e] text-xs font-medium mb-1.5">Schedule</label>
                <input
                  className="w-full bg-[#252836] border border-[#2e3149] rounded-lg px-3 py-2.5 text-sm text-[#e8eaf0] placeholder-[#7b7f9e] focus:outline-none focus:border-[#6c63ff]"
                  placeholder="0 9 * * *"
                  value={form.schedule ?? ""}
                  onChange={(e) => set("schedule", e.target.value || undefined)}
                />
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => set("memory_enabled", !form.memory_enabled)}
                  className={`relative w-10 h-5 rounded-full transition-colors ${form.memory_enabled ? "bg-[#6c63ff]" : "bg-[#252836]"}`}
                >
                  <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${form.memory_enabled ? "translate-x-5" : ""}`} />
                </button>
                <label className="text-[#7b7f9e] text-sm">Memory Enabled</label>
              </div>

              {form.memory_enabled && (
                <div>
                  <label className="block text-[#7b7f9e] text-xs font-medium mb-1.5">Memory Window</label>
                  <input
                    type="number" min={1} max={100}
                    className="w-24 bg-[#252836] border border-[#2e3149] rounded-lg px-3 py-2 text-sm text-[#e8eaf0] focus:outline-none focus:border-[#6c63ff]"
                    value={form.memory_window ?? 10}
                    onChange={(e) => set("memory_window", Number(e.target.value))}
                  />
                </div>
              )}

              <div>
                <label className="block text-[#7b7f9e] text-xs font-medium mb-1.5">Skills (comma-separated)</label>
                <input
                  className="w-full bg-[#252836] border border-[#2e3149] rounded-lg px-3 py-2.5 text-sm text-[#e8eaf0] placeholder-[#7b7f9e] focus:outline-none focus:border-[#6c63ff]"
                  placeholder="search, recommend, analyze"
                  value={(form.skills ?? []).join(", ")}
                  onChange={(e) =>
                    set("skills", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))
                  }
                />
              </div>

              <div>
                <label className="block text-[#7b7f9e] text-xs font-medium mb-1.5">Interaction Rules</label>
                <textarea
                  rows={3}
                  className="w-full bg-[#252836] border border-[#2e3149] rounded-lg px-3 py-2.5 text-sm text-[#e8eaf0] placeholder-[#7b7f9e] focus:outline-none focus:border-[#6c63ff] resize-none"
                  placeholder="Always be concise. Never mention pricing without context."
                  value={form.interaction_rules ?? ""}
                  onChange={(e) => set("interaction_rules", e.target.value || undefined)}
                />
              </div>
            </div>
          )}
        </form>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-[#2e3149] flex gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 px-4 py-2.5 rounded-lg border border-[#2e3149] text-[#7b7f9e] text-sm hover:bg-[#252836] hover:text-[#e8eaf0] transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="flex-1 px-4 py-2.5 rounded-lg bg-[#6c63ff] text-white text-sm font-medium hover:bg-[#574fd6] disabled:opacity-50 transition-colors"
          >
            {saving ? "Saving..." : agent ? "Update Agent" : "Create Agent"}
          </button>
        </div>
      </div>
    </div>
  );
}
