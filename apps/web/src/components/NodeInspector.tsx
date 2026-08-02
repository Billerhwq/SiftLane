import { useEffect, useState } from "react";
import { AlertTriangle, Trash2 } from "lucide-react";
import type { FlowNodeRecord, JsonSchema, NodeCapability } from "../types";

interface Props {
  node: FlowNodeRecord;
  capability?: NodeCapability;
  onChange: (node: FlowNodeRecord) => void;
  onDelete: () => void;
  readOnly?: boolean;
}

function JsonField({ value, onChange, disabled = false }: { value: unknown; onChange: (value: unknown) => void; disabled?: boolean }) {
  const [text, setText] = useState(() => JSON.stringify(value ?? {}, null, 2));
  const [error, setError] = useState("");

  useEffect(() => setText(JSON.stringify(value ?? {}, null, 2)), [value]);

  function commit() {
    try {
      onChange(JSON.parse(text));
      setError("");
    } catch {
      setError("请输入有效 JSON");
    }
  }

  return (
    <>
      <textarea
        disabled={disabled}
        className={error ? "invalid" : ""}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={commit}
        spellCheck={false}
      />
      {error && <span className="field-error"><AlertTriangle size={12} />{error}</span>}
    </>
  );
}

function ConfigField({
  name,
  schema,
  value,
  required,
  onChange,
  disabled = false,
}: {
  name: string;
  schema: JsonSchema;
  value: unknown;
  required: boolean;
  onChange: (value: unknown) => void;
  disabled?: boolean;
}) {
  const title = schema.title ?? name.replaceAll("_", " ");
  if (schema.enum?.length) {
    return (
      <label className="field">
        <span>{title}{required ? " *" : ""}</span>
        <select disabled={disabled} value={String(value ?? schema.default ?? "")} onChange={(event) => onChange(event.target.value)}>
          {schema.enum.map((option) => <option key={String(option)} value={String(option)}>{String(option)}</option>)}
        </select>
      </label>
    );
  }
  if (schema.type === "boolean") {
    return (
      <label className="switch-field">
        <span>{title}{required ? " *" : ""}</span>
        <input disabled={disabled} type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
        <i aria-hidden="true" />
      </label>
    );
  }
  if (schema.type === "array") {
    const separator = schema.items?.type === "integer" || schema.items?.type === "number" ? /[\n,]+/ : /\n/;
    return (
      <label className="field">
        <span>{title}{required ? " *" : ""}</span>
        <textarea
          disabled={disabled}
          value={Array.isArray(value) ? value.join("\n") : ""}
          onChange={(event) => onChange(event.target.value.split(separator).map((item) => item.trim()).filter(Boolean).map((item) => schema.items?.type === "integer" || schema.items?.type === "number" ? Number(item) : item))}
          placeholder="每行一项"
        />
      </label>
    );
  }
  if (schema.type === "integer" || schema.type === "number") {
    return (
      <label className="field">
        <span>{title}{required ? " *" : ""}</span>
        <input
          disabled={disabled}
          type="number"
          min={schema.minimum}
          max={schema.maximum}
          step={schema.type === "integer" ? 1 : "any"}
          value={typeof value === "number" ? value : Number(schema.default ?? 0)}
          onChange={(event) => onChange(schema.type === "integer" ? Number.parseInt(event.target.value, 10) : Number(event.target.value))}
        />
      </label>
    );
  }
  if (schema.type === "object") {
    return (
      <label className="field">
        <span>{title}{required ? " *" : ""}</span>
        <JsonField value={value} onChange={onChange} disabled={disabled} />
      </label>
    );
  }
  return (
    <label className="field">
      <span>{title}{required ? " *" : ""}</span>
      <input
        disabled={disabled}
        value={String(value ?? "")}
        onChange={(event) => onChange(event.target.value)}
        placeholder={schema.description}
      />
    </label>
  );
}

export function NodeInspector({ node, capability, onChange, onDelete, readOnly = false }: Props) {
  const properties = capability?.config_schema.properties ?? {};
  const required = new Set(capability?.config_schema.required ?? []);
  const retryProperties = capability?.retry_schema.properties ?? {};
  const retryRequired = new Set(capability?.retry_schema.required ?? []);
  const retry = node.retry ?? {
    max_attempts: 1,
    backoff_seconds: 0.25,
    max_backoff_seconds: 10,
    retryable_statuses: [408, 429, 500, 502, 503, 504],
    retryable_errors: ["TimeoutError", "ConnectionError", "HTTPStatusError"],
  };
  return (
    <aside className="inspector" aria-label="节点设置">
      <header className="inspector__header">
        <strong>节点设置</strong>
        <span>{node.type.toUpperCase()}</span>
      </header>
      <section className="inspector__section">
        <div className="section-heading"><strong>基本信息</strong></div>
        <label className="field">
          <span>节点名称</span>
          <input disabled={readOnly} value={node.name} onChange={(event) => onChange({ ...node, name: event.target.value })} />
        </label>
        <label className="field">
          <span>节点 ID</span>
          <input value={node.id} disabled />
        </label>
      </section>
      <section className="inspector__section">
        <div className="section-heading">
          <strong>Retry policy</strong>
          <span>{retry.max_attempts} attempts</span>
        </div>
        {Object.entries(retryProperties).map(([name, schema]) => (
          <ConfigField
            key={name}
            name={name}
            schema={schema}
            value={retry[name as keyof typeof retry]}
            required={retryRequired.has(name)}
            disabled={readOnly}
            onChange={(value) => onChange({ ...node, retry: { ...retry, [name]: value } })}
          />
        ))}
      </section>
      <section className="inspector__section">
        <div className="section-heading">
          <strong>执行配置</strong>
          <span>{Object.keys(properties).length} 项</span>
        </div>
        {Object.entries(properties).map(([name, schema]) => (
          <ConfigField
            key={name}
            name={name}
            schema={schema}
            value={node.config[name]}
            required={required.has(name)}
            disabled={readOnly}
            onChange={(value) => onChange({ ...node, config: { ...node.config, [name]: value } })}
          />
        ))}
        {!Object.keys(properties).length && <p className="quiet-empty">此节点无需额外配置</p>}
      </section>
      <p className="policy-note"><AlertTriangle size={14} />配置遵循 JSON Schema，节点不执行任意 Python 或 JavaScript。</p>
      <button className="danger-button" type="button" disabled={readOnly} onClick={onDelete}><Trash2 size={14} />删除节点</button>
    </aside>
  );
}
