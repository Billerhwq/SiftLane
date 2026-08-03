import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addEdge,
  applyEdgeChanges,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  useNodesState,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from "@xyflow/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Menu as AntMenu } from "antd";
import {
  Activity,
  AlertCircle,
  Bell,
  Braces,
  CalendarClock,
  Check,
  ChevronRight,
  CircleHelp,
  CodeXml,
  Database,
  Download,
  GitBranch,
  Globe2,
  ListFilter,
  ListPlus,
  LockKeyhole,
  LogOut,
  PanelRight,
  PanelRightClose,
  PanelRightOpen,
  Play,
  Plug,
  Plus,
  RefreshCw,
  Repeat2,
  Save,
  Settings2,
  Users,
  Workflow,
  X,
} from "lucide-react";
import { API_BASE, api, streamRunEvents } from "./api";
import { Dialog } from "./components/Dialog";
import { EventDock } from "./components/EventDock";
import { FlowNodeCard, type FlowNodeData, type NodeExecutionState } from "./components/FlowNodeCard";
import { FlowLibrary } from "./components/FlowLibrary";
import { ImportWorkspace } from "./components/ImportWorkspace";
import { IntegrationDrawer } from "./components/IntegrationDrawer";
import { ItemDetailPanel } from "./components/ItemDetailPanel";
import { NodeInspector } from "./components/NodeInspector";
import { TaskScheduleCenter } from "./components/TaskScheduleCenter";
import { TeamDrawer } from "./components/TeamDrawer";
import { useMediaQuery, useModalFocus } from "./hooks/useModalFocus";
import type {
  FlowDefinition,
  FlowEdgeRecord,
  FlowNodeRecord,
  FlowRecord,
  ItemRecord,
  NodeCapability,
  NodeType,
  RunEvent,
  RunRecord,
} from "./types";

const nodeTypes = { siftlane: FlowNodeCard };
type ViewTab = "library" | "imports" | "editor" | "runs" | "results" | "schedules";

