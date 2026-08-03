import { useMemo, useRef, useState } from "react";
import {
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tabs,
  Tooltip,
  type TableProps,
} from "antd";
import {
  Activity,
  ArrowRight,
  CalendarClock,
  ChevronRight,
  CirclePause,
  Clock3,
  Edit3,
  ListFilter,
  Play,
  Plus,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  Radar,
  RefreshCw,
  Rows3,
  Search,
  Server,
  Trash2,
  TriangleAlert,
  Workflow,
} from "lucide-react";
import { api } from "../api";
import type { CurrentUser, FlowRecord, Health, RunRecord, ScheduleDefinition, ScheduleRecord } from "../types";

type ScheduleFilter = "all" | "active" | "paused" | "error";
type BusyOperation = "save" | "toggle" | "trigger" | "delete";
type ScheduleView = "overview" | "plans" | "runs" | "exceptions";
type RunFilter = "all" | "active" | "succeeded" | "failed";
type ExceptionView = "schedules" | "runs";

interface ScheduleFormValues {
  flow_id: string;
  name: string;
  cron: string;
  timezone: string;
  enabled: boolean;
  parameters_text: string;
}

interface Props {
  schedules: ScheduleRecord[];
  flows: FlowRecord[];
  runs: RunRecord[];
  health?: Health;
  loading: boolean;
  currentUser: CurrentUser;
  onChanged: () => void;
  onRun: (run: RunRecord) => void;
  onToast: (kind: "success" | "error", message: string) => void;
}

const activeRunStatuses = new Set(["QUEUED", "RUNNING", "CANCELLING"]);

