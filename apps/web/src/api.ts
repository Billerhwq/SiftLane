import type {
  Capabilities,
  ConnectorManifest,
  FlowDefinition,
  FlowRecord,
  Health,
  ItemPage,
  RunEvent,
  RunRecord,
  ScheduleDefinition,
  ScheduleRecord,
} from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8090").replace(/\/$/, "");
const API_TOKEN = import.meta.env.VITE_API_TOKEN ?? "";

function headers(extra?: HeadersInit): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
    ...extra,
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: headers(init?.headers),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? body ?? {});
    throw new Error(detail || `请求失败 (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  capabilities: () => request<Capabilities>("/api/v1/capabilities"),
  connectors: () => request<ConnectorManifest[]>("/api/v1/connectors"),
  schedules: () => request<ScheduleRecord[]>("/api/v1/schedules"),
  createSchedule: (definition: ScheduleDefinition) =>
    request<ScheduleRecord>("/api/v1/schedules", { method: "POST", body: JSON.stringify(definition) }),
  updateSchedule: (schedule: ScheduleRecord) => {
    const definition: ScheduleDefinition = {
      flow_id: schedule.flow_id,
      name: schedule.name,
      cron: schedule.cron,
      timezone: schedule.timezone,
      enabled: schedule.enabled,
      parameters: schedule.parameters,
    };
    return request<ScheduleRecord>(`/api/v1/schedules/${schedule.id}?expectedRevision=${schedule.revision}`, {
      method: "PUT",
      body: JSON.stringify(definition),
    });
  },
  deleteSchedule: (id: string) => request<void>(`/api/v1/schedules/${id}`, { method: "DELETE" }),
  triggerSchedule: (id: string) => request<RunRecord>(`/api/v1/schedules/${id}/trigger`, { method: "POST" }),
  flows: () => request<FlowRecord[]>("/api/v1/flows"),
  createFlow: (definition: FlowDefinition) =>
    request<FlowRecord>("/api/v1/flows", { method: "POST", body: JSON.stringify(definition) }),
  updateFlow: (flow: FlowRecord) => {
    const definition: FlowDefinition = {
      name: flow.name,
      description: flow.description,
      enabled: flow.enabled,
      max_items: flow.max_items,
      timeout_seconds: flow.timeout_seconds,
      parameter_schema: flow.parameter_schema,
      nodes: flow.nodes,
      edges: flow.edges,
    };
    return request<FlowRecord>(`/api/v1/flows/${flow.id}?expectedRevision=${flow.revision}`, {
      method: "PUT",
      body: JSON.stringify(definition),
    });
  },
  deleteFlow: (id: string) => request<void>(`/api/v1/flows/${id}`, { method: "DELETE" }),
  runs: () => request<RunRecord[]>("/api/v1/runs?limit=200"),
  createRun: (flowId: string) => request<RunRecord>("/api/v1/runs", {
    method: "POST",
    body: JSON.stringify({ flow_id: flowId, parameters: {}, idempotency_key: crypto.randomUUID() }),
  }),
  cancelRun: (runId: string) => request<RunRecord>(`/api/v1/runs/${runId}/cancel`, { method: "POST" }),
  events: (runId: string) => request<RunEvent[]>(`/api/v1/runs/${runId}/events`),
  items: (runId: string) => request<ItemPage>(`/api/v1/runs/${runId}/items?limit=200`),
};

export async function streamRunEvents(
  runId: string,
  after: number,
  signal: AbortSignal,
  onEvent: (event: RunEvent) => void,
  onOpen?: () => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/runs/${runId}/events/stream?after=${after}`, {
    headers: headers(after > 0 ? { "Last-Event-ID": String(after) } : undefined),
    signal,
  });
  if (!response.ok || !response.body) throw new Error(`事件流连接失败 (${response.status})`);
  onOpen?.();

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const data = chunk.split("\n").find((line) => line.startsWith("data: "));
      if (data) onEvent(JSON.parse(data.slice(6)) as RunEvent);
    }
  }
}