const typeIcons: Record<NodeType, typeof Globe2> = {
  start: ChevronRight,
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

const statusLabel: Record<string, string> = {
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

function duration(run: RunRecord) {
  if (!run.started_at) return "--";
  const end = run.finished_at ? new Date(run.finished_at).getTime() : Date.now();
  return `${Math.max(0, (end - new Date(run.started_at).getTime()) / 1000).toFixed(1)}s`;
}

function newFlow(name: string): FlowDefinition {
  return {
    name,
    description: "",
    enabled: true,
    visibility: "team",
    max_items: 100,
    timeout_seconds: 300,
    parameter_schema: { type: "object", additionalProperties: true },
    nodes: [
      { id: "start", type: "start", name: "输入地址", x: 80, y: 220, config: { urls: ["https://example.com"] } },
      { id: "request", type: "http_request", name: "获取页面", x: 330, y: 220, config: { url: "{{url}}", respect_robots: true } },
      { id: "extract", type: "html_extract", name: "提取内容", x: 580, y: 220, config: { item_selector: "body", fields: { title: "h1", content: "p" } } },
      { id: "emit", type: "emit", name: "输出结果", x: 830, y: 220, config: {} },
    ],
    edges: [
      { id: "edge-start-request", source: "start", target: "request" },
      { id: "edge-request-extract", source: "request", target: "extract" },
      { id: "edge-extract-emit", source: "extract", target: "emit" },
    ],
  };
}

function defaultRetry() {
  return {
    max_attempts: 1,
    backoff_seconds: 0.25,
    max_backoff_seconds: 10,
    retryable_statuses: [408, 429, 500, 502, 503, 504],
    retryable_errors: ["TimeoutError", "ConnectionError", "HTTPStatusError"],
  };
}

function defaultConfig(type: NodeType): Record<string, unknown> {
  if (type === "start") return { urls: ["https://example.com"] };
  if (type === "http_request") return { url: "{{url}}", respect_robots: true };
  if (type === "html_extract") return { item_selector: "article", fields: { title: "h2", content: "p" } };
  if (type === "json_extract") return { items_path: "data.items", fields: { title: "title", url: "url" } };
  if (type === "condition") return { field: "status", operator: "eq", value: "published" };
  if (type === "loop") return { items_path: "items", item_name: "item", index_name: "item_index", max_iterations: 100 };
  if (type === "pagination") return { url: "{{url}}", page_parameter: "page", start_page: 1, max_pages: 10 };
  if (type === "transform") return { mapping: { title: "{{title}}" } };
  return {};
}

function mergeEvents(previous: RunEvent[], incoming: RunEvent[]) {
  const merged = new Map(previous.map((event) => [event.sequence, event]));
  incoming.forEach((event) => merged.set(event.sequence, event));
  return [...merged.values()].sort((a, b) => a.sequence - b.sequence);
}

export function App() {
  const queryClient = useQueryClient();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 3_000 });
  const currentUser = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false });
  const authenticated = currentUser.isSuccess;
  const capabilities = useQuery({ queryKey: ["capabilities"], queryFn: api.capabilities, enabled: authenticated });
  const schedules = useQuery({ queryKey: ["schedules"], queryFn: api.schedules, refetchInterval: 10_000, enabled: authenticated });
  const flows = useQuery({ queryKey: ["flows"], queryFn: api.flows, enabled: authenticated });
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs, refetchInterval: 1_500, enabled: authenticated });

  const [selectedFlowId, setSelectedFlowId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [draft, setDraft] = useState<FlowRecord | null>(null);
  const [graphNodes, setGraphNodes, applyGraphNodeChanges] = useNodesState<Node<FlowNodeData>>([]);
  const [dirty, setDirty] = useState(false);
  const [tab, setTab] = useState<ViewTab>("library");
  const [search, setSearch] = useState("");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [streamState, setStreamState] = useState<"idle" | "connecting" | "connected" | "disconnected">("idle");
  const [eventsExpanded, setEventsExpanded] = useState(false);
  const [newDialog, setNewDialog] = useState(false);
  const [newName, setNewName] = useState("网页采集流程");
  const [nodeLibrary, setNodeLibrary] = useState(false);
  const [connectorsOpen, setConnectorsOpen] = useState(false);
  const [teamOpen, setTeamOpen] = useState(false);
  const [mobileInspector, setMobileInspector] = useState(false);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(() => window.localStorage.getItem("siftlane:workflow:inspector") === "collapsed");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ kind: "success" | "error"; message: string } | null>(null);
  const isNarrow = useMediaQuery("(max-width: 900px)");
  const compactNav = useMediaQuery("(max-width: 1280px)");
  const inspectorRef = useModalFocus<HTMLDivElement>(isNarrow && mobileInspector, () => setMobileInspector(false));
  const connectorRef = useModalFocus<HTMLElement>(connectorsOpen, () => setConnectorsOpen(false));
  const teamRef = useModalFocus<HTMLDivElement>(teamOpen, () => setTeamOpen(false));

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4_000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (currentUser.data?.auth_mode !== "team") return;
    const timer = window.setInterval(() => {
      void api.refreshSession().catch(() => {
        window.location.reload();
      });
    }, 5 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, [currentUser.data?.auth_mode]);

  useEffect(() => {
    if (!selectedFlowId && flows.data?.length) setSelectedFlowId(flows.data[0].id);
  }, [flows.data, selectedFlowId]);

  const selectedFlow = flows.data?.find((flow) => flow.id === selectedFlowId);
  useEffect(() => {
    if (!selectedFlow) {
      setDraft(null);
      return;
    }
    setDraft(structuredClone(selectedFlow));
    setDirty(false);
    setSelectedNodeId(null);
  }, [selectedFlow]);

  const flowRuns = useMemo(
    () => (runs.data ?? []).filter((run) => run.flow_id === selectedFlowId),
    [runs.data, selectedFlowId],
  );

  useEffect(() => {
    if (!flowRuns.length) {
      setSelectedRunId(null);
      return;
    }
    if (!flowRuns.some((run) => run.id === selectedRunId)) setSelectedRunId(flowRuns[0].id);
  }, [flowRuns, selectedRunId]);

  const selectedRun = flowRuns.find((run) => run.id === selectedRunId);

  useEffect(() => {
    setSelectedItemId(null);
  }, [selectedRunId]);

  useEffect(() => {
    if (!selectedRunId) {
      setEvents([]);
      setStreamState("idle");
      return;
    }
    const controller = new AbortController();
    let active = true;
    (async () => {
      try {
        const initial = await api.events(selectedRunId);
        if (!active) return;
        setEvents(initial);
        const runIsActive = selectedRun && ["QUEUED", "RUNNING", "CANCELLING"].includes(selectedRun.status);
        if (!runIsActive) {
          setStreamState("idle");
          return;
        }
        let after = initial.at(-1)?.sequence ?? 0;
        while (active && !controller.signal.aborted) {
          try {
            setStreamState("connecting");
            await streamRunEvents(selectedRunId, after, controller.signal, (event) => {
              after = Math.max(after, event.sequence);
              setEvents((current) => mergeEvents(current, [event]));
              void queryClient.invalidateQueries({ queryKey: ["runs"] });
              if (event.type === "item.emitted" || event.type === "run.completed") {
                void queryClient.invalidateQueries({ queryKey: ["items", selectedRunId] });
              }
            }, () => setStreamState("connected"));
            setStreamState("idle");
            break;
          } catch (error) {
            if (controller.signal.aborted) break;
            setStreamState("disconnected");
            setToast({ kind: "error", message: error instanceof Error ? `${error.message}，正在重连` : "事件流已断开，正在重连" });
            await new Promise((resolve) => window.setTimeout(resolve, 1_200));
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) setToast({ kind: "error", message: error instanceof Error ? error.message : "事件流连接失败" });
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, [queryClient, selectedRun?.status, selectedRunId]);

  const items = useQuery({
    queryKey: ["items", selectedRunId],
    queryFn: () => api.items(selectedRunId!),
    enabled: Boolean(selectedRunId) && tab === "results",
    refetchInterval: selectedRun && ["QUEUED", "RUNNING", "CANCELLING"].includes(selectedRun.status) ? 1_000 : false,
  });

  useEffect(() => {
    if (selectedRun?.status === "SUCCEEDED") {
      void queryClient.invalidateQueries({ queryKey: ["items", selectedRun.id] });
    }
  }, [queryClient, selectedRun?.id, selectedRun?.status]);

  const executionStates = useMemo(() => {
    const states = new Map<string, NodeExecutionState>();
    for (const event of events) {
      const nodeId = typeof event.data.nodeId === "string" ? event.data.nodeId : null;
      if (!nodeId) continue;
      if (event.type === "node.started") states.set(nodeId, "running");
      if (event.type === "node.completed") states.set(nodeId, "completed");
      if (event.type === "node.restored") states.set(nodeId, "completed");
    }
    if (selectedRun?.status === "FAILED" && selectedRun.current_node) states.set(selectedRun.current_node, "failed");
    return states;
  }, [events, selectedRun]);

  useEffect(() => {
    const records = draft?.nodes ?? [];
    setGraphNodes((current) => {
      const currentById = new Map(current.map((node) => [node.id, node]));
      let changed = current.length !== records.length;
      const next = records.map((record) => {
        const existing = currentById.get(record.id);
        const executionState = executionStates.get(record.id) ?? "idle";
        const selected = record.id === selectedNodeId;
        if (!existing) {
          changed = true;
          return {
            id: record.id,
            type: "siftlane",
            position: { x: record.x, y: record.y },
            selected,
            data: { record, executionState },
          };
        }

        const positionChanged = existing.position.x !== record.x || existing.position.y !== record.y;
        const dataChanged = existing.data.record !== record || existing.data.executionState !== executionState;
        if (!positionChanged && !dataChanged && existing.selected === selected) return existing;
        changed = true;
        return {
          ...existing,
          position: positionChanged ? { x: record.x, y: record.y } : existing.position,
          selected,
          data: dataChanged ? { record, executionState } : existing.data,
        };
      });
      return changed ? next : current;
    });
  }, [draft?.nodes, executionStates, selectedNodeId, setGraphNodes]);

  const graphEdges = useMemo<Edge[]>(() => (draft?.edges ?? []).map((edge) => ({
    ...edge,
    sourceHandle: edge.source_port ?? "default",
    type: "smoothstep",
    animated: executionStates.get(edge.source) === "completed" && executionStates.get(edge.target) === "running",
    className: executionStates.get(edge.source) === "completed" ? "edge-completed" : "",
  })), [draft?.edges, executionStates]);

  const updateDraft = useCallback((updater: (value: FlowRecord) => FlowRecord) => {
    setDraft((current) => current ? updater(current) : current);
    setDirty(true);
  }, []);

  const onNodesChange = useCallback((changes: NodeChange<Node<FlowNodeData>>[]) => {
    applyGraphNodeChanges(changes);
    const removedIds = new Set(changes.filter((change) => change.type === "remove").map((change) => change.id));
    if (!removedIds.size) return;
    updateDraft((flow) => ({
      ...flow,
      nodes: flow.nodes.filter((node) => !removedIds.has(node.id)),
      edges: flow.edges.filter((edge) => !removedIds.has(edge.source) && !removedIds.has(edge.target)),
    }));
    setSelectedNodeId((current) => current && removedIds.has(current) ? null : current);
  }, [applyGraphNodeChanges, updateDraft]);

  const onNodeDragStop = useCallback((_: MouseEvent | TouchEvent, node: Node<FlowNodeData>) => {
    updateDraft((flow) => ({
      ...flow,
      nodes: flow.nodes.map((record) => record.id === node.id
        ? { ...record, x: node.position.x, y: node.position.y }
        : record),
    }));
  }, [updateDraft]);

  const onEdgesChange = useCallback((changes: EdgeChange<Edge>[]) => {
    const persisted = changes.filter((change) => change.type === "remove");
    if (!persisted.length) return;
    const next = applyEdgeChanges(persisted, graphEdges);
    updateDraft((flow) => ({ ...flow, edges: next.map(({ id, source, target, sourceHandle }) => ({ id, source, target, source_port: sourceHandle ?? "default" })) }));
  }, [graphEdges, updateDraft]);

  const onConnect = useCallback((connection: Connection) => {
    if (!connection.source || !connection.target || connection.source === connection.target) return;
    const sourcePort = connection.sourceHandle ?? "default";
    const exists = graphEdges.some((edge) => edge.source === connection.source && edge.target === connection.target && (edge.sourceHandle ?? "default") === sourcePort);
    if (exists) return;
    const next = addEdge({ ...connection, id: `edge-${connection.source}-${sourcePort}-${connection.target}` }, graphEdges);
    updateDraft((flow) => ({ ...flow, edges: next.map(({ id, source, target, sourceHandle }) => ({ id, source, target, source_port: sourceHandle ?? "default" })) }));
  }, [graphEdges, updateDraft]);

  const selectedNode = draft?.nodes.find((node) => node.id === selectedNodeId);
  const selectedCapability = capabilities.data?.nodeTypes.find((capability) => capability.type === selectedNode?.type);

  function chooseFlow(id: string) {
    if (dirty && !window.confirm("当前修改尚未保存，确定切换流程吗？")) return false;
    setSelectedFlowId(id);
    setTab("editor");
    return true;
  }

  function setInspectorDrawerCollapsed(collapsed: boolean) {
    window.localStorage.setItem("siftlane:workflow:inspector", collapsed ? "collapsed" : "expanded");
    setInspectorCollapsed(collapsed);
  }

  async function createFlow() {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      const created = await api.createFlow(newFlow(newName.trim()));
      queryClient.setQueryData<FlowRecord[]>(["flows"], (current = []) => [created, ...current]);
      setSelectedFlowId(created.id);
      setNewDialog(false);
      setNewName("网页采集流程");
      setToast({ kind: "success", message: "流程已创建" });
    } catch (error) {
      setToast({ kind: "error", message: error instanceof Error ? error.message : "创建失败" });
    } finally {
      setBusy(false);
    }
  }

  async function saveFlow(showToast = true): Promise<FlowRecord | null> {
    if (!draft) return null;
    setBusy(true);
    try {
      const saved = await api.updateFlow(draft);
      queryClient.setQueryData<FlowRecord[]>((["flows"]), (current = []) => current.map((flow) => flow.id === saved.id ? saved : flow));
      setDraft(saved);
      setDirty(false);
      if (showToast) setToast({ kind: "success", message: `已保存版本 ${saved.revision}` });
      return saved;
    } catch (error) {
      setToast({ kind: "error", message: error instanceof Error ? error.message : "保存失败" });
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function runFlow() {
    let flow = draft;
    if (!flow) return;
    if (dirty) flow = await saveFlow(false);
    if (!flow) return;
    setBusy(true);
    try {
      const run = await api.createRun(flow.id);
      setSelectedRunId(run.id);
      setEvents([]);
      queryClient.setQueryData<RunRecord[]>(["runs"], (current = []) => [run, ...current]);
      setToast({ kind: "success", message: "运行已进入队列" });
    } catch (error) {
      setToast({ kind: "error", message: error instanceof Error ? error.message : "运行失败" });
    } finally {
      setBusy(false);
    }
  }

  async function cancelRun() {
    if (!selectedRunId) return;
    try {
      await api.cancelRun(selectedRunId);
      await queryClient.invalidateQueries({ queryKey: ["runs"] });
    } catch (error) {
      setToast({ kind: "error", message: error instanceof Error ? error.message : "取消失败" });
    }
  }

  async function deleteFlow() {
    if (!draft || !window.confirm(`确定删除“${draft.name}”吗？`)) return;
    try {
      await api.deleteFlow(draft.id);
      queryClient.setQueryData<FlowRecord[]>(["flows"], (current = []) => current.filter((flow) => flow.id !== draft.id));
      setSelectedFlowId(null);
      setDraft(null);
      setToast({ kind: "success", message: "流程已删除" });
    } catch (error) {
      setToast({ kind: "error", message: error instanceof Error ? error.message : "删除失败" });
    }
  }

  function addNode(capability: NodeCapability) {
    if (!draft) return;
    if (capability.type === "start" && draft.nodes.some((node) => node.type === "start")) {
      setToast({ kind: "error", message: "一个流程只能有一个开始节点" });
      return;
    }
    const id = `${capability.type}-${crypto.randomUUID().slice(0, 6)}`;
    const node: FlowNodeRecord = {
      id,
      type: capability.type,
      name: capability.label,
      x: 140 + draft.nodes.length * 36,
      y: 160 + draft.nodes.length * 24,
      config: defaultConfig(capability.type),
      retry: defaultRetry(),
    };
    updateDraft((flow) => ({ ...flow, nodes: [...flow.nodes, node] }));
    setSelectedNodeId(id);
    setNodeLibrary(false);
    setInspectorDrawerCollapsed(false);
    setMobileInspector(true);
  }

  function removeNode() {
    if (!draft || !selectedNode) return;
    updateDraft((flow) => ({
      ...flow,
      nodes: flow.nodes.filter((node) => node.id !== selectedNode.id),
      edges: flow.edges.filter((edge) => edge.source !== selectedNode.id && edge.target !== selectedNode.id),
    }));
    setSelectedNodeId(null);
  }

  const filteredFlows = (flows.data ?? []).filter((flow) => flow.name.toLowerCase().includes(search.toLowerCase()));
  const error = health.error || capabilities.error || flows.error || runs.error || schedules.error;
  const canCreateFlow = currentUser.data?.role !== "viewer";
  const canManageFlow = Boolean(draft && currentUser.data && (currentUser.data.role === "admin" || currentUser.data.id === draft.owner_id));
  const canRunFlow = Boolean(draft && currentUser.data && (
    currentUser.data.role === "admin"
    || currentUser.data.id === draft.owner_id
    || (currentUser.data.role === "editor" && draft.visibility === "team")
  ));

  if (currentUser.isLoading) {
    return <div className="auth-screen"><div className="auth-loading"><i /><strong>正在验证工作区</strong></div></div>;
  }
  if (currentUser.isError || !currentUser.data) {
    return <LoginScreen engineOnline={!health.isError} />;
  }

  return (
    <main className={`app-shell ${selectedItemId ? "detail-mode" : ""} ${tab === "library" ? "library-mode" : ""} ${tab === "schedules" ? "schedule-mode" : ""} ${inspectorCollapsed ? "inspector-collapsed" : ""}`}>
      <header className="topbar">
        <div className="brand"><span><ChevronRight size={19} /></span><div><strong>Siftlane</strong><small>采集工作室</small></div></div>
        <div className="breadcrumb"><b>SiftLane</b><ChevronRight size={13} /><span>{tab === "schedules" ? "任务调度中心" : tab === "library" ? "流程库" : draft?.name ?? "本地工作区"}</span></div>
        <div className="topbar__actions">
          <a className="icon-button" href={`${API_BASE}/docs`} target="_blank" rel="noreferrer" title="API 帮助" aria-label="打开 API 帮助"><CircleHelp size={18} /></a>
          <button className="icon-button" onClick={() => setEventsExpanded(true)} title="运行事件" aria-label="展开运行事件"><Bell size={18} /></button>
          <button className="icon-button" onClick={() => void Promise.all([health.refetch(), flows.refetch(), runs.refetch()])} title="刷新状态" aria-label="刷新状态"><RefreshCw size={16} /></button>
          <button className="button primary" disabled={!canCreateFlow} onClick={() => setTab("imports")}><Globe2 size={16} />导入网站</button>
          <span className="user-chip"><span className="user-avatar" aria-hidden="true">{currentUser.data.display_name.slice(0, 1).toUpperCase()}</span><span><strong>{currentUser.data.display_name}</strong><small>{currentUser.data.role}</small></span></span>
          {currentUser.data.auth_mode === "team" && <button className="icon-button" onClick={() => void api.logout().then(() => window.location.reload())} title="退出登录" aria-label="退出登录"><LogOut size={16} /></button>}
          <button className="mobile-only icon-button" onClick={() => { setInspectorDrawerCollapsed(false); setMobileInspector(true); }} aria-label="打开设置"><PanelRight size={18} /></button>
        </div>
      </header>

      <section className="status-strip">
        <div className="engine-status"><i className={health.isError ? "down" : ""} /><span><strong>{health.isError ? "执行引擎离线" : "执行引擎在线"}</strong><code>PY {health.data?.version ?? "--"} / {health.data?.workers ?? 0} WORKERS / {capabilities.data?.nodeTypes.length ?? 0} NODES</code></span></div>
        <div className="status-stat"><span>已保存流程</span><b>{String(flows.data?.length ?? 0).padStart(2, "0")}</b></div>
        <div className="status-stat"><span>最近运行</span><b>{String(runs.data?.length ?? 0).padStart(2, "0")}</b></div>
        <div className="current-activity"><Activity size={17} /><span><strong>{selectedRun?.message ?? (draft ? `${draft.name} · 等待操作` : "选择或创建流程")}</strong><code>{selectedRun ? `${selectedRun.status} / ${selectedRun.processed_items} ITEMS` : `${capabilities.data?.connectorCount ?? 0} CONNECTORS / PROTOCOL ${capabilities.data?.protocolVersion ?? "--"}`}</code></span></div>
      </section>

      {error && <div className="global-error"><AlertCircle size={16} /><span>无法连接执行引擎：{error instanceof Error ? error.message : "未知错误"}</span><button onClick={() => window.location.reload()}>重新连接</button></div>}

      <nav className="utility-rail" aria-label="主功能">
        <AntMenu
          mode="inline"
          inlineCollapsed={compactNav}
          selectedKeys={[tab === "library" ? "editor" : tab]}
          onClick={({ key }) => {
            if (["editor", "imports", "runs", "results", "schedules"].includes(key)) {
              setTab(key === "editor" ? "library" : key as ViewTab);
              setSelectedItemId(null);
              return;
            }
            if (key === "connectors") setConnectorsOpen(true);
            if (key === "team") setTeamOpen(true);
          }}
          items={[
            { key: "editor", icon: <Workflow size={18} />, label: "流程编排" },
            { key: "imports", icon: <Globe2 size={18} />, label: "导入网站" },
            { key: "runs", icon: <Activity size={18} />, label: "运行记录" },
            { key: "results", icon: <Database size={18} />, label: "采集结果" },
            { key: "schedules", icon: <CalendarClock size={18} />, label: "任务调度" },
            { type: "divider" },
            { key: "connectors", icon: <Plug size={18} />, label: "连接器" },
            ...(currentUser.data.role === "admin" ? [{ key: "team", icon: <Users size={18} />, label: "团队与安全" }] : []),
          ]}
        />
        <AntMenu
          mode="inline"
          inlineCollapsed={compactNav}
          selectable={false}
          onClick={() => { setSelectedNodeId(null); setInspectorDrawerCollapsed(false); setMobileInspector(true); }}
          items={[{ key: "settings", icon: <Settings2 size={18} />, label: "工作区设置" }]}
        />
      </nav>

      <section className="workspace">
        <header className="workspace-bar">
          <nav aria-label="工作区视图">
            <button className={tab === "library" ? "selected" : ""} onClick={() => { setTab("library"); setSelectedItemId(null); }}>流程库</button>
            <button className={tab === "imports" ? "selected" : ""} onClick={() => { setTab("imports"); setSelectedItemId(null); }}>导入网站</button>
            <button className={tab === "editor" ? "selected" : ""} onClick={() => { setTab("editor"); setSelectedItemId(null); }}>编排</button>
            <button className={tab === "runs" ? "selected" : ""} onClick={() => { setTab("runs"); setSelectedItemId(null); }}>运行记录</button>
            <button className={tab === "results" ? "selected" : ""} onClick={() => { setTab("results"); setSelectedItemId(null); }}>结果</button>
          </nav>
          {tab === "editor" && <div className="workspace-bar__actions">
            <div className="node-library-wrap">
              <button className="button" disabled={!draft || tab !== "editor" || !canManageFlow} onClick={() => setNodeLibrary(!nodeLibrary)}><Plus size={14} />添加节点</button>
              {nodeLibrary && (
                <div className="node-library">
                  <header><strong>节点库</strong><button className="icon-button" onClick={() => setNodeLibrary(false)} aria-label="关闭"><X size={14} /></button></header>
                  {capabilities.data?.nodeTypes.map((capability) => {
                    const Icon = typeIcons[capability.type];
                    return <button key={capability.type} onClick={() => addNode(capability)}><i><Icon size={15} /></i><span><strong>{capability.label}</strong><small>{capability.description}</small></span></button>;
                  })}
                </div>
              )}
            </div>
            <button className="button" disabled={!dirty || busy || !canManageFlow} onClick={() => void saveFlow()}><Save size={14} />保存</button>
            <button className="button primary" disabled={!draft || busy || !canRunFlow} onClick={() => void runFlow()}><Play size={14} fill="currentColor" />运行</button>
          </div>}
        </header>

        {tab === "schedules" ? (
          <TaskScheduleCenter
            schedules={schedules.data ?? []}
            flows={flows.data ?? []}
            runs={runs.data ?? []}
            health={health.data}
            loading={schedules.isLoading}
            currentUser={currentUser.data}
            onChanged={() => { void schedules.refetch(); void runs.refetch(); }}
            onRun={(run) => {
              setSelectedFlowId(run.flow_id);
              setSelectedRunId(run.id);
              setTab("runs");
              queryClient.setQueryData<RunRecord[]>(["runs"], (current = []) => [run, ...current.filter((item) => item.id !== run.id)]);
            }}
            onToast={(kind, message) => setToast({ kind, message })}
          />
        ) : tab === "imports" ? (
          <ImportWorkspace onCreated={() => { void flows.refetch(); }} />
        ) : tab === "library" ? (
          <FlowLibrary
            flows={filteredFlows}
            runs={runs.data ?? []}
            loading={flows.isLoading}
            query={search}
            selectedFlowId={selectedFlowId}
            onQueryChange={setSearch}
            onOpen={chooseFlow}
            onOpenRun={(run) => {
              if (!chooseFlow(run.flow_id)) return;
              setSelectedRunId(run.id);
              setTab("runs");
            }}
          />
        ) : !draft ? (
          <div className="workspace-empty">
            <div className="workspace-empty-visual" aria-hidden="true"><i /><i /><i /><span /><span /></div>
            <h1>还没有流程</h1><p>创建第一个流程后，采集链路会显示在这里。</p><button className="button primary" onClick={() => setNewDialog(true)}><Plus size={15} />新建流程</button>
          </div>
        ) : tab === "editor" ? (
          <div className="graph-stage">
            <div className="graph-title"><h1>{draft.name}</h1><p>版本 {draft.revision} · {dirty ? "有未保存修改" : `保存于 ${dateTime(draft.updated_at)}`}</p></div>
            <ReactFlow
              nodes={graphNodes}
              edges={graphEdges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onNodeDragStop={onNodeDragStop}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={(_, node) => { setSelectedNodeId(node.id); setInspectorDrawerCollapsed(false); setMobileInspector(true); }}
              onPaneClick={() => setSelectedNodeId(null)}
              deleteKeyCode={null}
              fitView
              minZoom={0.5}
              maxZoom={1.6}
              fitViewOptions={{ padding: 0.25, minZoom: isNarrow ? 0.8 : 0.5 }}
              proOptions={{ hideAttribution: true }}
            >
              <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#c7d9ec" />
              <Controls showInteractive={false} />
              <MiniMap pannable zoomable nodeColor={(node) => node.selected ? "#0052d9" : "#b9cee8"} maskColor="rgba(242,247,252,.72)" />
            </ReactFlow>
          </div>
        ) : tab === "runs" ? (
          <RunTable runs={flowRuns} selectedRunId={selectedRunId} onSelect={setSelectedRunId} />
        ) : (
          <ResultWorkspace
            run={selectedRun}
            loading={items.isLoading}
            items={items.data?.items ?? []}
            error={items.error}
            selectedItemId={selectedItemId}
            onSelectItem={setSelectedItemId}
          />
        )}

        {tab !== "schedules" && tab !== "library" && <EventDock run={selectedRun} events={events} expanded={eventsExpanded} onExpandedChange={setEventsExpanded} onCancel={() => void cancelRun()} streamState={streamState} />}
      </section>

      {tab !== "library" && tab !== "schedules" && (
        <div id="workflow-inspector-content" ref={inspectorRef} className={`inspector-wrap ${inspectorCollapsed ? "is-collapsed" : ""} ${mobileInspector ? "mobile-open" : ""}`} inert={isNarrow && !mobileInspector ? true : undefined} aria-hidden={isNarrow && !mobileInspector ? true : undefined}>
          <button
            className="inspector-drawer-toggle icon-button"
            onClick={() => setInspectorDrawerCollapsed(!inspectorCollapsed)}
            aria-label={inspectorCollapsed ? `展开${selectedNode ? "节点设置" : "流程设置"}` : `收起${selectedNode ? "节点设置" : "流程设置"}`}
            aria-expanded={!inspectorCollapsed}
            aria-controls="workflow-inspector-content"
            title={inspectorCollapsed ? "展开设置" : "收起设置"}
          >
            {inspectorCollapsed ? <PanelRightOpen size={16} /> : <PanelRightClose size={16} />}
          </button>
          {inspectorCollapsed ? (
            <div className="inspector-collapsed-summary"><Settings2 size={16} /><span>{selectedNode ? "节点设置" : "流程设置"}</span><b>{draft ? `R${draft.revision}` : "--"}</b></div>
          ) : (
            <>
              <button className="mobile-only inspector-close icon-button" onClick={() => setMobileInspector(false)} aria-label="关闭设置"><X size={16} /></button>
              {selectedNode && draft ? (
                <NodeInspector
                  node={selectedNode}
                  capability={selectedCapability}
                  readOnly={!canManageFlow}
                  onChange={(node) => canManageFlow && updateDraft((flow) => ({ ...flow, nodes: flow.nodes.map((item) => item.id === node.id ? node : item) }))}
                  onDelete={() => canManageFlow && removeNode()}
                />
              ) : draft ? (
                <FlowInspector flow={draft} run={selectedRun} readOnly={!canManageFlow} onChange={(flow) => { setDraft(flow); setDirty(true); }} onDelete={() => void deleteFlow()} />
              ) : <aside className="inspector blank"><Settings2 size={24} /><p>选择流程或节点后查看设置</p></aside>}
            </>
          )}
        </div>
      )}

      {connectorsOpen && (
        <div ref={(element) => { connectorRef.current = element; }} className="side-drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setConnectorsOpen(false)}>
          <IntegrationDrawer currentUser={currentUser.data} onClose={() => setConnectorsOpen(false)} onToast={(kind, message) => setToast({ kind, message })} />
        </div>
      )}

      {teamOpen && (
        <div ref={teamRef} className="side-drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setTeamOpen(false)}>
          <TeamDrawer currentUser={currentUser.data} onClose={() => setTeamOpen(false)} onToast={(kind, message) => setToast({ kind, message })} />
        </div>
      )}

      <Dialog open={newDialog} title="新建流程" submitLabel="创建流程" busy={busy} onClose={() => setNewDialog(false)} onSubmit={() => void createFlow()}>
        <label className="field"><span>流程名称</span><input autoFocus value={newName} onChange={(event) => setNewName(event.target.value)} maxLength={160} /></label>
        <p className="dialog-note">新流程包含开始、HTTP、HTML 提取和输出四个可编辑节点。</p>
      </Dialog>

      {toast && <div className={`toast ${toast.kind}`} role="status">{toast.kind === "success" ? <Check size={15} /> : <AlertCircle size={15} />}<span>{toast.message}</span><button onClick={() => setToast(null)} aria-label="关闭"><X size={14} /></button></div>}
      {mobileInspector && <div className="mobile-scrim inspector-scrim" onClick={() => setMobileInspector(false)} />}
    </main>
  );
}

function LoginScreen({ engineOnline }: { engineOnline: boolean }) {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const session = await api.login(username, password);
      queryClient.setQueryData(["me"], session.user);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-screen">
      <form className="login-panel" onSubmit={(event) => void submit(event)}>
        <header><span><ChevronRight size={20} /></span><div><strong>Siftlane</strong><small>团队工作区</small></div></header>
        <div className="login-title"><LockKeyhole size={22} /><div><h1>登录</h1><p>使用工作区账号继续。</p></div></div>
        <label className="field"><span>用户名</span><input autoFocus autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required /></label>
        <label className="field"><span>密码</span><input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
        {message && <div className="login-error" role="alert"><AlertCircle size={15} />{message}</div>}
        <button className="button primary login-submit" disabled={busy || !engineOnline}>{busy ? "正在验证" : engineOnline ? "登录" : "引擎离线"}</button>
        <footer><i className={engineOnline ? "" : "down"} />{engineOnline ? "执行引擎在线" : "无法连接执行引擎"}</footer>
      </form>
    </main>
  );
}

function FlowInspector({ flow, run, readOnly, onChange, onDelete }: { flow: FlowRecord; run?: RunRecord; readOnly: boolean; onChange: (flow: FlowRecord) => void; onDelete: () => void }) {
  return (
    <aside className="inspector">
      <header className="inspector__header"><strong>流程设置</strong><span>REV {flow.revision}</span></header>
      <section className="inspector__section">
        <div className="section-heading"><strong>基本信息</strong><span>{flow.enabled ? "已启用" : "已暂停"}</span></div>
        <label className="field"><span>流程名称</span><input disabled={readOnly} value={flow.name} onChange={(event) => onChange({ ...flow, name: event.target.value })} /></label>
        <label className="field"><span>描述</span><textarea disabled={readOnly} value={flow.description} onChange={(event) => onChange({ ...flow, description: event.target.value })} /></label>
        <label className="field"><span>可见范围</span><select disabled={readOnly} value={flow.visibility} onChange={(event) => onChange({ ...flow, visibility: event.target.value as "private" | "team" })}><option value="private">仅所有者</option><option value="team">团队可见</option></select></label>
        <label className="switch-field"><span>允许运行</span><input disabled={readOnly} type="checkbox" checked={flow.enabled} onChange={(event) => onChange({ ...flow, enabled: event.target.checked })} /><i /></label>
      </section>
      <section className="inspector__section">
        <div className="section-heading"><strong>运行策略</strong></div>
        <div className="field-grid">
          <label className="field"><span>最大结果</span><input disabled={readOnly} type="number" min={1} max={10000} value={flow.max_items} onChange={(event) => onChange({ ...flow, max_items: Number(event.target.value) })} /></label>
          <label className="field"><span>超时（秒）</span><input disabled={readOnly} type="number" min={5} max={3600} value={flow.timeout_seconds} onChange={(event) => onChange({ ...flow, timeout_seconds: Number(event.target.value) })} /></label>
        </div>
      </section>
      <section className="inspector__section run-summary">
        <div className="section-heading"><strong>最近运行</strong>{run && <span className={`status-${run.status.toLowerCase()}`}>{statusLabel[run.status]}</span>}</div>
        {run ? <dl><div><dt>开始</dt><dd>{dateTime(run.started_at)}</dd></div><div><dt>结果</dt><dd>{run.processed_items} 项</dd></div><div><dt>耗时</dt><dd>{duration(run)}</dd></div></dl> : <p className="quiet-empty">还没有运行记录</p>}
      </section>
      <button className="danger-button" type="button" disabled={readOnly} onClick={onDelete}>删除流程</button>
    </aside>
  );
}

function RunTable({ runs, selectedRunId, onSelect }: { runs: RunRecord[]; selectedRunId: string | null; onSelect: (id: string) => void }) {
  if (!runs.length) return <div className="view-empty"><Activity size={30} /><h2>还没有运行记录</h2><p>从编排视图启动流程后，记录会显示在这里。</p></div>;
  return (
    <div className="data-view">
      <header><div><h1>运行记录</h1><p>{runs.length} 次运行</p></div></header>
      <div className="table-wrap"><table><thead><tr><th>状态</th><th>运行 ID</th><th>流程版本</th><th>开始时间</th><th>耗时</th><th>结果</th><th>当前活动</th></tr></thead><tbody>{runs.map((run) => (
        <tr
          key={run.id}
          className={run.id === selectedRunId ? "selected" : ""}
          onClick={() => onSelect(run.id)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onSelect(run.id);
            }
          }}
          role="button"
          tabIndex={0}
          aria-selected={run.id === selectedRunId}
        >
          <td><span className={`status-badge status-${run.status.toLowerCase()}`}>{statusLabel[run.status]}</span></td>
          <td><code>{run.id.slice(0, 12)}</code></td><td>REV {run.flow_revision}</td><td>{dateTime(run.started_at ?? run.created_at)}</td><td>{duration(run)}</td><td>{run.processed_items}</td><td>{run.error_message ?? run.message ?? "--"}</td>
        </tr>
      ))}</tbody></table></div>
    </div>
  );
}

function ResultWorkspace({ run, loading, items, error, selectedItemId, onSelectItem }: { run?: RunRecord; loading: boolean; items: ItemRecord[]; error: Error | null; selectedItemId: string | null; onSelectItem: (id: string | null) => void }) {
  const returnFocusId = useRef<string | null>(null);
  const selectedIndex = items.findIndex((item) => item.id === selectedItemId);

  useEffect(() => {
    if (selectedItemId || !returnFocusId.current) return;
    const rowId = `result-row-${returnFocusId.current}`;
    window.requestAnimationFrame(() => document.getElementById(rowId)?.focus());
  }, [selectedItemId]);

  function selectItem(id: string | null) {
    if (id) returnFocusId.current = id;
    onSelectItem(id);
  }

  if (selectedIndex >= 0) {
    return (
      <ItemDetailPanel
        item={items[selectedIndex]}
        index={selectedIndex}
        total={items.length}
        onBack={() => selectItem(null)}
        onPrevious={selectedIndex > 0 ? () => selectItem(items[selectedIndex - 1].id) : undefined}
        onNext={selectedIndex < items.length - 1 ? () => selectItem(items[selectedIndex + 1].id) : undefined}
      />
    );
  }
  if (!run) return <div className="view-empty"><Download size={30} /><h2>还没有可查看的结果</h2><p>选择一次运行后查看结构化输出。</p></div>;
  return (
    <div className="data-view">
      <header><div><h1>采集结果</h1><p>{run.id.slice(0, 12)} · {run.processed_items} 项</p></div></header>
      {error ? <div className="inline-error"><AlertCircle size={16} />{error.message}</div> : loading ? <div className="data-loading">正在读取结果</div> : items.length ? (
        <div className="table-wrap"><table><thead><tr><th>标题</th><th>来源 URL</th><th>类型</th><th>观察时间</th><th>外部 ID</th></tr></thead><tbody>{items.map((item) => (
          <tr
            key={item.id}
            id={`result-row-${item.id}`}
            className="result-row"
            onClick={() => selectItem(item.id)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                selectItem(item.id);
              }
            }}
            role="button"
            tabIndex={0}
            aria-label={`查看详情：${item.title}`}
          >
            <td><strong>{item.title}</strong><small>{item.content.slice(0, 100)}</small></td><td><a href={item.url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>{item.url}</a></td><td>{item.media_type}</td><td>{dateTime(item.observed_at)}</td><td><code>{item.external_id.slice(0, 12)}</code></td>
          </tr>
        ))}</tbody></table></div>
      ) : <div className="view-empty embedded"><Download size={28} /><h2>本次运行没有输出结果</h2><p>{run.error_message ?? statusLabel[run.status]}</p></div>}
    </div>
  );
}
