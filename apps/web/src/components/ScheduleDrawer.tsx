import { useEffect, useState } from "react";
import { CalendarClock, Edit3, Play, Plus, Save, Trash2, X } from "lucide-react";
import { api } from "../api";
import type { FlowRecord, RunRecord, ScheduleDefinition, ScheduleRecord } from "../types";

interface Props {
  schedules: ScheduleRecord[];
  flows: FlowRecord[];
  loading: boolean;
  onClose: () => void;
  onChanged: () => void;
  onRun: (run: RunRecord) => void;
  onToast: (kind: "success" | "error", message: string) => void;
}

function blank(flowId = ""): ScheduleDefinition {
  return {
    flow_id: flowId,
    name: "每日采集",
    cron: "0 8 * * *",
    timezone: "Asia/Shanghai",
    enabled: true,
    parameters: {},
  };
}

export function ScheduleDrawer({ schedules, flows, loading, onClose, onChanged, onRun, onToast }: Props) {
  const [editing, setEditing] = useState<ScheduleRecord | null>(null);
  const [form, setForm] = useState<ScheduleDefinition>(() => blank(flows[0]?.id));
  const [parametersText, setParametersText] = useState("{}");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!form.flow_id && flows[0]) setForm((current) => ({ ...current, flow_id: flows[0].id }));
  }, [flows, form.flow_id]);

  function reset() {
    setEditing(null);
    setForm(blank(flows[0]?.id));
    setParametersText("{}");
  }

  function edit(schedule: ScheduleRecord) {
    setEditing(schedule);
    setForm({
      flow_id: schedule.flow_id,
      name: schedule.name,
      cron: schedule.cron,
      timezone: schedule.timezone,
      enabled: schedule.enabled,
      parameters: schedule.parameters,
    });
    setParametersText(JSON.stringify(schedule.parameters, null, 2));
  }

  async function save() {
    setBusy(true);
    try {
      const parameters = JSON.parse(parametersText) as Record<string, unknown>;
      if (editing) {
        await api.updateSchedule({ ...editing, ...form, parameters });
        onToast("success", "计划已更新");
      } else {
        await api.createSchedule({ ...form, parameters });
        onToast("success", "计划已创建");
      }
      reset();
      onChanged();
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "保存计划失败");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(schedule: ScheduleRecord) {
    try {
      await api.updateSchedule({ ...schedule, enabled: !schedule.enabled });
      onChanged();
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "更新计划失败");
    }
  }

  async function trigger(schedule: ScheduleRecord) {
    try {
      const run = await api.triggerSchedule(schedule.id);
      onRun(run);
      onChanged();
      onToast("success", "计划已触发");
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "触发计划失败");
    }
  }

  async function remove(schedule: ScheduleRecord) {
    if (!window.confirm(`删除计划“${schedule.name}”？`)) return;
    try {
      await api.deleteSchedule(schedule.id);
      if (editing?.id === schedule.id) reset();
      onChanged();
    } catch (error) {
      onToast("error", error instanceof Error ? error.message : "删除计划失败");
    }
  }

  return (
    <aside className="side-drawer schedule-drawer" role="dialog" aria-modal="true" aria-label="调度计划">
      <header>
        <div><CalendarClock size={17} /><strong>调度计划</strong><span>{schedules.length}</span></div>
        <button className="icon-button" onClick={onClose} aria-label="关闭"><X size={16} /></button>
      </header>
      <section className="schedule-form">
        <div className="schedule-form__title">
          <strong>{editing ? "编辑计划" : "新建计划"}</strong>
          {editing && <button className="button" onClick={reset}><Plus size={13} />新建</button>}
        </div>
        <label className="field"><span>名称</span><input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
        <label className="field"><span>流程</span><select value={form.flow_id} onChange={(event) => setForm({ ...form, flow_id: event.target.value })}>{flows.map((flow) => <option key={flow.id} value={flow.id}>{flow.name}</option>)}</select></label>
        <div className="field-grid">
          <label className="field"><span>Cron</span><input value={form.cron} onChange={(event) => setForm({ ...form, cron: event.target.value })} /></label>
          <label className="field"><span>时区</span><input value={form.timezone} onChange={(event) => setForm({ ...form, timezone: event.target.value })} /></label>
        </div>
        <label className="field"><span>运行参数 JSON</span><textarea value={parametersText} onChange={(event) => setParametersText(event.target.value)} spellCheck={false} /></label>
        <label className="switch-field"><span>启用计划</span><input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} /><i /></label>
        <button className="button primary schedule-save" disabled={busy || !form.flow_id || !form.name.trim()} onClick={() => void save()}><Save size={14} />{editing ? "保存修改" : "创建计划"}</button>
      </section>
      <section className="schedule-list" aria-label="计划列表">
        {loading ? <div className="drawer-loading">正在读取计划</div> : schedules.map((schedule) => (
          <article className="schedule-row" key={schedule.id}>
            <div className="schedule-row__main">
              <i className={schedule.enabled ? "enabled" : ""} />
              <span><strong>{schedule.name}</strong><code>{schedule.cron} / {schedule.timezone}</code></span>
              <label className="mini-switch" title={schedule.enabled ? "停用" : "启用"}><input type="checkbox" checked={schedule.enabled} onChange={() => void toggle(schedule)} /><i /></label>
            </div>
            <dl>
              <div><dt>下次运行</dt><dd>{schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString("zh-CN", { hour12: false }) : "已暂停"}</dd></div>
              <div><dt>最近运行</dt><dd>{schedule.last_run_at ? new Date(schedule.last_run_at).toLocaleString("zh-CN", { hour12: false }) : "--"}</dd></div>
            </dl>
            {schedule.last_error && <p className="schedule-error">{schedule.last_error}</p>}
            <div className="schedule-row__actions">
              <button className="icon-button" title="编辑" aria-label="编辑" onClick={() => edit(schedule)}><Edit3 size={14} /></button>
              <button className="icon-button" title="立即运行" aria-label="立即运行" onClick={() => void trigger(schedule)}><Play size={14} /></button>
              <button className="icon-button danger-icon" title="删除" aria-label="删除" onClick={() => void remove(schedule)}><Trash2 size={14} /></button>
            </div>
          </article>
        ))}
        {!loading && !schedules.length && <div className="drawer-empty schedule-empty"><CalendarClock size={28} /><h2>还没有调度计划</h2><p>上方创建后，执行引擎会按时区计算下次运行时间。</p></div>}
      </section>
    </aside>
  );
}
