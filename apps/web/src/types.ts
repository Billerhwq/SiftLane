export type NodeType =
  | "start"
  | "http_request"
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
  max_items: number;
  timeout_seconds: number;
  parameter_schema: Record<string, unknown>;
  nodes: FlowNodeRecord[];
  edges: FlowEdgeRecord[];
}

export interface FlowRecord extends FlowDefinition {
  id: string;
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
}

export interface RunRecord {
  id: string;
  flow_id: string;
  flow_name: string;
  flow_revision: number;
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
