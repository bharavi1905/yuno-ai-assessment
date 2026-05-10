const WS_BASE = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000";

export interface LogEvent {
  type: string;
  node?: string;
  run_id?: string;
  message?: string;
  timestamp?: string;
  result?: Record<string, unknown>;
  tokens?: { input: number; output: number; cost_usd: number };
  [key: string]: unknown;
}

export function createLogStream(
  runId: string,
  onEvent: (event: LogEvent) => void,
  onClose?: () => void,
): () => void {
  const ws = new WebSocket(`${WS_BASE}/ws/logs/${runId}`);
  ws.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data as string) as LogEvent);
    } catch {
      // ignore malformed events
    }
  };
  ws.onclose = () => onClose?.();
  ws.onerror = () => onClose?.();
  return () => ws.close();
}

export function createMonitorStream(
  onEvent: (event: LogEvent) => void,
  onConnectionChange?: (connected: boolean) => void,
): () => void {
  let ws: WebSocket;
  let reconnectTimer: ReturnType<typeof setTimeout>;
  let stopped = false;

  function connect() {
    if (stopped) return;
    ws = new WebSocket(`${WS_BASE}/ws/monitor`);
    ws.onopen = () => onConnectionChange?.(true);
    ws.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data as string) as LogEvent;
        if (ev.type !== "ping") onEvent(ev);
      } catch {
        // ignore
      }
    };
    ws.onclose = () => {
      onConnectionChange?.(false);
      if (!stopped) reconnectTimer = setTimeout(connect, 3000);
    };
    ws.onerror = () => ws.close();
  }

  connect();
  return () => {
    stopped = true;
    clearTimeout(reconnectTimer);
    ws?.close();
  };
}
