import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Check, Plus, ShieldCheck, UserRound, Users, X } from "lucide-react";
import { api } from "../api";
import type { CurrentUser, UserRole } from "../types";

const roleLabel: Record<UserRole, string> = {
  admin: "管理员",
  editor: "编辑者",
  viewer: "只读成员",
};

export function TeamDrawer({
  currentUser,
  onClose,
  onToast,
}: {
  currentUser: CurrentUser;
  onClose: () => void;
  onToast: (kind: "success" | "error", message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"members" | "audit">("members");
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("viewer");
  const users = useQuery({ queryKey: ["users"], queryFn: api.users });
  const audit = useQuery({ queryKey: ["audit"], queryFn: api.audit, enabled: tab === "audit" });
  const security = useQuery({
    queryKey: ["security-operations"],
    queryFn: api.securityOperations,
    enabled: tab === "audit",
  });

  async function createUser() {
    if (!username || !displayName || password.length < 12) return;
    setBusy(true);
    try {
      await api.createUser({
        username: username.toLowerCase(),
        display_name: displayName,
        password,
        role,
      });
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      setAdding(false);
      setUsername("");
      setDisplayName("");
      setPassword("");
      setRole("viewer");
      onToast("success", "成员已创建");
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "创建成员失败");
    } finally {
      setBusy(false);
    }
  }

  async function updateUser(id: string, update: Partial<{ role: UserRole; active: boolean }>) {
    setBusy(true);
    try {
      await api.updateUser(id, update);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["users"] }),
        queryClient.invalidateQueries({ queryKey: ["audit"] }),
      ]);
      onToast("success", "成员权限已更新");
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "更新成员失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="side-drawer team-drawer" role="dialog" aria-modal="true" aria-label="团队与审计">
      <header>
        <div><Users size={17} /><strong>团队与审计</strong></div>
        <button className="icon-button" onClick={onClose} aria-label="关闭"><X size={16} /></button>
      </header>
      <nav className="drawer-tabs" aria-label="团队视图">
        <button className={tab === "members" ? "selected" : ""} onClick={() => setTab("members")}><Users size={14} />成员</button>
        <button className={tab === "audit" ? "selected" : ""} onClick={() => setTab("audit")}><Activity size={14} />审计</button>
      </nav>

      {tab === "members" ? (
        <div className="drawer-body">
          <div className="drawer-toolbar">
            <span>{users.data?.length ?? 0} 名成员</span>
            <button className="button primary" onClick={() => setAdding((value) => !value)}><Plus size={14} />添加成员</button>
          </div>
          {adding && (
            <form className="member-form" onSubmit={(event) => { event.preventDefault(); void createUser(); }}>
              <label className="field"><span>用户名</span><input value={username} onChange={(event) => setUsername(event.target.value)} pattern="[a-z][a-z0-9_.-]+" minLength={3} required /></label>
              <label className="field"><span>显示名称</span><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} required /></label>
              <label className="field"><span>初始密码</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} autoComplete="new-password" required /></label>
              <label className="field"><span>角色</span><select value={role} onChange={(event) => setRole(event.target.value as UserRole)}><option value="viewer">只读成员</option><option value="editor">编辑者</option><option value="admin">管理员</option></select></label>
              <div className="form-actions"><button type="button" className="button" onClick={() => setAdding(false)}>取消</button><button className="button primary" disabled={busy}><Check size={14} />创建</button></div>
            </form>
          )}
          <div className="member-list">
            {(users.data ?? []).map((user) => (
              <article key={user.id} className={!user.active ? "inactive" : ""}>
                <i><UserRound size={16} /></i>
                <div><strong>{user.display_name}</strong><code>@{user.username}</code></div>
                <select aria-label={`${user.username}角色`} value={user.role} disabled={busy || user.id === currentUser.id} onChange={(event) => void updateUser(user.id, { role: event.target.value as UserRole })}><option value="viewer">只读成员</option><option value="editor">编辑者</option><option value="admin">管理员</option></select>
                <label className="compact-toggle"><input type="checkbox" checked={user.active} disabled={busy || user.id === currentUser.id} onChange={(event) => void updateUser(user.id, { active: event.target.checked })} /><span>{user.active ? "启用" : "停用"}</span></label>
              </article>
            ))}
          </div>
        </div>
      ) : (
        <div className="drawer-body">
          <div className="security-summary"><ShieldCheck size={17} /><span><strong>安全事件</strong><small>{security.data?.recentAlerts.length ?? 0} 条活动告警 · {Object.values(security.data?.counters ?? {}).reduce((sum, value) => sum + value, 0)} 次计数</small></span></div>
          <div className="audit-list">
            {(audit.data ?? []).map((event) => (
              <article key={event.id}>
                <i className={event.outcome}>{event.outcome === "success" ? <Check size={13} /> : <X size={13} />}</i>
                <div><strong>{event.action}</strong><span>{event.actor_username ?? "system"} · {event.resource_type}{event.resource_id ? ` / ${event.resource_id.slice(0, 8)}` : ""}</span></div>
                <time>{new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(event.created_at))}</time>
              </article>
            ))}
            {!audit.isLoading && !audit.data?.length && <div className="drawer-empty"><Activity size={26} /><h2>暂无审计事件</h2></div>}
          </div>
        </div>
      )}
      <footer className="drawer-user"><span>{currentUser.display_name}</span><code>{roleLabel[currentUser.role]} · {currentUser.auth_mode}</code></footer>
    </aside>
  );
}
