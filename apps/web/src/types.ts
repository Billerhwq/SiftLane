export type NodeType =
  | "start"
  | "http_request"
  | "browser_request"
  | "html_extract"
  | "json_extract"
  | "condition"
  | "loop"
  | "pagination"
  | "transform"
  | "emit";

export type RunStatus =
  | "QUEUED"
  | "RUNNING"
  | "CANCELLING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED";

export type UserRole = "admin" | "editor" | "viewer";
export type FlowVisibility = "private" | "team";

export interface JsonSchema {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
  additionalProperties?: boolean | JsonSchema;
  enum?: Array<string | number>;
  minimum?: number;
  maximum?: number;
}

export interface RetryPolicy {
  max_attempts: number;
  backoff_seconds: number;
  max_backoff_seconds: number;
  retryable_statuses: number[];
  retryable_errors: string[];
}

export interface FlowNodeRecord {
  id: string;
  type: NodeType;
  name: string;
  x: number;
  y: number;
  config: Record<string, unknown>;
  retry?: RetryPolicy;
}

export interface FlowEdgeRecord {
  id: string;
  source: string;
  target: string;
  source_port?: string;
}

export interface FlowDefinition {
  name: string;
  description: string;
  enabled: boolean;
  visibility: FlowVisibility;
  max_items: number;
  timeout_seconds: number;
  parameter_schema: Record<string, unknown>;
  nodes: FlowNodeRecord[];
  edges: FlowEdgeRecord[];
}

export interface FlowRecord extends FlowDefinition {
  id: string;
  owner_id: string;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface NodeCapability {
  type: NodeType;
  label: string;
  description: string;
  category: string;
  config_schema: JsonSchema;
  retry_schema: JsonSchema;
}

export interface Capabilities {
  protocolVersion: string;
  nodeTypes: NodeCapability[];
  connectorCount: number;
  features: Record<string, boolean>;
}

export interface Health {
  status: string;
  version: string;
  workers: number;
  queuedRuns: number;
  database: string;
  authMode: "local" | "team";
}

export interface RunRecord {
  id: string;
  flow_id: string;
  flow_name: string;
  flow_revision: number;
  owner_id: string;
  visibility: FlowVisibility;
  created_by: string;
  status: RunStatus;
  parameters: Record<string, unknown>;
  idempotency_key: string | null;
  current_node: string | null;
  message: string | null;
  processed_items: number;
  total_items: number | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface RunEvent {
  id: string;
  run_id: string;
  sequence: number;
  type: string;
  level: string;
  message: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface ItemRecord {
  id: string;
  run_id: string;
  external_id: string;
  url: string;
  title: string;
  content: string;
  media_type: string;
  observed_at: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ItemPage {
  items: ItemRecord[];
  next_cursor: string | null;
}

export type ImportStatus = "DRAFT" | "PROBING" | "PROBE_READY" | "COMPILING" | "DRAFT_READY" | "PREVIEWING" | "PREVIEW_READY" | "NEEDS_INPUT" | "UNSUPPORTED" | "CREATED" | "FAILED" | "CANCELLED";
export interface WebsiteImportRecord { id:string; owner_id:string; visibility:FlowVisibility; status:ImportStatus; source_url:string; intent:{description:string;fields:string[];item_type:string}; scope:{follow_details:boolean;preview_pages:number;allowed_domains:string[]}; runtime_preference:string; probe_revision:number;draft_revision:number;preview_revision:number;probe_report_json:Record<string,unknown>|null;flow_draft_json:{field_bindings?:Array<{field:string;selector:string;attribute:string;confidence:number;evidence:string[]}>}|null;created_flow_id:string|null;error_code:string|null;error_message:string|null;created_at:string;updated_at:string }
export interface ImportPreviewItem { id:string;import_id:string;draft_revision:number;external_id:string;normalized_json:Record<string,unknown>;field_evidence_json:Record<string,unknown>;quality_json:Record<string,unknown>;created_at:string }
export interface ImportEvent { id:string;import_id:string;sequence:number;type:string;level:string;message:string;data:Record<string,unknown>;created_at:string }

export interface ScheduleDefinition {
  flow_id: string;
  name: string;
  cron: string;
  timezone: string;
  enabled: boolean;
  parameters: Record<string, unknown>;
}

export interface ScheduleRecord extends ScheduleDefinition {
  id: string;
  owner_id: string;
  visibility: FlowVisibility;
  created_by: string;
  revision: number;
  next_run_at: string | null;
  last_run_at: string | null;
  last_run_id: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConnectorCapability {
  id: string;
  label: string;
  description: string;
  supports_cursor: boolean;
}

export interface ConnectorManifest {
  api_version: string;
  id: string;
  name: string;
  version: string;
  description: string;
  capabilities: ConnectorCapability[];
  runtime: {
    browser: boolean;
    allowed_domains: string[];
    media_download: boolean;
  };
}

export type ConnectorState = "enabled" | "disabled" | "error";

export interface ManagedConnectorRecord {
  id: string;
  version: string;
  previous_version: string | null;
  state: ConnectorState;
  source: string;
  manifest: ConnectorManifest;
  installed_at: string;
  updated_at: string;
}

export type SecretScope = "connector" | "delivery_target";

export interface SecretRecord {
  id: string;
  name: string;
  scope_type: SecretScope;
  scope_id: string;
  owner_id: string;
  created_by: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export type DeliveryTargetType = "webhook" | "ndjson";
export type DeliveryAuthScheme = "none" | "bearer" | "hmac_sha256";

export interface DeliveryTargetDefinition {
  name: string;
  type: DeliveryTargetType;
  visibility: FlowVisibility;
  enabled: boolean;
  url: string | null;
  auth_scheme: DeliveryAuthScheme;
  secret_id: string | null;
  max_attempts: number;
  backoff_seconds: number;
}

export interface DeliveryTargetRecord extends DeliveryTargetDefinition {
  id: string;
  owner_id: string;
  created_by: string;
  revision: number;
  created_at: string;
  updated_at: string;
}

export type DeliveryStatus = "queued" | "delivering" | "retrying" | "succeeded" | "dead_letter" | "cancelled";

export interface DeliveryRecord {
  id: string;
  target_id: string;
  run_id: string;
  idempotency_key: string;
  status: DeliveryStatus;
  attempt_count: number;
  next_attempt_at: string | null;
  response_status: number | null;
  error: string | null;
  artifact_path: string | null;
  payload_sha256: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
}

export interface UserRecord {
  id: string;
  username: string;
  display_name: string;
  role: UserRole;
  active: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

export interface CurrentUser extends UserRecord {
  auth_mode: "local" | "team";
}

export interface AuthSession {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: CurrentUser;
}

export interface AuditRecord {
  id: string;
  actor_user_id: string | null;
  actor_username: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  outcome: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface SecurityOperations {
  counters: Record<string, number>;
  recentAlerts: Array<{
    type: string;
    detail: Record<string, unknown>;
    created_at: string;
  }>;
}
