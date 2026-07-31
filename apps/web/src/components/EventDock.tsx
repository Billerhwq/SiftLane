import { ChevronDown, ChevronUp, CircleStop, Radio } from "lucide-react";
import type { RunEvent, RunRecord } from "../types";

interface Props {
  run?: RunRecord;
  events: RunEvent[];
  expanded: boolean;
  onExpandedChange: (value: boolean) => void;
  onCancel: () => void;
  streamState: "idle" | "connecting" | "connected" | "disconnected";
}

function time(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

export function EventDock({ run, events, expanded, onExpandedChange, onCancel, streamState }: Props) {
  const visible = events.slice(-2);
  const active = run && ["QUEUED", "RUNNING", "CANCELLING"].includes(run.status);
  const streamLabel = active
    ? streamState === "connected"
      ? "事件流已连接"
      : streamState === "disconnected"
        ? "事件流已断开"
        : "正在连接事件流"
    : run ? run.status : "尚未运行";
  return (
    <section className={`event-dock ${expanded ? "expanded" : ""}`} aria-label="运行事件">
      {expanded && (
        <div className="event-ledger">
          <header>
            <div><Radio size={15} /><strong>完整运行记录</strong><code>{run?.id.slice(0, 12) ?? "NO RUN"}</code></div>
            <button className="icon-button" onClick={() => onExpandedChange(false)} title="收起完整记录" aria-label="收起完整记录"><ChevronDown size={16} /></button>
          </header>
          {events.length ? (
            <ol>
              {events.map((event) => (
                <li key={event.id} className={`level-${event.level}`}>
                  <b>{String(event.sequence).padStart(2, "0")}</b>
                  <span>{event.message}</span>
                  <code>{event.type}</code>
                  <time>{time(event.created_at)}</time>
                </li>
              ))}
            </ol>
          ) : <div className="ledger-empty">当前运行还没有事件</div>}
        </div>
      )}
      <div className="event-dock__label">
        <strong>实时活动</strong>
        <span className={streamState === "connected" ? "live" : streamState === "disconnected" ? "disconnected" : ""}>{streamLabel}</span>
      </div>
      <div className="event-dock__lines" aria-live="polite">
        {visible.length ? visible.map((event) => (
          <div className="event-line" key={event.id}>
            <i />
            <time>{time(event.created_at)}</time>
            <b>{event.message}</b>
            <span>{event.type}</span>
          </div>
        )) : <span className="event-placeholder">运行流程后，此处显示最近两条活动</span>}
      </div>
      <div className="event-dock__actions">
        {active && <button className="icon-button danger-icon" onClick={onCancel} title="取消运行" aria-label="取消运行"><CircleStop size={16} /></button>}
        <button className="detail-button" onClick={() => onExpandedChange(!expanded)} aria-expanded={expanded}>
          {expanded ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          {events.length} 条事件
        </button>
      </div>
    </section>
  );
}
