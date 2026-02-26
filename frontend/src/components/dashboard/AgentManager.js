import { useState, useEffect, useCallback } from "react";
import { Bot, Plus, Pencil, Trash2, Save, X, ChevronDown, ChevronUp, Wrench, Shield, Cpu } from "lucide-react";

const DEFAULT_TOOLS = ["web_search", "read_file", "write_file", "list_files", "execute_command"];

export function AgentManager({ rpc, authenticated }) {
  const [agents, setAgents] = useState([]);
  const [routes, setRoutes] = useState([]);
  const [editingAgent, setEditingAgent] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [routeEditing, setRouteEditing] = useState(false);

  const fetchAgents = useCallback(() => {
    if (!authenticated) return;
    rpc("agents.list").then(r => { if (r?.agents) setAgents(r.agents); }).catch(() => {});
    rpc("routing.list").then(r => { if (r?.routes) setRoutes(r.routes); }).catch(() => {});
  }, [authenticated, rpc]);

  useEffect(() => { fetchAgents(); }, [fetchAgents]);

  return (
    <div data-testid="agent-manager" className="bg-zinc-900/60 border border-zinc-800/60 rounded-lg overflow-hidden hover:border-zinc-700/80 transition-colors">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-zinc-400" />
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-widest">Agents & Routing</span>
        </div>
        <button
          data-testid="create-agent-btn"
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 px-2 py-1 rounded hover:bg-blue-400/10 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          New Agent
        </button>
      </div>

      <div className="p-4 space-y-3">
        {/* Create Agent Form */}
        {showCreate && (
          <AgentForm
            rpc={rpc}
            onSave={() => { setShowCreate(false); fetchAgents(); }}
            onCancel={() => setShowCreate(false)}
          />
        )}

        {/* Agent Cards */}
        {agents.map(agent => (
          <AgentCard
            key={agent.id}
            agent={agent}
            isEditing={editingAgent === agent.id}
            onEdit={() => setEditingAgent(editingAgent === agent.id ? null : agent.id)}
            onSaved={fetchAgents}
            onDeleted={fetchAgents}
            rpc={rpc}
            routes={routes}
          />
        ))}

        {/* Routing Rules */}
        <RoutingSection
          routes={routes}
          agents={agents}
          editing={routeEditing}
          onToggle={() => setRouteEditing(!routeEditing)}
          rpc={rpc}
          onSaved={fetchAgents}
        />
      </div>
    </div>
  );
}

