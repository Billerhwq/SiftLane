import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Check, KeyRound, PackagePlus, Plug, RefreshCw, RotateCcw, Send, Trash2, X } from "lucide-react";
import { api } from "../api";
import type {
  CurrentUser,
  DeliveryAuthScheme,
  DeliveryTargetRecord,
  DeliveryTargetType,
  ManagedConnectorRecord,
  SecretScope,
} from "../types";

type Toast = (kind: "success" | "error", message: string) => void;

export function IntegrationDrawer({ currentUser, onClose, onToast }: { currentUser: CurrentUser; onClose: () => void; onToast: Toast }) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"connectors" | "secrets" | "delivery">("connectors");
  const [busy, setBusy] = useState(false);
  const [filename, setFilename] = useState("");
  const [sha256, setSha256] = useState("");
  const [upgradeId, setUpgradeId] = useState("");
  const [secretName, setSecretName] = useState("");
  const [secretValue, setSecretValue] = useState("");
  const [scopeType, setScopeType] = useState<SecretScope>("connector");
  const [scopeId, setScopeId] = useState("");
  const [targetName, setTargetName] = useState("");
  const [targetType, setTargetType] = useState<DeliveryTargetType>("ndjson");
  const [targetUrl, setTargetUrl] = useState("");
  const [deliveryTarget, setDeliveryTarget] = useState("");
  const [deliveryRun, setDeliveryRun] = useState("");

  const connectors = useQuery({ queryKey: ["managed-connectors"], queryFn: api.managedConnectors });
  const secrets = useQuery({ queryKey: ["secrets"], queryFn: api.secrets, enabled: currentUser.role === "admin" });
  const targets = useQuery({ queryKey: ["delivery-targets"], queryFn: api.deliveryTargets });
  const deliveries = useQuery({ queryKey: ["deliveries"], queryFn: api.deliveries, refetchInterval: 3_000 });
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["managed-connectors"] }),
      queryClient.invalidateQueries({ queryKey: ["secrets"] }),
      queryClient.invalidateQueries({ queryKey: ["delivery-targets"] }),
      queryClient.invalidateQueries({ queryKey: ["deliveries"] }),
    ]);
  }

  async function act(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    try {
      await action();
      await refresh();
      onToast("success", success);
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function install() {
    await act(
      () => upgradeId ? api.upgradeConnector(upgradeId, filename, sha256) : api.installConnector(filename, sha256),
      upgradeId ? "连接器已升级" : "连接器已安装",
    );
    setFilename("");
    setSha256("");
    setUpgradeId("");
  }

  async function createSecret() {
    await act(() => api.createSecret({ name: secretName, scope_type: scopeType, scope_id: scopeId, value: secretValue }), "密钥已加密保存");
    setSecretName("");
    setSecretValue("");
  }

  async function createTarget() {
    await act(() => api.createDeliveryTarget({
      name: targetName,
      type: targetType,
      visibility: "team",
      enabled: true,
      url: targetType === "webhook" ? targetUrl : null,
      auth_scheme: "none",
      secret_id: null,
      max_attempts: 3,
      backoff_seconds: 1,
    }), "交付目标已创建");
    setTargetName("");
    setTargetUrl("");
  }

  async function deliver() {
    await act(() => api.createDelivery(deliveryTarget, deliveryRun, crypto.randomUUID()), "交付请求已处理");
  }

  const scopeOptions = scopeType === "connector"
    ? (connectors.data ?? []).map((item) => ({ id: item.id, label: item.manifest.name }))
    : (targets.data ?? []).map((item) => ({ id: item.id, label: item.name }));

  return (
    <aside className="side-drawer integration-drawer" role="dialog" aria-modal="true" aria-label="连接器与交付">
      <header><div><Plug size={17} /><strong>连接器与交付</strong></div><button className="icon-button" onClick={onClose} aria-label="关闭"><X size={16} /></button></header>
      <nav className="drawer-tabs integration-tabs" aria-label="集成视图">
        <button className={tab === "connectors" ? "selected" : ""} onClick={() => setTab("connectors")}><Plug size={14} />连接器</button>
        <button className={tab === "secrets" ? "selected" : ""} onClick={() => setTab("secrets")}><KeyRound size={14} />密钥</button>
        <button className={tab === "delivery" ? "selected" : ""} onClick={() => setTab("delivery")}><Send size={14} />交付</button>
      </nav>

      {tab === "connectors" && <div className="drawer-body">
        {currentUser.role === "admin" && <form className="integration-form" onSubmit={(event) => { event.preventDefault(); void install(); }}>
          <div className="field-grid"><label className="field"><span>Inbox wheel 文件名</span><input value={filename} onChange={(event) => setFilename(event.target.value)} required /></label><label className="field"><span>升级现有连接器</span><select value={upgradeId} onChange={(event) => setUpgradeId(event.target.value)}><option value="">新安装</option>{(connectors.data ?? []).map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}</select></label></div>
          <label className="field"><span>SHA-256</span><input value={sha256} onChange={(event) => setSha256(event.target.value.toLowerCase())} pattern="[a-fA-F0-9]{64}" required /></label>
          <button className="button primary integration-submit" disabled={busy}><PackagePlus size={14} />{upgradeId ? "验证并升级" : "验证并安装"}</button>
        </form>}
        <div className="integration-list">{(connectors.data ?? []).map((connector) => <ConnectorRow key={connector.id} connector={connector} admin={currentUser.role === "admin"} busy={busy} act={act} />)}</div>
      </div>}

      {tab === "secrets" && <div className="drawer-body">
        {currentUser.role === "admin" ? <>
          <form className="integration-form" onSubmit={(event) => { event.preventDefault(); void createSecret(); }}>
            <div className="field-grid"><label className="field"><span>作用域</span><select value={scopeType} onChange={(event) => { setScopeType(event.target.value as SecretScope); setScopeId(""); }}><option value="connector">连接器</option><option value="delivery_target">交付目标</option></select></label><label className="field"><span>资源</span><select value={scopeId} onChange={(event) => setScopeId(event.target.value)} required><option value="">选择资源</option>{scopeOptions.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label></div>
            <label className="field"><span>密钥名称</span><input value={secretName} onChange={(event) => setSecretName(event.target.value)} pattern="[A-Za-z0-9_.-]+" required /></label>
            <label className="field"><span>密钥值</span><input type="password" autoComplete="new-password" value={secretValue} onChange={(event) => setSecretValue(event.target.value)} required /></label>
            <button className="button primary integration-submit" disabled={busy}><KeyRound size={14} />加密保存</button>
          </form>
          <div className="integration-list">{(secrets.data ?? []).map((secret) => <article key={secret.id} className="integration-row"><i><KeyRound size={15} /></i><div><strong>{secret.name}</strong><code>{secret.scope_type} / {secret.scope_id.slice(0, 16)} · v{secret.version}</code></div><button className="icon-button" disabled={busy} onClick={() => void act(() => api.deleteSecret(secret.id), "密钥已删除")} aria-label={`删除密钥 ${secret.name}`}><Trash2 size={14} /></button></article>)}</div>
        </> : <div className="drawer-empty"><KeyRound size={28} /><h2>密钥仅对管理员可见</h2></div>}
      </div>}

      {tab === "delivery" && <div className="drawer-body">
        {currentUser.role !== "viewer" && <form className="integration-form" onSubmit={(event) => { event.preventDefault(); void createTarget(); }}>
          <div className="field-grid"><label className="field"><span>目标名称</span><input value={targetName} onChange={(event) => setTargetName(event.target.value)} required /></label><label className="field"><span>类型</span><select value={targetType} onChange={(event) => setTargetType(event.target.value as DeliveryTargetType)}><option value="ndjson">NDJSON 文件</option><option value="webhook">Webhook</option></select></label></div>
          {targetType === "webhook" && <label className="field"><span>Webhook URL</span><input type="url" value={targetUrl} onChange={(event) => setTargetUrl(event.target.value)} required /></label>}
          <button className="button primary integration-submit" disabled={busy}><Archive size={14} />创建目标</button>
        </form>}
        <div className="integration-list target-list">{(targets.data ?? []).map((target) => <TargetRow key={target.id} target={target} secrets={(secrets.data ?? []).filter((item) => item.scope_type === "delivery_target" && item.scope_id === target.id)} admin={currentUser.role === "admin" || currentUser.id === target.owner_id} busy={busy} act={act} />)}</div>
        {currentUser.role !== "viewer" && <form className="integration-form delivery-form" onSubmit={(event) => { event.preventDefault(); void deliver(); }}>
          <div className="field-grid"><label className="field"><span>交付目标</span><select value={deliveryTarget} onChange={(event) => setDeliveryTarget(event.target.value)} required><option value="">选择目标</option>{(targets.data ?? []).filter((item) => item.enabled).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="field"><span>运行结果</span><select value={deliveryRun} onChange={(event) => setDeliveryRun(event.target.value)} required><option value="">选择运行</option>{(runs.data ?? []).map((run) => <option key={run.id} value={run.id}>{run.flow_name} / {run.id.slice(0, 8)}</option>)}</select></label></div>
          <button className="button primary integration-submit" disabled={busy}><Send size={14} />立即交付</button>
        </form>}
        <div className="delivery-history">{(deliveries.data ?? []).map((delivery) => <article key={delivery.id}><i className={delivery.status}>{delivery.status === "succeeded" ? <Check size={13} /> : <RefreshCw size={13} />}</i><div><strong>{delivery.status}</strong><code>{delivery.id.slice(0, 8)} · 尝试 {delivery.attempt_count}{delivery.response_status ? ` · HTTP ${delivery.response_status}` : ""}</code><small>{delivery.error ?? delivery.artifact_path ?? delivery.next_attempt_at ?? "完成"}</small></div>{(delivery.status === "dead_letter" || delivery.status === "cancelled") && <button className="icon-button" onClick={() => void act(() => api.replayDelivery(delivery.id), "交付已重放")} aria-label="重放交付"><RotateCcw size={14} /></button>}{delivery.status === "retrying" && <button className="icon-button" onClick={() => void act(() => api.cancelDelivery(delivery.id), "交付已取消")} aria-label="取消交付"><X size={14} /></button>}</article>)}</div>
      </div>}
      <footer className="drawer-user"><span>{currentUser.display_name}</span><code>P4 integration control plane</code></footer>
    </aside>
  );
}

function ConnectorRow({ connector, admin, busy, act }: { connector: ManagedConnectorRecord; admin: boolean; busy: boolean; act: (action: () => Promise<unknown>, success: string) => Promise<void> }) {
  return <article className="connector-row"><div><strong>{connector.manifest.name}</strong><code>{connector.version} · {connector.state}</code></div><p>{connector.manifest.description}</p><span>{connector.id} · {connector.source}</span>{admin && <div className="row-actions"><button className="button" disabled={busy} onClick={() => void act(() => api.setConnectorEnabled(connector.id, connector.state !== "enabled"), connector.state === "enabled" ? "连接器已停用" : "连接器已启用")}>{connector.state === "enabled" ? "停用" : "启用"}</button><button className="icon-button" disabled={busy || !connector.previous_version} onClick={() => void act(() => api.rollbackConnector(connector.id), "连接器已回退")} aria-label={`回退 ${connector.id}`}><RotateCcw size={14} /></button><button className="icon-button" disabled={busy} onClick={() => void act(() => api.uninstallConnector(connector.id), "连接器已卸载")} aria-label={`卸载 ${connector.id}`}><Trash2 size={14} /></button></div>}</article>;
}

function TargetRow({ target, secrets, admin, busy, act }: { target: DeliveryTargetRecord; secrets: Array<{ id: string; name: string }>; admin: boolean; busy: boolean; act: (action: () => Promise<unknown>, success: string) => Promise<void> }) {
  const [auth, setAuth] = useState<DeliveryAuthScheme>(target.auth_scheme);
  const [secretId, setSecretId] = useState(target.secret_id ?? "");
  return <article className="target-row"><div><i className={target.enabled ? "enabled" : ""} /><span><strong>{target.name}</strong><code>{target.type} · {target.url ?? "exports/"}</code></span><label className="mini-switch"><input type="checkbox" checked={target.enabled} disabled={!admin || busy} onChange={(event) => void act(() => api.updateDeliveryTarget(target, { enabled: event.target.checked }), event.target.checked ? "目标已启用" : "目标已暂停")} /><i /></label></div>{admin && <div className="target-auth"><select aria-label={`${target.name} 认证方式`} value={auth} onChange={(event) => setAuth(event.target.value as DeliveryAuthScheme)}><option value="none">无认证</option><option value="bearer">Bearer</option><option value="hmac_sha256">HMAC-SHA256</option></select><select aria-label={`${target.name} 密钥`} value={secretId} onChange={(event) => setSecretId(event.target.value)} disabled={auth === "none"}><option value="">选择密钥</option>{secrets.map((secret) => <option key={secret.id} value={secret.id}>{secret.name}</option>)}</select><button className="button" disabled={busy || (auth !== "none" && !secretId)} onClick={() => void act(() => api.updateDeliveryTarget(target, { auth_scheme: auth, secret_id: auth === "none" ? null : secretId }), "目标认证已更新")}>保存</button></div>}</article>;
}
