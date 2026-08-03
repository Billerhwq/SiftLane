import { Button, Empty, Input, Table, Tag, type TableColumnsType } from "antd";
import { Activity, ArrowRight, Clock3, Search, Workflow } from "lucide-react";
import { useMemo } from "react";

import type { FlowRecord, RunRecord } from "../types";

type Props = {
  flows: FlowRecord[];
  runs: RunRecord[];
  loading: boolean;
  query: string;
  selectedFlowId: string | null;
  onQueryChange: (value: string) => void;
  onOpen: (flowId: string) => void;
  onOpenRun: (run: RunRecord) => void;
};

function dateTime(value?: string | null) {
  if (!value) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function duration(run: RunRecord) {
  if (!run.started_at) return "--";
  const end = run.finished_at ? new Date(run.finished_at).getTime() : Date.now();
  return `${Math.max(0, (end - new Date(run.started_at).getTime()) / 1000).toFixed(1)}s`;
}

const runStatusLabel: Record<string, string> = {
  QUEUED: "排队中",
  RUNNING: "运行中",
  CANCELLING: "取消中",
  SUCCEEDED: "成功",
  FAILED: "失败",
  CANCELLED: "已取消",
};

const runStatusColor: Record<string, string> = {
  QUEUED: "warning",
  RUNNING: "processing",
  CANCELLING: "warning",
  SUCCEEDED: "success",
  FAILED: "error",
  CANCELLED: "default",
};

export function FlowLibrary({ flows, runs, loading, query, selectedFlowId, onQueryChange, onOpen, onOpenRun }: Props) {
  const latestRunByFlow = useMemo(() => {
    const latest = new Map<string, RunRecord>();
    runs.forEach((run) => {
      if (!latest.has(run.flow_id)) latest.set(run.flow_id, run);
    });
    return latest;
  }, [runs]);

  const columns: TableColumnsType<FlowRecord> = [
    {
      title: "状态",
      key: "status",
      width: 86,
      render: (_, flow) => <Tag color={flow.enabled ? "success" : "default"}>{flow.enabled ? "已启用" : "已暂停"}</Tag>,
    },
    {
      title: "流程 / ID",
      key: "flow",
      render: (_, flow) => (
        <span className="flow-library__identity">
          <strong>{flow.name}</strong>
          <code>{flow.id}</code>
        </span>
      ),
    },
    {
      title: "版本",
      dataIndex: "revision",
      width: 86,
      render: (revision: number) => <code>REV {String(revision).padStart(2, "0")}</code>,
    },
    {
      title: "节点",
      key: "nodes",
      width: 82,
      render: (_, flow) => <span>{flow.nodes.length}</span>,
    },
    {
      title: "最近运行",
      key: "lastRun",
      width: 190,
      render: (_, flow) => {
        const run = latestRunByFlow.get(flow.id);
        return run ? (
          <span className="flow-library__last-run">
            <Tag color={runStatusColor[run.status]}>{runStatusLabel[run.status] ?? run.status}</Tag>
            <time>{dateTime(run.created_at)}</time>
          </span>
        ) : <span className="flow-library__quiet">尚未运行</span>;
      },
    },
    {
      title: "最近更新",
      dataIndex: "updated_at",
      width: 150,
      render: (value: string) => <time>{dateTime(value)}</time>,
    },
    {
      title: "操作",
      key: "action",
      width: 112,
      render: (_, flow) => (
        <Button type="link" icon={<ArrowRight size={13} />} iconPosition="end" onClick={(event) => { event.stopPropagation(); onOpen(flow.id); }}>
          打开编排
        </Button>
      ),
    },
  ];

  return (
    <section className="flow-library" aria-labelledby="flow-library-title">
      <header className="flow-library__toolbar">
        <div>
          <Workflow size={18} />
          <span><h1 id="flow-library-title">流程库</h1><small>{flows.length} 个匹配流程</small></span>
        </div>
        <div>
          <Input prefix={<Search size={14} />} value={query} onChange={(event) => onQueryChange(event.target.value)} allowClear placeholder="搜索流程" aria-label="搜索流程" />
        </div>
      </header>

      <div className="flow-library__table">
        <Table<FlowRecord>
          rowKey="id"
          size="small"
          columns={columns}
          dataSource={flows}
          loading={loading}
          pagination={{ pageSize: 12, size: "small", showSizeChanger: false, hideOnSinglePage: true }}
          scroll={{ x: 960 }}
          rowClassName={(flow) => flow.id === selectedFlowId ? "flow-library__row-selected" : ""}
          onRow={(flow) => ({
            onClick: () => onOpen(flow.id),
            onKeyDown: (event) => {
              if (event.target !== event.currentTarget) return;
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onOpen(flow.id);
              }
            },
            tabIndex: 0,
            "aria-selected": flow.id === selectedFlowId,
          })}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={query ? "没有匹配的流程" : "还没有流程"} /> }}
        />
      </div>

      <section className="flow-library__recent" aria-labelledby="recent-runs-title">
        <header><div><Activity size={15} /><strong id="recent-runs-title">最近运行</strong></div><span>{Math.min(runs.length, 4)} / {runs.length}</span></header>
        <div>
          {runs.slice(0, 4).map((run) => (
            <button key={run.id} onClick={() => onOpenRun(run)}>
              <i className={`run-${run.status.toLowerCase()}`} />
              <span><strong>{run.flow_name}</strong><small>{run.message ?? run.error_message ?? run.id}</small></span>
              <span><Tag color={runStatusColor[run.status]}>{runStatusLabel[run.status] ?? run.status}</Tag><time><Clock3 size={11} />{dateTime(run.created_at)} · {duration(run)}</time></span>
              <ArrowRight size={14} />
            </button>
          ))}
          {!runs.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有运行记录" />}
        </div>
      </section>
    </section>
  );
}