function AgentCard({ agent, isEditing, onEdit, onSaved, onDeleted, rpc, routes }) {
  const isDefault = agent.id === "default";
  const routeCount = routes.filter(r => r.agent_id === agent.id).length;
  const providerColor = agent.model?.startsWith("anthropic") ? "text-orange-400" : "text-emerald-400";

  const handleDelete = async () => {
    if (isDefault) return;
    await rpc("agents.delete", { id: agent.id });
    onDeleted();
  };

  return (
    <div className={`border rounded-lg transition-colors ${isDefault ? "border-zinc-700/60 bg-zinc-800/30" : "border-zinc-800/50 bg-zinc-900/30"}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className={`w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0 ${isDefault ? "bg-zinc-700 border border-zinc-600" : "bg-blue-400/10 border border-blue-400/20"}`}>
            <Bot className={`w-3.5 h-3.5 ${isDefault ? "text-zinc-300" : "text-blue-400"}`} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-zinc-200 truncate">{agent.name}</span>
              {isDefault && <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-400 uppercase tracking-wider">default</span>}
            </div>
            <div className="flex items-center gap-3 text-[10px] text-zinc-500 mt-0.5">
              <span className={`font-mono ${providerColor}`}>{agent.model}</span>
              <span>{routeCount} route{routeCount !== 1 ? "s" : ""}</span>
              {agent.tools_allowed && <span>{agent.tools_allowed.length} tools</span>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={onEdit} className="p-1.5 text-zinc-500 hover:text-zinc-300 rounded hover:bg-zinc-800 transition-colors" data-testid={`edit-agent-${agent.id}`}>
            {isEditing ? <ChevronUp className="w-3.5 h-3.5" /> : <Pencil className="w-3.5 h-3.5" />}
          </button>
          {!isDefault && (
            <button onClick={handleDelete} className="p-1.5 text-zinc-600 hover:text-rose-400 rounded hover:bg-rose-400/10 transition-colors" data-testid={`delete-agent-${agent.id}`}>
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Description */}
      {agent.description && (
        <div className="px-4 pb-2 text-xs text-zinc-500">{agent.description}</div>
      )}

      {/* Edit form */}
      {isEditing && (
        <div className="border-t border-zinc-800/50 p-4">
          <AgentForm
            rpc={rpc}
            existing={agent}
            onSave={() => { onEdit(); onSaved(); }}
            onCancel={onEdit}
          />
        </div>
      )}
    </div>
  );
}

function AgentForm({ rpc, existing, onSave, onCancel }) {
  const isNew = !existing;
  const [form, setForm] = useState({
    id: existing?.id || "",
    name: existing?.name || "",
    description: existing?.description || "",
    model: existing?.model || "openai/gpt-4o",
    system_prompt: existing?.system_prompt || "You are a helpful assistant.",
    max_context_messages: existing?.max_context_messages || 50,
    tools_allowed: existing?.tools_allowed || ["web_search", "read_file", "list_files"],
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const updateField = (key, value) => setForm(prev => ({ ...prev, [key]: value }));
  const toggleTool = (tool) => {
    setForm(prev => ({
      ...prev,
      tools_allowed: prev.tools_allowed.includes(tool)
        ? prev.tools_allowed.filter(t => t !== tool)
        : [...prev.tools_allowed, tool],
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const method = isNew ? "agents.create" : "agents.update";
      const result = await rpc(method, form);
      if (result?.error) {
        setError(result.error);
      } else {
        onSave();
      }
    } catch (err) {
      setError(err?.message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3" data-testid={isNew ? "agent-create-form" : `agent-edit-form-${existing?.id}`}>
      {isNew && (
        <div className="grid grid-cols-2 gap-3">
          <FieldInput label="Agent ID" value={form.id} onChange={v => updateField("id", v)} placeholder="e.g. engineering" mono />
          <FieldInput label="Name" value={form.name} onChange={v => updateField("name", v)} placeholder="Engineering Agent" />
        </div>
      )}
      {!isNew && existing?.id !== "default" && (
        <FieldInput label="Name" value={form.name} onChange={v => updateField("name", v)} />
      )}
      <FieldInput label="Description" value={form.description} onChange={v => updateField("description", v)} placeholder="What does this agent do?" />

      <div>
        <label className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1 block">Model</label>
        <select
          value={form.model}
          onChange={e => updateField("model", e.target.value)}
          className="w-full bg-zinc-800/50 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-mono text-zinc-200 focus:outline-none focus:border-zinc-500"
          data-testid="agent-model-select"
        >
          <optgroup label="OpenAI">
            <option value="openai/gpt-5.2">GPT-5.2</option>
            <option value="openai/gpt-5.2-pro">GPT-5.2 Pro</option>
            <option value="openai/gpt-5-mini">GPT-5 Mini</option>
            <option value="openai/gpt-4.1">GPT-4.1</option>
            <option value="openai/gpt-4.1-mini">GPT-4.1 Mini</option>
            <option value="openai/gpt-4o">GPT-4o</option>
          </optgroup>
          <optgroup label="Anthropic">
            <option value="anthropic/claude-opus-4.6">Claude Opus 4.6</option>
            <option value="anthropic/claude-sonnet-4.6">Claude Sonnet 4.6</option>
            <option value="anthropic/claude-sonnet-4.5">Claude Sonnet 4.5</option>
            <option value="anthropic/claude-haiku-4.5">Claude Haiku 4.5</option>
          </optgroup>
        </select>
      </div>

      <div>
        <label className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1 block">System Prompt</label>
        <textarea
          value={form.system_prompt}
          onChange={e => updateField("system_prompt", e.target.value)}
          rows={3}
          className="w-full bg-zinc-800/50 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs text-zinc-200 focus:outline-none focus:border-zinc-500 resize-none"
          data-testid="agent-system-prompt"
        />
      </div>

      <div>
        <label className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5 block">Tools Allowed</label>
        <div className="flex flex-wrap gap-1.5">
          {DEFAULT_TOOLS.map(tool => {
            const active = form.tools_allowed.includes(tool);
            return (
              <button
                key={tool}
                onClick={() => toggleTool(tool)}
                data-testid={`tool-toggle-${tool}`}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-mono transition-colors ${
                  active ? "bg-amber-400/10 border border-amber-400/20 text-amber-400" : "bg-zinc-800/50 border border-zinc-700/30 text-zinc-600"
                }`}
              >
                <Wrench className="w-3 h-3" />
                {tool}
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <div className="text-xs text-rose-400 bg-rose-400/10 border border-rose-400/20 px-3 py-2 rounded-lg">{error}</div>
      )}

      <div className="flex items-center gap-2 pt-1">
        <button
          onClick={handleSave}
          disabled={saving || (isNew && !form.id.trim())}
          data-testid="agent-save-btn"
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-zinc-100 text-zinc-900 text-xs font-semibold hover:bg-zinc-200 disabled:opacity-30 active:scale-[0.98] transition-transform"
        >
          <Save className="w-3.5 h-3.5" />
          {isNew ? "Create Agent" : "Save Changes"}
        </button>
        <button
          onClick={onCancel}
          className="px-4 py-2 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function RoutingSection({ routes, agents, editing, onToggle, rpc, onSaved }) {
  const [localRoutes, setLocalRoutes] = useState(routes);
  const [saving, setSaving] = useState(false);

  useEffect(() => { setLocalRoutes(routes); }, [routes]);

  const addRoute = () => {
    setLocalRoutes(prev => [...prev, { pattern: "*", agent_id: "default" }]);
  };

  const updateRoute = (index, field, value) => {
    setLocalRoutes(prev => prev.map((r, i) => i === index ? { ...r, [field]: value } : r));
  };

  const removeRoute = (index) => {
    setLocalRoutes(prev => prev.filter((_, i) => i !== index));
  };

  const handleSave = async () => {
    setSaving(true);
    await rpc("routing.set", { routes: localRoutes });
    setSaving(false);
    onSaved();
    onToggle();
  };

  return (
    <div className="border border-zinc-800/50 rounded-lg overflow-hidden" data-testid="routing-section">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-zinc-800/30 transition-colors"
        data-testid="routing-toggle"
      >
        <div className="flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-zinc-500" />
          <span className="text-xs font-medium text-zinc-400">Routing Rules</span>
          <span className="text-[10px] font-mono text-zinc-600">{routes.length} rule{routes.length !== 1 ? "s" : ""}</span>
        </div>
        {editing ? <ChevronUp className="w-3.5 h-3.5 text-zinc-500" /> : <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />}
      </button>

      {editing && (
        <div className="border-t border-zinc-800/50 p-4 space-y-3">
          <p className="text-[11px] text-zinc-500 leading-relaxed">
            Routes are matched in order. Pattern format: <code className="text-zinc-400">channel:target:user</code> with <code className="text-zinc-400">*</code> wildcards.
            Examples: <code className="text-zinc-400">slack:C012345:*</code>, <code className="text-zinc-400">webchat:*</code>
          </p>

          {localRoutes.map((route, i) => (
            <div key={i} className="flex items-center gap-2" data-testid={`route-row-${i}`}>
              <input
                value={route.pattern}
                onChange={e => updateRoute(i, "pattern", e.target.value)}
                placeholder="pattern (e.g. slack:C012345:*)"
                className="flex-1 bg-zinc-800/50 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-mono text-zinc-200 focus:outline-none focus:border-zinc-500"
              />
              <span className="text-zinc-600 text-xs">&rarr;</span>
              <select
                value={route.agent_id}
                onChange={e => updateRoute(i, "agent_id", e.target.value)}
                className="bg-zinc-800/50 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-mono text-zinc-200 focus:outline-none focus:border-zinc-500"
              >
                {agents.map(a => (
                  <option key={a.id} value={a.id}>{a.name} ({a.id})</option>
                ))}
              </select>
              <button onClick={() => removeRoute(i)} className="p-1.5 text-zinc-600 hover:text-rose-400 transition-colors">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}

          <div className="flex items-center gap-2">
            <button onClick={addRoute} className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 px-3 py-1.5 rounded-lg hover:bg-zinc-800 transition-colors">
              <Plus className="w-3.5 h-3.5" />
              Add Rule
            </button>
            <div className="flex-1" />
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-zinc-100 text-zinc-900 text-xs font-semibold hover:bg-zinc-200 disabled:opacity-30 active:scale-[0.98] transition-transform"
              data-testid="routing-save-btn"
            >
              <Save className="w-3.5 h-3.5" />
              Save Routes
            </button>
          </div>
        </div>
      )}

      {!editing && routes.length > 0 && (
        <div className="border-t border-zinc-800/40 px-4 py-2 space-y-1">
          {routes.map((r, i) => (
            <div key={i} className="flex items-center gap-2 text-[11px]">
              <code className="text-zinc-400 font-mono">{r.pattern}</code>
              <span className="text-zinc-600">&rarr;</span>
              <span className="text-blue-400 font-mono">{r.agent_id}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FieldInput({ label, value, onChange, placeholder, mono }) {
  return (
    <div>
      <label className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1 block">{label}</label>
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className={`w-full bg-zinc-800/50 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500 ${mono ? "font-mono" : ""}`}
      />
    </div>
  );
}