const runStatusLabel: Record<string, string> = {
  QUEUED: "排队中",
  RUNNING: "运行中",
  CANCELLING: "取消中",
  SUCCEEDED: "成功",
  FAILED: "失败",
  CANCELLED: "已取消",
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

function scheduleState(schedule: ScheduleRecord) {
  if (schedule.last_error) return { key: "error", label: "异常", color: "error" } as const;
  if (!schedule.enabled) return { key: "paused", label: "已暂停", color: "default" } as const;
  return { key: "active", label: "已启用", color: "success" } as const;
}

function canManageSchedule(user: CurrentUser, schedule: ScheduleRecord) {
  return user.role === "admin" || (user.role === "editor" && [schedule.owner_id, schedule.created_by].includes(user.id));
}

function canRunSchedule(user: CurrentUser, schedule: ScheduleRecord) {
  return user.role === "admin" || user.id === schedule.owner_id || (user.role === "editor" && schedule.visibility === "team");
}

function runDuration(run: RunRecord) {
  if (!run.started_at) return "--";
  const end = run.finished_at ? new Date(run.finished_at).getTime() : Date.now();
  const seconds = Math.max(0, Math.round((end - new Date(run.started_at).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function runTagColor(status: string) {
  if (status === "FAILED" || status === "CANCELLED") return "error";
  if (status === "SUCCEEDED") return "success";
  if (status === "QUEUED") return "warning";
  return "processing";
}

function initialDockState(key: string, fallback: boolean) {
  try {
    const stored = window.localStorage.getItem(key);
    return stored === null ? fallback : stored === "collapsed";
  } catch {
    return fallback;
  }
}

function ScheduleHorizon({ schedules, flowById, selectedId, onSelect }: { schedules: ScheduleRecord[]; flowById: Map<string, FlowRecord>; selectedId: string | null; onSelect: (id: string) => void }) {
  const now = Date.now();
  const start = now;
  const end = now + 24 * 60 * 60 * 1000;
  const entries = schedules
    .filter((schedule) => schedule.enabled && schedule.next_run_at)
    .map((schedule) => ({ schedule, time: new Date(schedule.next_run_at!).getTime() }))
    .filter(({ time }) => time >= start && time <= end)
    .sort((left, right) => left.time - right.time);
  const currentPosition = ((now - start) / (end - start)) * 100;
  const ticks = [0, 6, 12, 18, 24].map((offset) => ({
    offset,
    label: new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })
      .format(new Date(start + offset * 60 * 60 * 1000)),
  }));

  return (
    <section className="schedule-horizon" aria-label="未来 24 小时任务运行带">
      <header>
        <div><CalendarClock size={16} /><strong>未来 24 小时运行带</strong></div>
        <span>{entries.length} 个即将触发</span>
      </header>
      <div className="schedule-horizon__axis" aria-hidden="true">
        <span />
        {ticks.map((tick) => <time key={tick.offset} style={{ left: `${(tick.offset / 24) * 100}%` }}>{tick.label}</time>)}
      </div>
      {entries.length ? (
        <div className="schedule-horizon__lanes">
          <i className="schedule-horizon__now" style={{ left: `calc(124px + (100% - 124px) * ${currentPosition / 100})` }} aria-hidden="true" />
          {entries.map(({ schedule, time }) => {
            const position = ((time - start) / (end - start)) * 100;
            return (
              <div className="schedule-lane" key={schedule.id}>
                <span title={schedule.name}>{schedule.name}</span>
                <div>
                  <Tooltip title={`${flowById.get(schedule.flow_id)?.name ?? "未知流程"} · ${dateTime(schedule.next_run_at)}`}>
                    <button type="button" className={`schedule-fire ${schedule.id === selectedId ? "selected" : ""}`} style={{ left: `${position}%` }} aria-label={`${schedule.name} 将于 ${dateTime(schedule.next_run_at)} 触发`} aria-pressed={schedule.id === selectedId} onClick={() => onSelect(schedule.id)} />
                  </Tooltip>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未来 24 小时没有计划触发" />
      )}
    </section>
  );
}

export function TaskScheduleCenter({ schedules, flows, runs, health, loading, currentUser, onChanged, onRun, onToast }: Props) {
  const [view, setView] = useState<ScheduleView>("overview");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<ScheduleFilter>("all");
  const [runQuery, setRunQuery] = useState("");
  const [runFilter, setRunFilter] = useState<RunFilter>("all");
  const [exceptionView, setExceptionView] = useState<ExceptionView>("schedules");
  const [leftCollapsed, setLeftCollapsed] = useState(() => initialDockState("siftlane:schedule:left", false));
  const [rightCollapsed, setRightCollapsed] = useState(() => initialDockState("siftlane:schedule:right", window.innerWidth <= 1280));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<ScheduleRecord | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [busyOperation, setBusyOperation] = useState<BusyOperation | null>(null);
  const busyRef = useRef(false);
  const [form] = Form.useForm<ScheduleFormValues>();
  const flowById = useMemo(() => new Map(flows.map((flow) => [flow.id, flow])), [flows]);
  const runnableFlows = flows.filter((flow) => currentUser.role === "admin" || currentUser.id === flow.owner_id || (currentUser.role === "editor" && flow.visibility === "team"));
  const canCreate = currentUser.role !== "viewer" && runnableFlows.length > 0;

  const counts = useMemo(() => ({
    total: schedules.length,
    active: schedules.filter((schedule) => schedule.enabled && !schedule.last_error).length,
    paused: schedules.filter((schedule) => !schedule.enabled).length,
    error: schedules.filter((schedule) => Boolean(schedule.last_error)).length,
    running: runs.filter((run) => run.status === "RUNNING").length,
    queued: health?.queuedRuns ?? runs.filter((run) => run.status === "QUEUED").length,
  }), [health?.queuedRuns, runs, schedules]);

  const filtered = useMemo(() => schedules.filter((schedule) => {
    const state = scheduleState(schedule).key;
    const flowName = flowById.get(schedule.flow_id)?.name ?? "";
    const matchesQuery = `${schedule.name} ${flowName}`.toLowerCase().includes(query.trim().toLowerCase());
    return matchesQuery && (filter === "all" || state === filter);
  }), [filter, flowById, query, schedules]);

  const selectedSchedule = filtered.find((schedule) => schedule.id === selectedId) ?? filtered[0] ?? null;
  const liveRuns = runs.filter((run) => activeRunStatuses.has(run.status));
  const recentRuns = runs.slice(0, 12);
  const overviewRuns = (liveRuns.length ? liveRuns : recentRuns).slice(0, 5);
  const contextRuns = selectedSchedule ? runs.filter((run) => run.flow_id === selectedSchedule.flow_id).slice(0, 4) : [];
  const nextSchedules = filtered
    .filter((schedule) => schedule.enabled && schedule.next_run_at)
    .sort((left, right) => new Date(left.next_run_at!).getTime() - new Date(right.next_run_at!).getTime());
  const attentionSchedules = filtered.filter((schedule) => schedule.last_error || !schedule.enabled).slice(0, 5);
  const problemSchedules = schedules.filter((schedule) => Boolean(schedule.last_error));
  const failedRuns = runs.filter((run) => run.status === "FAILED");
  const filteredRuns = useMemo(() => runs.filter((run) => {
    const matchesQuery = `${run.flow_name} ${run.id} ${run.message ?? ""} ${run.error_message ?? ""}`.toLowerCase().includes(runQuery.trim().toLowerCase());
    const matchesFilter = runFilter === "all"
      || (runFilter === "active" && activeRunStatuses.has(run.status))
      || (runFilter === "succeeded" && run.status === "SUCCEEDED")
      || (runFilter === "failed" && ["FAILED", "CANCELLED"].includes(run.status));
    return matchesQuery && matchesFilter;
  }), [runFilter, runQuery, runs]);

  function toggleDock(side: "left" | "right") {
    if (side === "left") {
      setLeftCollapsed((current) => {
        const next = !current;
        window.localStorage.setItem("siftlane:schedule:left", next ? "collapsed" : "expanded");
        return next;
      });
      return;
    }
    setRightCollapsed((current) => {
      const next = !current;
      window.localStorage.setItem("siftlane:schedule:right", next ? "collapsed" : "expanded");
      return next;
    });
  }

  function openPlans(nextFilter: ScheduleFilter = "all") {
    setFilter(nextFilter);
    setView("plans");
  }

  function openRuns(nextFilter: RunFilter = "all") {
    setRunFilter(nextFilter);
    setView("runs");
  }

  function openCreate() {
    setEditing(null);
    form.setFieldsValue({
      flow_id: runnableFlows[0]?.id ?? "",
      name: "每日采集",
      cron: "0 8 * * *",
      timezone: "Asia/Shanghai",
      enabled: true,
      parameters_text: "{}",
    });
    setDrawerOpen(true);
  }

  function openEdit(schedule: ScheduleRecord) {
    setEditing(schedule);
    form.setFieldsValue({
      flow_id: schedule.flow_id,
      name: schedule.name,
      cron: schedule.cron,
      timezone: schedule.timezone,
      enabled: schedule.enabled,
      parameters_text: JSON.stringify(schedule.parameters, null, 2),
    });
    setDrawerOpen(true);
  }

  async function save(values: ScheduleFormValues) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusyId(editing?.id ?? "create");
    setBusyOperation("save");
    try {
      const definition: ScheduleDefinition = {
        flow_id: values.flow_id,
        name: values.name.trim(),
        cron: values.cron.trim(),
        timezone: values.timezone.trim(),
        enabled: values.enabled,
        parameters: JSON.parse(values.parameters_text || "{}") as Record<string, unknown>,
      };
      if (editing) await api.updateSchedule({ ...editing, ...definition });
      else await api.createSchedule(definition);
      setDrawerOpen(false);
      onChanged();
      onToast("success", editing ? "计划已更新" : "计划已创建");
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "保存计划失败");
    } finally {
      busyRef.current = false;
      setBusyId(null);
      setBusyOperation(null);
    }
  }

  async function toggle(schedule: ScheduleRecord) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusyId(schedule.id);
    setBusyOperation("toggle");
    try {
      await api.updateSchedule({ ...schedule, enabled: !schedule.enabled });
      onChanged();
      onToast("success", schedule.enabled ? "计划已暂停" : "计划已启用");
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "更新计划失败");
    } finally {
      busyRef.current = false;
      setBusyId(null);
      setBusyOperation(null);
    }
  }

  async function trigger(schedule: ScheduleRecord) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusyId(schedule.id);
    setBusyOperation("trigger");
    try {
      const run = await api.triggerSchedule(schedule.id);
      onChanged();
      onRun(run);
      onToast("success", "计划已触发");
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "触发计划失败");
    } finally {
      busyRef.current = false;
      setBusyId(null);
      setBusyOperation(null);
    }
  }

  async function remove(schedule: ScheduleRecord) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusyId(schedule.id);
    setBusyOperation("delete");
    try {
      await api.deleteSchedule(schedule.id);
      if (selectedId === schedule.id) setSelectedId(null);
      onChanged();
      onToast("success", "计划已删除");
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "删除计划失败");
    } finally {
      busyRef.current = false;
      setBusyId(null);
      setBusyOperation(null);
    }
  }

  const columns: TableProps<ScheduleRecord>["columns"] = [
    {
      title: "状态",
      key: "status",
      width: 88,
      render: (_, schedule) => {
        const state = scheduleState(schedule);
        return <Tag color={state.color}>{state.label}</Tag>;
      },
    },
    {
      title: "任务 / 流程",
      key: "task",
      width: 210,
      render: (_, schedule) => <div className="schedule-task-cell"><strong>{schedule.name}</strong><span>{flowById.get(schedule.flow_id)?.name ?? "流程不可用"}</span></div>,
    },
    {
      title: "调度表达式",
      key: "cron",
      width: 180,
      render: (_, schedule) => <div className="schedule-cron-cell"><code>{schedule.cron}</code><span>{schedule.timezone}</span></div>,
    },
    { title: "下次运行", dataIndex: "next_run_at", key: "next", width: 155, render: dateTime },
    { title: "最近运行", dataIndex: "last_run_at", key: "last", width: 155, render: dateTime },
    {
      title: "操作",
      key: "actions",
      fixed: "right",
      width: 138,
      render: (_, schedule) => {
        const manageable = canManageSchedule(currentUser, schedule);
        const runnable = canRunSchedule(currentUser, schedule);
        return (
          <Space size={2} onClick={(event) => event.stopPropagation()}>
            <Tooltip title={schedule.enabled ? "暂停" : "启用"}><Button type="text" size="small" loading={busyId === schedule.id && busyOperation === "toggle"} disabled={!manageable || busyId !== null} icon={schedule.enabled ? <CirclePause size={14} /> : <Play size={14} />} onClick={() => void toggle(schedule)} aria-label={schedule.enabled ? "暂停" : "启用"} /></Tooltip>
            <Tooltip title="立即运行"><Button type="text" size="small" loading={busyId === schedule.id && busyOperation === "trigger"} disabled={!runnable || busyId !== null} icon={<Play size={14} />} onClick={() => void trigger(schedule)} aria-label="立即运行" /></Tooltip>
            <Tooltip title="编辑"><Button type="text" size="small" disabled={!manageable || busyId !== null} icon={<Edit3 size={14} />} onClick={() => openEdit(schedule)} aria-label="编辑" /></Tooltip>
            <Popconfirm title="删除计划" description={`确定删除“${schedule.name}”吗？`} okText="删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={() => void remove(schedule)} disabled={!manageable}>
              <Button danger type="text" size="small" loading={busyId === schedule.id && busyOperation === "delete"} disabled={!manageable || busyId !== null} icon={<Trash2 size={14} />} aria-label="删除" />
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  const runColumns: TableProps<RunRecord>["columns"] = [
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 96,
      render: (status: string) => <Tag color={runTagColor(status)}>{runStatusLabel[status] ?? status}</Tag>,
    },
    {
      title: "流程 / 运行 ID",
      key: "run",
      width: 250,
      render: (_, run) => <div className="schedule-task-cell"><strong>{run.flow_name}</strong><span>{run.id}</span></div>,
    },
    { title: "创建时间", dataIndex: "created_at", key: "created", width: 170, render: dateTime },
    { title: "耗时", key: "duration", width: 100, render: (_, run) => <code>{runDuration(run)}</code> },
    { title: "结果", dataIndex: "processed_items", key: "items", width: 90 },
    {
      title: "当前活动 / 错误",
      key: "message",
      ellipsis: true,
      render: (_, run) => run.error_message ?? run.message ?? "--",
    },
    {
      title: "操作",
      key: "action",
      fixed: "right",
      width: 92,
      render: (_, run) => <Button type="link" size="small" icon={<ArrowRight size={13} />} onClick={(event) => { event.stopPropagation(); onRun(run); }}>查看</Button>,
    },
  ];

  const scheduleTable = (dataSource: ScheduleRecord[], pageSize = 12) => (
    <Table<ScheduleRecord>
      rowKey="id"
      size="small"
      loading={loading}
      columns={columns}
      dataSource={dataSource}
      pagination={{ pageSize, size: "small", showSizeChanger: false, hideOnSinglePage: true }}
      scroll={{ x: 920 }}
      rowClassName={(schedule) => schedule.id === selectedSchedule?.id ? "ant-table-row-selected" : ""}
      onRow={(schedule) => ({
        onClick: () => setSelectedId(schedule.id),
        onKeyDown: (event) => {
          if (event.target !== event.currentTarget) return;
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setSelectedId(schedule.id);
          }
        },
        tabIndex: 0,
        "aria-selected": schedule.id === selectedSchedule?.id,
      })}
      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的计划" /> }}
    />
  );

  const runTable = (dataSource: RunRecord[], pageSize = 14) => (
    <Table<RunRecord>
      rowKey="id"
      size="small"
      columns={runColumns}
      dataSource={dataSource}
      pagination={{ pageSize, size: "small", showSizeChanger: false, hideOnSinglePage: true }}
      scroll={{ x: 980 }}
      onRow={(run) => ({
        onClick: () => onRun(run),
        onKeyDown: (event) => {
          if (event.target !== event.currentTarget) return;
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onRun(run);
          }
        },
        tabIndex: 0,
      })}
      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的运行记录" /> }}
    />
  );

  return (
    <div className="schedule-center">
      <header className="schedule-center__header">
        <div className="schedule-center__heading"><h1>任务调度中心</h1><p>统一查看计划、未来触发和实时执行状态</p></div>
        <Tabs
          className="schedule-center__tabs"
          activeKey={view}
          onChange={(key) => setView(key as ScheduleView)}
          items={[
            { key: "overview", label: <span><Radar size={14} />调度态势</span> },
            { key: "plans", label: <span><Rows3 size={14} />计划管理</span> },
            { key: "runs", label: <span><Activity size={14} />执行记录</span> },
            { key: "exceptions", label: <span><TriangleAlert size={14} />异常中心</span> },
          ]}
        />
        <Space>
          <Button icon={<RefreshCw size={14} />} onClick={onChanged}>刷新</Button>
          <Button type="primary" icon={<Plus size={15} />} disabled={!canCreate || busyId !== null} onClick={openCreate}>新建计划</Button>
        </Space>
      </header>

      <section className="schedule-command-strip" aria-label="调度状态概览">
        <button type="button" className={counts.running ? "is-live" : ""} onClick={() => openRuns("active")}><Activity size={15} /><span>运行中</span><strong>{counts.running}</strong></button>
        <button type="button" className={counts.queued ? "is-warning" : ""} onClick={() => openRuns("active")}><Server size={15} /><span>队列</span><strong>{counts.queued}</strong></button>
        <button type="button" className={counts.error ? "is-alert" : ""} onClick={() => setView("exceptions")}><TriangleAlert size={15} /><span>异常</span><strong>{counts.error}</strong></button>
        <button type="button" onClick={() => openPlans("active")}><Play size={15} /><span>已启用</span><strong>{counts.active}</strong></button>
        <button type="button" onClick={() => openPlans("paused")}><CirclePause size={15} /><span>已暂停</span><strong>{counts.paused}</strong></button>
        <button type="button" onClick={() => openPlans("all")}><CalendarClock size={15} /><span>全部计划</span><strong>{counts.total}</strong></button>
      </section>

      {view === "overview" ? (
        <div className={`schedule-operations-grid ${leftCollapsed ? "is-left-collapsed" : ""} ${rightCollapsed ? "is-right-collapsed" : ""}`}>
          <aside className={`schedule-roster ${leftCollapsed ? "is-collapsed" : ""}`} aria-label="计划图层">
            <header>
              {!leftCollapsed && <div><ListFilter size={15} /><strong>计划图层</strong><span>{filtered.length}</span></div>}
              <Tooltip title={leftCollapsed ? "展开计划图层" : "收起计划图层"}>
                <Button type="text" size="small" icon={leftCollapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />} aria-label={leftCollapsed ? "展开计划图层" : "收起计划图层"} aria-expanded={!leftCollapsed} aria-controls="schedule-roster-content" onClick={() => toggleDock("left")} />
              </Tooltip>
            </header>
            <div id="schedule-roster-content" className="schedule-dock-content" hidden={leftCollapsed}>
              <Input prefix={<Search size={14} />} value={query} onChange={(event) => setQuery(event.target.value)} allowClear placeholder="搜索计划或流程" aria-label="搜索计划或流程" />
              <Segmented<ScheduleFilter>
                block
                size="small"
                value={filter}
                onChange={setFilter}
                options={[
                  { label: "全部", value: "all" },
                  { label: "启用", value: "active" },
                  { label: "暂停", value: "paused" },
                  { label: "异常", value: "error" },
                ]}
              />
              <div className="schedule-roster__section-title"><span>即将触发</span><Clock3 size={13} /></div>
              <div className="schedule-roster__list">
                {nextSchedules.slice(0, 6).map((schedule) => (
                  <button key={schedule.id} className={selectedSchedule?.id === schedule.id ? "selected" : ""} onClick={() => setSelectedId(schedule.id)}>
                    <i className={schedule.last_error ? "error" : ""} />
                    <span><strong>{schedule.name}</strong><small>{flowById.get(schedule.flow_id)?.name ?? "流程不可用"}</small></span>
                    <time>{dateTime(schedule.next_run_at)}</time>
                  </button>
                ))}
                {!nextSchedules.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有即将触发的计划" />}
              </div>
              <Button className="schedule-dock-link" type="text" icon={<ArrowRight size={13} />} iconPosition="end" onClick={() => openPlans(filter)}>查看全部计划 · {filtered.length}</Button>
            </div>
            {leftCollapsed && <div className="schedule-collapsed-dock"><ListFilter size={15} /><span>计划图层</span><b>{filtered.length}</b></div>}
          </aside>

          <main className="schedule-situation-field">
            <ScheduleHorizon schedules={filtered} flowById={flowById} selectedId={selectedSchedule?.id ?? null} onSelect={setSelectedId} />
            <div className="schedule-signal-deck">
              <section className="schedule-signal-panel">
                <header><div><TriangleAlert size={15} /><strong>计划风险</strong></div><span>{attentionSchedules.length}</span></header>
                <div className="schedule-signal-list">
                  {attentionSchedules.map((schedule) => (
                    <button key={schedule.id} onClick={() => setSelectedId(schedule.id)}>
                      <i className={schedule.last_error ? "error" : "paused"} />
                      <span><strong>{schedule.name}</strong><small>{schedule.last_error ?? "计划已暂停"}</small></span>
                      <Tag color={scheduleState(schedule).color}>{scheduleState(schedule).label}</Tag>
                    </button>
                  ))}
                  {!attentionSchedules.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前没有计划风险" />}
                </div>
                <Button type="text" icon={<ArrowRight size={13} />} iconPosition="end" onClick={() => setView("exceptions")}>进入异常中心</Button>
              </section>
              <section className="schedule-signal-panel">
                <header><div><Activity size={15} /><strong>执行脉冲</strong></div><span className={liveRuns.length ? "live" : ""}>{liveRuns.length ? `${liveRuns.length} 实时` : "最近运行"}</span></header>
                <div className="schedule-signal-list">
                  {overviewRuns.map((run) => (
                    <button key={run.id} onClick={() => onRun(run)}>
                      <i className={`run-${run.status.toLowerCase()}`} />
                      <span><strong>{run.flow_name}</strong><small>{run.message ?? run.error_message ?? run.id.slice(0, 12)}</small></span>
                      <time>{dateTime(run.created_at)}</time>
                    </button>
                  ))}
                  {!overviewRuns.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有执行信号" />}
                </div>
                <Button type="text" icon={<ArrowRight size={13} />} iconPosition="end" onClick={() => openRuns("all")}>查看全部执行</Button>
              </section>
            </div>
          </main>

          <aside className={`schedule-intelligence ${rightCollapsed ? "is-collapsed" : ""}`} aria-label="任务情报">
            <header>
              <Tooltip title={rightCollapsed ? "展开任务情报" : "收起任务情报"}>
                <Button type="text" size="small" icon={rightCollapsed ? <PanelRightOpen size={15} /> : <PanelRightClose size={15} />} aria-label={rightCollapsed ? "展开任务情报" : "收起任务情报"} aria-expanded={!rightCollapsed} aria-controls="schedule-intelligence-content" onClick={() => toggleDock("right")} />
              </Tooltip>
              {!rightCollapsed && <div><Workflow size={15} /><strong>任务情报</strong></div>}
            </header>
            <div id="schedule-intelligence-content" className="schedule-dock-content" hidden={rightCollapsed}>
              <section className="schedule-selected">
                {selectedSchedule ? (
                  <>
                    <div className="schedule-selected__title"><div><strong>{selectedSchedule.name}</strong><span>{flowById.get(selectedSchedule.flow_id)?.name ?? "流程不可用"}</span></div><Tag color={scheduleState(selectedSchedule).color}>{scheduleState(selectedSchedule).label}</Tag></div>
                    <dl>
                      <div><dt>下次运行</dt><dd>{dateTime(selectedSchedule.next_run_at)}</dd></div>
                      <div><dt>最近运行</dt><dd>{dateTime(selectedSchedule.last_run_at)}</dd></div>
                      <div><dt>时区</dt><dd>{selectedSchedule.timezone}</dd></div>
                      <div><dt>Cron</dt><dd><code>{selectedSchedule.cron}</code></dd></div>
                    </dl>
                    {selectedSchedule.last_error && <div className="schedule-selected__error" role="alert"><TriangleAlert size={14} /><span>{selectedSchedule.last_error}</span></div>}
                    <Space wrap>
                      <Button size="small" icon={<Edit3 size={13} />} disabled={!canManageSchedule(currentUser, selectedSchedule) || busyId !== null} onClick={() => openEdit(selectedSchedule)}>编辑</Button>
                      <Button size="small" type="primary" icon={<Play size={13} />} disabled={!canRunSchedule(currentUser, selectedSchedule) || busyId !== null} loading={busyId === selectedSchedule.id && busyOperation === "trigger"} onClick={() => void trigger(selectedSchedule)}>立即运行</Button>
                    </Space>
                  </>
                ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择一个计划" />}
              </section>
              <section className="schedule-live-ledger">
                <header><div><Activity size={15} /><strong>关联运行</strong></div><span>{contextRuns.length}</span></header>
                <div>
                  {contextRuns.map((run) => (
                    <button key={run.id} onClick={() => onRun(run)}>
                      <i className={`run-${run.status.toLowerCase()}`} />
                      <span><strong>{run.flow_name}</strong><small>{run.message ?? run.error_message ?? run.id.slice(0, 12)}</small></span>
                      <span><Tag color={runTagColor(run.status)}>{runStatusLabel[run.status] ?? run.status}</Tag><time>{dateTime(run.created_at)}</time></span>
                      <ChevronRight size={13} />
                    </button>
                  ))}
                  {!contextRuns.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有关联运行" />}
                </div>
                <Button className="schedule-dock-link" type="text" icon={<ArrowRight size={13} />} iconPosition="end" onClick={() => openRuns("all")}>查看全部执行</Button>
              </section>
            </div>
            {rightCollapsed && <div className="schedule-collapsed-dock"><Workflow size={15} /><span>任务情报</span><b>{contextRuns.length}</b></div>}
          </aside>
        </div>
      ) : view === "plans" ? (
        <section className="schedule-data-view schedule-plans-view">
          <header className="schedule-data-toolbar">
            <div><Rows3 size={17} /><span><strong>计划管理</strong><small>{filtered.length} / {schedules.length} 个计划</small></span></div>
            <Space>
              <Input prefix={<Search size={14} />} value={query} onChange={(event) => setQuery(event.target.value)} allowClear placeholder="搜索计划或流程" aria-label="搜索计划或流程" />
              <Segmented<ScheduleFilter> value={filter} onChange={setFilter} options={[{ label: "全部", value: "all" }, { label: "启用", value: "active" }, { label: "暂停", value: "paused" }, { label: "异常", value: "error" }]} />
            </Space>
          </header>
          <div className="schedule-table-panel schedule-data-table">{scheduleTable(filtered)}</div>
        </section>
      ) : view === "runs" ? (
        <section className="schedule-data-view schedule-runs-view">
          <header className="schedule-data-toolbar">
            <div><Activity size={17} /><span><strong>执行记录</strong><small>{filteredRuns.length} / {runs.length} 次运行</small></span></div>
            <Space>
              <Input prefix={<Search size={14} />} value={runQuery} onChange={(event) => setRunQuery(event.target.value)} allowClear placeholder="搜索流程、运行 ID 或活动" aria-label="搜索执行记录" />
              <Segmented<RunFilter> value={runFilter} onChange={setRunFilter} options={[{ label: "全部", value: "all" }, { label: "活动", value: "active" }, { label: "成功", value: "succeeded" }, { label: "失败", value: "failed" }]} />
            </Space>
          </header>
          <div className="schedule-data-table schedule-run-table">{runTable(filteredRuns)}</div>
        </section>
      ) : (
        <section className="schedule-data-view schedule-exceptions-view">
          <header className="schedule-data-toolbar">
            <div><TriangleAlert size={17} /><span><strong>异常中心</strong><small>{problemSchedules.length} 个异常计划 · {failedRuns.length} 次失败运行</small></span></div>
            <Segmented<ExceptionView> value={exceptionView} onChange={setExceptionView} options={[{ label: `异常计划 ${problemSchedules.length}`, value: "schedules" }, { label: `失败运行 ${failedRuns.length}`, value: "runs" }]} />
          </header>
          <div className="schedule-data-table">{exceptionView === "schedules" ? scheduleTable(problemSchedules) : runTable(failedRuns)}</div>
        </section>
      )}

      <Drawer
        className="schedule-form-drawer"
        title={editing ? "编辑调度计划" : "新建调度计划"}
        width={480}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnHidden
        extra={<Button type="primary" loading={busyId === (editing?.id ?? "create") && busyOperation === "save"} onClick={() => form.submit()}>{editing ? "保存修改" : "创建计划"}</Button>}
      >
        <Form form={form} layout="vertical" requiredMark={false} onFinish={(values) => void save(values)}>
          <Form.Item label="计划名称" name="name" rules={[{ required: true, message: "请输入计划名称" }]}><Input maxLength={160} /></Form.Item>
          <Form.Item label="关联流程" name="flow_id" rules={[{ required: true, message: "请选择流程" }]}>
            <Select showSearch optionFilterProp="label" options={runnableFlows.map((flow) => ({ label: flow.name, value: flow.id }))} />
          </Form.Item>
          <div className="schedule-form-grid">
            <Form.Item label="Cron 表达式" name="cron" rules={[{ required: true, message: "请输入 Cron 表达式" }]}><Input placeholder="0 8 * * *" /></Form.Item>
            <Form.Item label="IANA 时区" name="timezone" rules={[{ required: true, message: "请输入时区" }]}><Input placeholder="Asia/Shanghai" /></Form.Item>
          </div>
          <Form.Item
            label="运行参数 JSON"
            name="parameters_text"
            rules={[{
              validator: async (_, value) => {
                try {
                  const parsed = JSON.parse(value || "{}");
                  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error();
                } catch {
                  throw new Error("运行参数必须是有效的 JSON 对象");
                }
              },
            }]}
          >
            <Input.TextArea className="schedule-json-input" rows={10} spellCheck={false} />
          </Form.Item>
          <Form.Item label="启用计划" name="enabled" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
