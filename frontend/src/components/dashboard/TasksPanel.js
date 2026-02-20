import { useState, useEffect, useCallback } from "react";
import { Clock, Play, Pause, Trash2, Plus, ChevronDown, ChevronUp, RotateCw, History, AlertCircle } from "lucide-react";

export function TasksPanel({ rpc, authenticated }) {
  const [tasks, setTasks] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [expandedTask, setExpandedTask] = useState(null);
  const [taskHistory, setTaskHistory] = useState({});
  const [form, setForm] = useState({
    name: "", prompt: "", interval_seconds: 60, agent_id: "default", notify: "on_change",
  });
  const [agents, setAgents] = useState([]);

  const fetchTasks = useCallback(() => {
    if (!authenticated) return;
    rpc("tasks.list").then(r => {
      if (r?.tasks) setTasks(r.tasks);
    }).catch(() => {});
  }, [authenticated, rpc]);

  // Auto-refresh history for expanded task
  useEffect(() => {
    if (!expandedTask || !authenticated) return;
    const interval = setInterval(() => {
      rpc("tasks.history", { id: expandedTask, limit: 10 }).then(r => {
        if (r?.history) setTaskHistory(prev => ({ ...prev, [expandedTask]: r.history }));
      }).catch(() => {});
    }, 5000);
    return () => clearInterval(interval);
  }, [expandedTask, authenticated, rpc]);

  useEffect(() => {
    fetchTasks();
    if (authenticated) rpc("agents.list").then(r => { if (r?.agents) setAgents(r.agents); }).catch(() => {});
    const interval = setInterval(fetchTasks, 5000);
    return () => clearInterval(interval);
  }, [fetchTasks, authenticated, rpc]);

  const handleCreate = async () => {
    if (!form.name || !form.prompt) return;
    await rpc("tasks.create", form);
    setForm({ name: "", prompt: "", interval_seconds: 60, agent_id: "default", notify: "on_change" });
    setShowCreate(false);
    fetchTasks();
  };

  const handlePause = async (id) => { await rpc("tasks.pause", { id }); fetchTasks(); };
  const handleResume = async (id) => { await rpc("tasks.resume", { id }); fetchTasks(); };
  const handleDelete = async (id) => { await rpc("tasks.delete", { id }); fetchTasks(); };
  const handleRunNow = async (id) => {
    await rpc("tasks.run_now", { id });
    fetchTasks();
    // Auto-refresh history after the task likely completes
    if (expandedTask === id) {
      setTimeout(() => loadHistory(id, true), 5000);
      setTimeout(() => loadHistory(id, true), 15000);
      setTimeout(() => loadHistory(id, true), 30000);
    }
  };

  const loadHistory = async (taskId, forceOpen) => {
    if (!forceOpen && expandedTask === taskId) { setExpandedTask(null); return; }
    const r = await rpc("tasks.history", { id: taskId, limit: 10 });
    if (r?.history) setTaskHistory(prev => ({ ...prev, [taskId]: r.history }));
    setExpandedTask(taskId);
  };

  const formatInterval = (s) => {
    if (s < 60) return `${s}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  };

  return (
    <div className="bg-zinc-900/50 border border-zinc-800/60 rounded-xl overflow-hidden" data-testid="tasks-panel">
      <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800/40">
        <div className="flex items-center gap-2.5">
          <Clock className="w-4 h-4 text-orange-400" />
          <h3 className="text-sm font-semibold text-zinc-200" style={{ fontFamily: 'Manrope, sans-serif' }}>
            Scheduled Tasks
          </h3>
          <span className="text-[10px] text-zinc-600 font-mono">{tasks.length} tasks</span>
        </div>
        <button
          data-testid="create-task-btn"
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-orange-400/10 border border-orange-400/20 text-xs text-orange-400 hover:bg-orange-400/20 transition-colors"
        >
          <Plus className="w-3 h-3" />
          New Task
        </button>
      </div>

      {showCreate && (
        <div className="p-4 border-b border-zinc-800/40 bg-zinc-900/80 space-y-3" data-testid="create-task-form">
          <div className="grid grid-cols-2 gap-3">
            <input
              data-testid="task-name-input"
              value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder="Task name" className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
            />
            <select
              data-testid="task-agent-select"
              value={form.agent_id} onChange={e => setForm({ ...form, agent_id: e.target.value })}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 focus:outline-none"
            >
              {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
          <textarea
            data-testid="task-prompt-input"
            value={form.prompt} onChange={e => setForm({ ...form, prompt: e.target.value })}
            placeholder="Task prompt — what should the agent do each time? (e.g., 'Monitor https://... for new notifications')"
            rows={3}
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500 resize-none"
          />
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <label className="text-xs text-zinc-500">Every</label>
              <input
                data-testid="task-interval-input"
                type="number" min="10" value={form.interval_seconds}
                onChange={e => setForm({ ...form, interval_seconds: parseInt(e.target.value) || 60 })}
                className="w-20 bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 text-sm text-zinc-200 text-center focus:outline-none"
              />
              <label className="text-xs text-zinc-500">seconds</label>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-zinc-500">Notify</label>
              <select
                data-testid="task-notify-select"
                value={form.notify} onChange={e => setForm({ ...form, notify: e.target.value })}
                className="bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 text-xs text-zinc-200 focus:outline-none"
              >
                <option value="on_change">On change</option>
                <option value="always">Always</option>
                <option value="never">Never</option>
              </select>
            </div>
            <div className="flex-1" />
            <button
              data-testid="task-submit-btn"
              onClick={handleCreate}
              disabled={!form.name || !form.prompt}
              className="px-4 py-1.5 rounded-lg bg-orange-400 text-zinc-900 text-xs font-medium hover:bg-orange-300 disabled:opacity-30 transition-colors"
            >
              Create
            </button>
          </div>
        </div>
      )}

      <div className="divide-y divide-zinc-800/30">
        {tasks.length === 0 ? (
          <div className="px-5 py-8 text-center text-xs text-zinc-600">
            No scheduled tasks. Create one to start monitoring.
          </div>
        ) : tasks.map(task => (
          <div key={task.id} className="px-5 py-3" data-testid={`task-${task.id}`}>
            <div className="flex items-center gap-3">
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${task.enabled ? (task.running ? "bg-blue-400 animate-pulse" : "bg-emerald-400") : "bg-zinc-600"}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-zinc-200 font-medium truncate">{task.name}</span>
                  <span className="text-[10px] text-zinc-600 font-mono">{formatInterval(task.interval_seconds)}</span>
                  {task.running && <span className="text-[10px] text-blue-400 animate-pulse">running...</span>}
                </div>
                <div className="text-[11px] text-zinc-500 truncate mt-0.5">{task.prompt.slice(0, 80)}{task.prompt.length > 80 ? "..." : ""}</div>
                {task.last_run && (
                  <div className="text-[10px] text-zinc-600 mt-0.5">
                    Last: {new Date(task.last_run).toLocaleTimeString()} | Agent: {task.agent_id}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <button onClick={() => handleRunNow(task.id)} title="Run now" className="p-1.5 text-zinc-500 hover:text-blue-400 transition-colors" data-testid={`task-run-${task.id}`}>
                  <RotateCw className="w-3.5 h-3.5" />
                </button>
                <button onClick={() => loadHistory(task.id)} title="History" className="p-1.5 text-zinc-500 hover:text-zinc-300 transition-colors" data-testid={`task-history-${task.id}`}>
                  <History className="w-3.5 h-3.5" />
                </button>
                {task.enabled ? (
                  <button onClick={() => handlePause(task.id)} title="Pause" className="p-1.5 text-zinc-500 hover:text-amber-400 transition-colors" data-testid={`task-pause-${task.id}`}>
                    <Pause className="w-3.5 h-3.5" />
                  </button>
                ) : (
                  <button onClick={() => handleResume(task.id)} title="Resume" className="p-1.5 text-zinc-500 hover:text-emerald-400 transition-colors" data-testid={`task-resume-${task.id}`}>
                    <Play className="w-3.5 h-3.5" />
                  </button>
                )}
                <button onClick={() => handleDelete(task.id)} title="Delete" className="p-1.5 text-zinc-500 hover:text-rose-400 transition-colors" data-testid={`task-delete-${task.id}`}>
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {expandedTask === task.id && (
              <div className="mt-2 ml-5 space-y-1.5" data-testid={`task-history-list-${task.id}`}>
                {(taskHistory[task.id] || []).length === 0 ? (
                  <div className="text-[11px] text-zinc-600 py-2">No execution history yet</div>
                ) : (taskHistory[task.id] || []).map((h, i) => (
                  <div key={i} className="bg-zinc-800/40 rounded-lg px-3 py-2 text-[11px]">
                    <div className="flex items-center gap-2">
                      <span className={`w-1.5 h-1.5 rounded-full ${h.status === "success" ? "bg-emerald-400" : "bg-rose-400"}`} />
                      <span className="text-zinc-400">{new Date(h.timestamp).toLocaleString()}</span>
                      <span className="text-zinc-600">{h.tool_calls_count} tools</span>
                    </div>
                    <div className="text-zinc-500 mt-1 line-clamp-2">{h.response?.slice(0, 150)}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
