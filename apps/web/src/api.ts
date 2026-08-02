import type {
  Capabilities,
  ConnectorManifest,
  DeliveryAuthScheme,
  DeliveryRecord,
  DeliveryTargetDefinition,
  DeliveryTargetRecord,
  CurrentUser,
  AuditRecord,
  AuthSession,
  FlowDefinition,
  FlowRecord,
  Health,
  ItemPage,
  ManagedConnectorRecord,
  RunEvent,
  RunRecord,
  ScheduleDefinition,
  ScheduleRecord,
  SecurityOperations,
  SecretRecord,
  SecretScope,
  UserRecord,
  UserRole,
} from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8090").replace(/\/$/, "");
const API_TOKEN = import.meta.env.VITE_API_TOKEN ?? "";
const SESSION_KEY = "siftlane.session";
const SESSION_EXPIRY_KEY = "siftlane.session.expires";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

function sessionToken() {
  return window.localStorage.getItem(SESSION_KEY) ?? "";
}

export function clearSession() {
  window.localStorage.removeItem(SESSION_KEY);
  window.localStorage.removeItem(SESSION_EXPIRY_KEY);
}

function persistSession(session: AuthSession) {
  window.localStorage.setItem(SESSION_KEY, session.access_token);
  window.localStorage.setItem(SESSION_EXPIRY_KEY, session.expires_at);
}

function headers(extra?: HeadersInit): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...((sessionToken() || API_TOKEN) ? { Authorization: `Bearer ${sessionToken() || API_TOKEN}` } : {}),
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
    throw new ApiError(detail || `请求失败 (${response.status})`, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  me: () => request<CurrentUser>("/api/v1/auth/me"),
  login: async (username: string, password: string) => {
    const session = await request<AuthSession>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    persistSession(session);
    return session;
  },
  refreshSession: async () => {
    const session = await request<AuthSession>("/api/v1/auth/refresh", { method: "POST" });
    persistSession(session);
    return session;
  },
  logout: async () => {
    try {
      await request<void>("/api/v1/auth/logout", { method: "POST" });
    } finally {
      clearSession();
    }
  },
  users: () => request<UserRecord[]>("/api/v1/users"),
  createUser: (user: { username: string; display_name: string; password: string; role: UserRole }) =>
    request<UserRecord>("/api/v1/users", { method: "POST", body: JSON.stringify(user) }),
  updateUser: (id: string, update: Partial<{ display_name: string; password: string; role: UserRole; active: boolean }>) =>
    request<UserRecord>(`/api/v1/users/${id}`, { method: "PATCH", body: JSON.stringify(update) }),
  audit: () => request<AuditRecord[]>("/api/v1/audit?limit=200"),
  securityOperations: () => request<SecurityOperations>("/api/v1/operations/security"),
  capabilities: () => request<Capabilities>("/api/v1/capabilities"),
  connectors: () => request<ConnectorManifest[]>("/api/v1/connectors"),
  managedConnectors: () => request<ManagedConnectorRecord[]>("/api/v1/managed-connectors"),
  installConnector: (filename: string, sha256: string) => request<ManagedConnectorRecord>("/api/v1/managed-connectors/install", { method: "POST", body: JSON.stringify({ filename, sha256 }) }),
  upgradeConnector: (id: string, filename: string, sha256: string) => request<ManagedConnectorRecord>(`/api/v1/managed-connectors/${id}/upgrade`, { method: "POST", body: JSON.stringify({ filename, sha256 }) }),
  setConnectorEnabled: (id: string, enabled: boolean) => request<ManagedConnectorRecord>(`/api/v1/managed-connectors/${id}/${enabled ? "enable" : "disable"}`, { method: "POST" }),
  rollbackConnector: (id: string) => request<ManagedConnectorRecord>(`/api/v1/managed-connectors/${id}/rollback`, { method: "POST" }),
  uninstallConnector: (id: string) => request<void>(`/api/v1/managed-connectors/${id}`, { method: "DELETE" }),
  secrets: () => request<SecretRecord[]>("/api/v1/secrets"),
  createSecret: (secret: { name: string; scope_type: SecretScope; scope_id: string; value: string }) => request<SecretRecord>("/api/v1/secrets", { method: "POST", body: JSON.stringify(secret) }),
  deleteSecret: (id: string) => request<void>(`/api/v1/secrets/${id}`, { method: "DELETE" }),
  deliveryTargets: () => request<DeliveryTargetRecord[]>("/api/v1/delivery-targets"),
  createDeliveryTarget: (target: DeliveryTargetDefinition) => request<DeliveryTargetRecord>("/api/v1/delivery-targets", { method: "POST", body: JSON.stringify(target) }),
  updateDeliveryTarget: (target: DeliveryTargetRecord, update: Partial<DeliveryTargetDefinition> = {}) => {
    const definition: DeliveryTargetDefinition = {
      name: target.name,
      type: target.type,
      visibility: target.visibility,
      enabled: target.enabled,
      url: target.url,
      auth_scheme: target.auth_scheme,
      secret_id: target.secret_id,
      max_attempts: target.max_attempts,
      backoff_seconds: target.backoff_seconds,
      ...update,
    };
    return request<DeliveryTargetRecord>(`/api/v1/delivery-targets/${target.id}?expectedRevision=${target.revision}`, { method: "PUT", body: JSON.stringify(definition) });
  },
  deleteDeliveryTarget: (id: string) => request<void>(`/api/v1/delivery-targets/${id}`, { method: "DELETE" }),
  deliveries: () => request<DeliveryRecord[]>("/api/v1/deliveries?limit=200"),
  createDelivery: (targetId: string, runId: string, idempotencyKey: string) => request<DeliveryRecord>("/api/v1/deliveries", { method: "POST", body: JSON.stringify({ target_id: targetId, run_id: runId, idempotency_key: idempotencyKey }) }),
  replayDelivery: (id: string) => request<DeliveryRecord>(`/api/v1/deliveries/${id}/replay`, { method: "POST" }),
  cancelDelivery: (id: string) => request<DeliveryRecord>(`/api/v1/deliveries/${id}/cancel`, { method: "POST" }),
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
      visibility: flow.visibility,
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
  const cancelReader = () => {
    void reader.cancel().catch(() => undefined);
  };
  signal.addEventListener("abort", cancelReader, { once: true });
  if (signal.aborted) cancelReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
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
  } finally {
    signal.removeEventListener("abort", cancelReader);
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
