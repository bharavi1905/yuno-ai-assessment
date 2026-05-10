import { useCallback, useEffect } from "react";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  useNodesState,
  useEdgesState,
  MarkerType,
  type Node,
  type Edge,
  type NodeProps,
} from "reactflow";
import "reactflow/dist/style.css";

const NODE_STATUS_COLORS: Record<string, { border: string; bg: string; text: string; glow: string }> = {
  active:    { border: "#6c63ff", bg: "#1e1b4b", text: "#a5b4fc", glow: "0 0 12px #6c63ff80" },
  completed: { border: "#22c55e", bg: "#052e16", text: "#86efac", glow: "0 0 8px #22c55e40" },
  error:     { border: "#ef4444", bg: "#2d0a0a", text: "#fca5a5", glow: "0 0 8px #ef444440" },
  idle:      { border: "#2e3149", bg: "#1a1d27", text: "#7b7f9e", glow: "none" },
};

const NODE_ICONS: Record<string, string> = {
  router:       "⇢",
  ordering:     "🍽",
  fraud:        "🛡",
  payment:      "💳",
  hitl:         "👤",
  notification: "📣",
  complaint:    "🎧",
};

function WorkflowNode({ data }: NodeProps) {
  const statusKey = (data.status as string) in NODE_STATUS_COLORS ? data.status as string : "idle";
  const colors = NODE_STATUS_COLORS[statusKey];

  return (
    <>
      <Handle type="target" position={Position.Top} style={{ background: "#4b5280", border: "none", width: 8, height: 8 }} />
      <div
        className="px-4 py-3 rounded-xl border-2 min-w-[130px] text-center transition-all duration-300"
        style={{
          borderColor: colors.border,
          backgroundColor: colors.bg,
          boxShadow: colors.glow,
        }}
      >
        <div className="text-xl mb-1">{NODE_ICONS[data.nodeId] ?? "◆"}</div>
        <div className="font-semibold text-xs" style={{ color: colors.text }}>
          {data.label}
        </div>
        {data.status === "active" && (
          <div className="mt-1.5 flex justify-center">
            <span className="w-2 h-2 rounded-full bg-[#6c63ff] animate-ping" />
          </div>
        )}
        {data.model && (
          <div className="mt-1 text-[10px] text-[#7b7f9e]">{data.model}</div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ background: "#4b5280", border: "none", width: 8, height: 8 }} />
    </>
  );
}

const nodeTypes = { workflowNode: WorkflowNode };

// Food ordering: router → ordering (HITL via HumanInTheLoopMiddleware on confirm_order)
//   → hitl → fraud → payment → notification
// Correction loop: hitl → ordering (retry_order)
const FOOD_ORDERING_NODES: Node[] = [
  { id: "router",   type: "workflowNode", position: { x: 250, y: 20  }, data: { nodeId: "router",   label: "Router",    status: "idle" } },
  { id: "ordering",     type: "workflowNode", position: { x: 250, y: 130 }, data: { nodeId: "ordering",     label: "Ordering",      status: "idle" } },
  { id: "hitl",         type: "workflowNode", position: { x: 250, y: 240 }, data: { nodeId: "hitl",         label: "HITL (Human)",  status: "idle" } },
  { id: "fraud",        type: "workflowNode", position: { x: 130, y: 360 }, data: { nodeId: "fraud",        label: "Fraud Check",   status: "idle" } },
  { id: "payment",      type: "workflowNode", position: { x: 130, y: 470 }, data: { nodeId: "payment",      label: "Payment",       status: "idle" } },
  { id: "notification", type: "workflowNode", position: { x: 250, y: 570 }, data: { nodeId: "notification", label: "Notification",  status: "idle" } },
];

