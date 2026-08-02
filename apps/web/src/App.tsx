import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
} from "@xyflow/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
  Menu,
  PanelRight,
  Play,
  Plug,
  Plus,
  RefreshCw,
  Repeat2,
  Save,
  Search,
  Settings2,
  ShieldCheck,
  Users,
  Workflow,
  X,
} from "lucide-react";
import { API_BASE, api, streamRunEvents } from "./api";
import { Dialog } from "./components/Dialog";
import { EventDock } from "./components/EventDock";
import { FlowNodeCard, type FlowNodeData, type NodeExecutionState } from "./components/FlowNodeCard";
import { IntegrationDrawer } from "./components/IntegrationDrawer";
import { ItemDetailPanel } from "./components/ItemDetailPanel";
import { NodeInspector } from "./components/NodeInspector";
import { ScheduleDrawer } from "./components/ScheduleDrawer";
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
type ViewTab = "editor" | "runs" | "results";

const typeIcons: Record<NodeType, typeof Globe2> = {
  start: ChevronRight,
  http_request: Globe2,
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
  const [dirty, setDirty] = useState(false);
  const [tab, setTab] = useState<ViewTab>("editor");
  const [search, setSearch] = useState("");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [streamState, setStreamState] = useState<"idle" | "connecting" | "connected" | "disconnected">("idle");
  const [eventsExpanded, setEventsExpanded] = useState(false);
  const [newDialog, setNewDialog] = useState(false);
  const [newName, setNewName] = useState("网页采集流程");
  const [nodeLibrary, setNodeLibrary] = useState(false);
  const [connectorsOpen, setConnectorsOpen] = useState(false);
  const [schedulesOpen, setSchedulesOpen] = useState(false);
  const [teamOpen, setTeamOpen] = useState(false);
  const [mobileRail, setMobileRail] = useState(false);
  const [mobileInspector, setMobileInspector] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ kind: "success" | "error"; message: string } | null>(null);
  const isNarrow = useMediaQuery("(max-width: 900px)");
  const flowRailRef = useModalFocus<HTMLElement>(isNarrow && mobileRail, () => setMobileRail(false));
  const inspectorRef = useModalFocus<HTMLDivElement>(isNarrow && mobileInspector, () => setMobileInspector(false));
  const connectorRef = useModalFocus<HTMLElement>(connectorsOpen, () => setConnectorsOpen(false));
  const scheduleRef = useModalFocus<HTMLDivElement>(schedulesOpen, () => setSchedulesOpen(false));
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

  const graphNodes = useMemo<Node<FlowNodeData>[]>(() => (draft?.nodes ?? []).map((node) => ({
    id: node.id,
    type: "siftlane",
    position: { x: node.x, y: node.y },
    selected: node.id === selectedNodeId,
    data: { record: node, executionState: executionStates.get(node.id) ?? "idle" },
  })), [draft?.nodes, executionStates, selectedNodeId]);

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
    const persisted = changes.filter((change) => change.type === "position" || change.type === "remove");
    if (!persisted.length) return;
    const next = applyNodeChanges(persisted, graphNodes);
    updateDraft((flow) => ({
      ...flow,
      nodes: flow.nodes.filter((node) => next.some((candidate) => candidate.id === node.id)).map((node) => {
        const graph = next.find((candidate) => candidate.id === node.id);
        return graph ? { ...node, x: graph.position.x, y: graph.position.y } : node;
      }),
    }));
  }, [graphNodes, updateDraft]);

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
    if (dirty && !window.confirm("当前修改尚未保存，确定切换流程吗？")) return;
    setSelectedFlowId(id);
    setMobileRail(false);
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
  const error = health.error || capabilities.error || flows.error || runs.error;
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
    <main className={`app-shell ${selectedItemId ? "detail-mode" : ""}`}>
      <header className="topbar">
        <button className="mobile-only icon-button" onClick={() => setMobileRail(true)} aria-label="打开流程列表"><Menu size={18} /></button>
        <div className="brand"><span><ChevronRight size={19} /></span><div><strong>Siftlane</strong><small>采集工作室</small></div></div>
        <div className="breadcrumb"><b>Studio</b><ChevronRight size={13} /><span>{draft?.name ?? "本地工作区"}</span></div>
        <div className="topbar__actions">
          <a className="icon-button" href={`${API_BASE}/docs`} target="_blank" rel="noreferrer" title="API 帮助" aria-label="打开 API 帮助"><CircleHelp size={18} /></a>
          <button className="icon-button" onClick={() => setEventsExpanded(true)} title="运行事件" aria-label="展开运行事件"><Bell size={18} /></button>
          <button className="icon-button" onClick={() => void Promise.all([health.refetch(), flows.refetch(), runs.refetch()])} title="刷新状态" aria-label="刷新状态"><RefreshCw size={16} /></button>
          <button className="button primary" disabled={!canCreateFlow} onClick={() => setNewDialog(true)}><Plus size={16} />新建流程</button>
          <span className="user-chip"><span className="user-avatar" aria-hidden="true">{currentUser.data.display_name.slice(0, 1).toUpperCase()}</span><span><strong>{currentUser.data.display_name}</strong><small>{currentUser.data.role}</small></span></span>
          {currentUser.data.auth_mode === "team" && <button className="icon-button" onClick={() => void api.logout().then(() => window.location.reload())} title="退出登录" aria-label="退出登录"><LogOut size={16} /></button>}
          <button className="mobile-only icon-button" onClick={() => setMobileInspector(true)} aria-label="打开设置"><PanelRight size={18} /></button>
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
        <div className="utility-rail__main">
          <button className={tab === "editor" ? "selected" : ""} onClick={() => { setTab("editor"); setSelectedItemId(null); }} title="流程编排" aria-label="流程编排" aria-current={tab === "editor" ? "page" : undefined}><Workflow size={19} /></button>
          <button className={tab === "runs" ? "selected" : ""} onClick={() => { setTab("runs"); setSelectedItemId(null); }} title="运行记录" aria-label="查看运行记录" aria-current={tab === "runs" ? "page" : undefined}><Activity size={19} /></button>
          <button className={tab === "results" ? "selected" : ""} onClick={() => { setTab("results"); setSelectedItemId(null); }} title="采集结果" aria-label="查看采集结果" aria-current={tab === "results" ? "page" : undefined}><Database size={19} /></button>
          <span />
          <button onClick={() => setSchedulesOpen(true)} title="调度" aria-label="打开调度"><CalendarClock size={18} /></button>
          <button onClick={() => setConnectorsOpen(true)} title="连接器" aria-label="打开连接器"><Plug size={18} /></button>
          {currentUser.data.role === "admin" && <button onClick={() => setTeamOpen(true)} title="团队与安全" aria-label="打开团队与安全"><Users size={18} /></button>}
        </div>
        <button onClick={() => { setSelectedNodeId(null); setMobileInspector(true); }} title="工作区设置" aria-label="打开工作区设置"><Settings2 size={18} /></button>
      </nav>

      <aside ref={flowRailRef} className={`flow-rail ${mobileRail ? "mobile-open" : ""}`} inert={isNarrow && !mobileRail ? true : undefined} aria-hidden={isNarrow && !mobileRail ? true : undefined}>
        <header><strong>流程</strong><button className="icon-button mobile-only" onClick={() => setMobileRail(false)} aria-label="关闭流程列表"><X size={16} /></button></header>
        <label className="search-box"><Search size={14} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索流程" /></label>
        <span className="rail-label">已保存</span>
        <div className="flow-list">
          {flows.isLoading && <div className="rail-loading"><i /><i /><i /></div>}
          {filteredFlows.map((flow) => (
            <button key={flow.id} className={`flow-list__item ${flow.id === selectedFlowId ? "selected" : ""}`} onClick={() => chooseFlow(flow.id)}>
              <strong>{flow.name}</strong>
              <code>{flow.id.slice(0, 12)} · REV {String(flow.revision).padStart(2, "0")}</code>
              <span><em>{flow.nodes.length} 个节点</em><b className={flow.enabled ? "enabled" : "paused"}>{flow.enabled ? "已启用" : "已暂停"}</b></span>
            </button>
          ))}
          {!flows.isLoading && !filteredFlows.length && <div className="rail-empty">没有匹配的流程</div>}
        </div>
        <span className="rail-label recent-label">最近运行</span>
        <div className="recent-runs">
          {(runs.data ?? []).slice(0, 4).map((run) => (
            <button key={run.id} onClick={() => { chooseFlow(run.flow_id); setSelectedRunId(run.id); setTab("runs"); }}>
              <Check size={14} className={`run-${run.status.toLowerCase()}`} />
              <span><strong>{run.flow_name}</strong><small>{dateTime(run.created_at)} · {run.processed_items} 项</small></span>
              <code>{duration(run)}</code>
            </button>
          ))}
        </div>
        <div className="security-note"><ShieldCheck size={15} /><span><strong>安全策略已启用</strong><small>SSRF · robots · rate limit · response size</small></span></div>
      </aside>

      <section className="workspace">
        <header className="workspace-bar">
          <nav aria-label="工作区视图">
            <button className={tab === "editor" ? "selected" : ""} onClick={() => { setTab("editor"); setSelectedItemId(null); }}>编排</button>
            <button className={tab === "runs" ? "selected" : ""} onClick={() => { setTab("runs"); setSelectedItemId(null); }}>运行记录</button>
            <button className={tab === "results" ? "selected" : ""} onClick={() => { setTab("results"); setSelectedItemId(null); }}>结果</button>
          </nav>
          <div className="workspace-bar__actions">
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
          </div>
        </header>

        {!draft ? (
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
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={(_, node) => { setSelectedNodeId(node.id); setMobileInspector(true); }}
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

        <EventDock run={selectedRun} events={events} expanded={eventsExpanded} onExpandedChange={setEventsExpanded} onCancel={() => void cancelRun()} streamState={streamState} />
      </section>

      <div ref={inspectorRef} className={`inspector-wrap ${mobileInspector ? "mobile-open" : ""}`} inert={isNarrow && !mobileInspector ? true : undefined} aria-hidden={isNarrow && !mobileInspector ? true : undefined}>
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
      </div>

      {schedulesOpen && (
        <div ref={scheduleRef} className="side-drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setSchedulesOpen(false)}>
          <ScheduleDrawer
            schedules={schedules.data ?? []}
            flows={flows.data ?? []}
            loading={schedules.isLoading}
            onClose={() => setSchedulesOpen(false)}
            onChanged={() => { void schedules.refetch(); void runs.refetch(); }}
            onRun={(run) => {
              setSelectedFlowId(run.flow_id);
              setSelectedRunId(run.id);
              setTab("runs");
              queryClient.setQueryData<RunRecord[]>(["runs"], (current = []) => [run, ...current.filter((item) => item.id !== run.id)]);
            }}
            onToast={(kind, message) => setToast({ kind, message })}
            currentUser={currentUser.data}
          />
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
      {mobileRail && <div className="mobile-scrim" onClick={() => setMobileRail(false)} />}
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
