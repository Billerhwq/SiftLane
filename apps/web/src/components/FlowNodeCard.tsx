import { memo, type ComponentType } from "react";
import {
  ArrowRight,
  Braces,
  CodeXml,
  Download,
  GitBranch,
  Globe2,
  ListFilter,
  ListPlus,
  Repeat2,
} from "lucide-react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { FlowNodeRecord, NodeType } from "../types";

export type NodeExecutionState = "idle" | "running" | "completed" | "failed";

export interface FlowNodeData extends Record<string, unknown> {
  record: FlowNodeRecord;
  executionState: NodeExecutionState;
}

const icons: Record<NodeType, ComponentType<{ size?: number }>> = {
  start: ArrowRight,
  http_request: Globe2,
  browser_request: Globe2,
  html_extract: CodeXml,
  json_extract: Braces,
  condition: GitBranch,
  loop: Repeat2,
  pagination: ListPlus,
  transform: ListFilter,
  emit: Download,
};

const labels: Record<NodeType, string> = {
  start: "START",
  http_request: "HTTP",
  browser_request: "BROWSER",
  html_extract: "HTML",
  json_extract: "JSON",
  condition: "IF",
  loop: "LOOP",
  pagination: "PAGES",
  transform: "MAP",
  emit: "EMIT",
};

const states: Record<NodeExecutionState, string> = {
  idle: "WAITING",
  running: "RUNNING",
  completed: "DONE",
  failed: "FAILED",
};

function summary(node: FlowNodeRecord): string {
  const config = node.config;
  if (node.type === "start") {
    const urls = Array.isArray(config.urls) ? config.urls.length : 0;
    return `${urls} seed URLs`;
  }
  if (node.type === "http_request") return `GET / ${String(config.url ?? "{{url}}")}`;
  if (node.type === "browser_request") return `RENDER / ${String(config.url ?? "{{url}}")}`;
  if (node.type === "html_extract") {
    return `${String(config.item_selector || "document")} / ${Object.keys((config.fields as object) ?? {}).length} fields`;
  }
  if (node.type === "json_extract") return `${String(config.items_path || "root")} / JSON path`;
  if (node.type === "condition") return `${String(config.field || "field")} ${String(config.operator || "eq")}`;
  if (node.type === "loop") return `${String(config.items_path || "items")} / ${String(config.max_iterations || 1)} max`;
  if (node.type === "pagination") return `${String(config.page_parameter || "page")} / ${String(config.max_pages || 1)} pages`;
  if (node.type === "transform") return `${Object.keys((config.mapping as object) ?? {}).length} field mappings`;
  return "normalized items";
}

export const FlowNodeCard = memo(function FlowNodeCard({ data, selected }: NodeProps) {
  const typed = data as FlowNodeData;
  const node = typed.record;
  const Icon = icons[node.type];
  return (
    <article className={`flow-node state-${typed.executionState} ${selected ? "selected" : ""}`} data-node-type={node.type}>
      {node.type !== "start" && <Handle type="target" position={Position.Left} />}
      <div className="flow-node__head">
        <span><i><Icon size={13} /></i>{labels[node.type]}</span>
        <span>{node.id.slice(0, 8)}</span>
      </div>
      <strong>{node.name}</strong>
      <code title={summary(node)}>{summary(node)}</code>
      <span className="flow-node__state">{states[typed.executionState]}</span>
      {node.type === "condition" ? (
        <>
          <Handle id="true" className="condition-handle condition-handle--true" type="source" position={Position.Right} />
          <Handle id="false" className="condition-handle condition-handle--false" type="source" position={Position.Right} />
          <span className="condition-label condition-label--true">T</span>
          <span className="condition-label condition-label--false">F</span>
        </>
      ) : node.type !== "emit" && <Handle id="default" type="source" position={Position.Right} />}
    </article>
  );
});