const FOOD_ORDERING_EDGES: Edge[] = [
  { id: "e-sup-ord",  source: "router", target: "ordering",     animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#4b5280" } },
  { id: "e-ord-hit",  source: "ordering",   target: "hitl",         animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#4b5280" } },
  // HITL confirmed → fraud check
  { id: "e-hit-fr",   source: "hitl",       target: "fraud",        label: "YES",    animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#22c55e" }, labelStyle: { fill: "#22c55e", fontSize: 10 }, labelBgStyle: { fill: "#052e16" } },
  // HITL correction → re-run ordering with feedback (HumanInTheLoopMiddleware reject decision)
  { id: "e-hit-ord",  source: "hitl",       target: "ordering",     label: "retry",  animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#f59e0b", strokeDasharray: "4 4" }, labelStyle: { fill: "#f59e0b", fontSize: 10 }, labelBgStyle: { fill: "#1c1500" } },
  { id: "e-fr-pay",   source: "fraud",      target: "payment",      label: "approve", animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#22c55e" }, labelStyle: { fill: "#22c55e", fontSize: 10 }, labelBgStyle: { fill: "#052e16" } },
  { id: "e-fr-not",   source: "fraud",      target: "notification", label: "block",  animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#ef4444" }, labelStyle: { fill: "#ef4444", fontSize: 10 }, labelBgStyle: { fill: "#2d0a0a" } },
  { id: "e-pay-not",  source: "payment",    target: "notification", animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#4b5280" } },
];


// complaint_resolution actual flow from builder.py + edges.py:
//   router → complaint → fraud
//   fraud → hitl (approve) | fraud → notification (block)
//   hitl → complaint (reprompt loop) | hitl → ordering (re-order) | hitl → notification (compensate/NO/expire)
//   ordering → hitl (loop: food found, needs confirmation)
const COMPLAINT_RESOLUTION_NODES: Node[] = [
  { id: "router",   type: "workflowNode", position: { x: 300, y: 20  }, data: { nodeId: "router",   label: "Router",        status: "idle" } },
  { id: "complaint",    type: "workflowNode", position: { x: 300, y: 140 }, data: { nodeId: "complaint",    label: "Complaint AI",  status: "idle" } },
  { id: "fraud",        type: "workflowNode", position: { x: 300, y: 270 }, data: { nodeId: "fraud",        label: "Fraud Check",   status: "idle" } },
  { id: "hitl",         type: "workflowNode", position: { x: 120, y: 410 }, data: { nodeId: "hitl",         label: "HITL (Human)",  status: "idle" } },
  { id: "ordering",     type: "workflowNode", position: { x: 120, y: 550 }, data: { nodeId: "ordering",     label: "Ordering",      status: "idle" } },
  { id: "notification", type: "workflowNode", position: { x: 480, y: 410 }, data: { nodeId: "notification", label: "Notification",  status: "idle" } },
];

const COMPLAINT_RESOLUTION_EDGES: Edge[] = [
  // main spine
  { id: "e-sup-com",  source: "router", target: "complaint",    animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#4b5280" } },
  { id: "e-com-fr",   source: "complaint",  target: "fraud",        animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#4b5280" } },
  // fraud branch
  { id: "e-fr-hit",   source: "fraud",      target: "hitl",         label: "approve",      animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#22c55e" }, labelStyle: { fill: "#22c55e", fontSize: 10 }, labelBgStyle: { fill: "#052e16" } },
  { id: "e-fr-not",   source: "fraud",      target: "notification", label: "block",        animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#ef4444" }, labelStyle: { fill: "#ef4444", fontSize: 10 }, labelBgStyle: { fill: "#2d0a0a" } },
  // hitl branches
  { id: "e-hit-ord",  source: "hitl",       target: "ordering",     label: "re-order",     animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#6c63ff" }, labelStyle: { fill: "#a5b4fc", fontSize: 10 }, labelBgStyle: { fill: "#1e1b4b" } },
  { id: "e-hit-not",  source: "hitl",       target: "notification", label: "compensate/NO",animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#22c55e" }, labelStyle: { fill: "#22c55e", fontSize: 10 }, labelBgStyle: { fill: "#052e16" } },
  { id: "e-hit-com",  source: "hitl",       target: "complaint",    label: "reprompt",     animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#f59e0b", strokeDasharray: "4 4" }, labelStyle: { fill: "#f59e0b", fontSize: 10 }, labelBgStyle: { fill: "#1c1500" } },
  // ordering loops back to hitl for confirmation
  { id: "e-ord-hit",  source: "ordering",   target: "hitl",         label: "food found",   animated: false, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#4b5280", strokeDasharray: "4 4" }, labelStyle: { fill: "#9ca3af", fontSize: 10 }, labelBgStyle: { fill: "#1a1d27" } },
];

interface Props {
  workflowType: "food_ordering" | "complaint_resolution";
  nodeStatuses?: Record<string, "idle" | "active" | "completed" | "error">;
  agentModels?: Record<string, string>;
}

export default function WorkflowCanvas({ workflowType, nodeStatuses = {}, agentModels = {} }: Props) {
  const baseNodes = workflowType === "complaint_resolution" ? COMPLAINT_RESOLUTION_NODES : FOOD_ORDERING_NODES;
  const baseEdges = workflowType === "complaint_resolution" ? COMPLAINT_RESOLUTION_EDGES : FOOD_ORDERING_EDGES;

  const initialNodes = baseNodes.map((n) => ({
    ...n,
    data: {
      ...n.data,
      status: nodeStatuses[n.id] ?? "idle",
      model: agentModels[n.id],
    },
  }));

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(baseEdges);

  useEffect(() => {
    setNodes((prev) =>
      prev.map((n) => ({
        ...n,
        data: {
          ...n.data,
          status: nodeStatuses[n.id] ?? "idle",
          model: agentModels[n.id],
        },
      }))
    );

    const activeNodeId = Object.entries(nodeStatuses).find(([, v]) => v === "active")?.[0];
    setEdges(
      baseEdges.map((e) => ({
        ...e,
        animated: !!(activeNodeId && (e.source === activeNodeId || e.target === activeNodeId)),
      }))
    );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeStatuses, agentModels]);

  const onInit = useCallback((instance: { fitView: () => void }) => {
    instance.fitView();
  }, []);

  return (
    <div className="w-full h-full" style={{ background: "#0f1117" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        onInit={onInit}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#2e3149" gap={20} size={1} />
        <Controls
          className="[&>button]:bg-[#1a1d27] [&>button]:border-[#2e3149] [&>button]:text-[#7b7f9e]"
        />
        <MiniMap
          nodeColor={(n) => {
            const s = (n.data?.status as string) ?? "idle";
            return NODE_STATUS_COLORS[s]?.border ?? "#2e3149";
          }}
          style={{ background: "#1a1d27", border: "1px solid #2e3149" }}
          maskColor="rgba(0,0,0,0.4)"
        />
      </ReactFlow>
    </div>
  );
}
