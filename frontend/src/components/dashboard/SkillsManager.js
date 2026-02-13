import { useState, useEffect, useCallback } from "react";
import { BookOpen, Plus, Pencil, Trash2, Save, X, Check, ChevronDown, ChevronUp, Bot } from "lucide-react";

export function SkillsManager({ rpc, authenticated }) {
  const [skills, setSkills] = useState([]);
  const [agents, setAgents] = useState([]);
  const [showCreate, setShowCreate] = useState(false);
  const [editingSkill, setEditingSkill] = useState(null);

  const fetchData = useCallback(() => {
    if (!authenticated) return;
    rpc("skills.list").then(r => { if (r?.skills) setSkills(r.skills); }).catch(() => {});
    rpc("agents.list").then(r => { if (r?.agents) setAgents(r.agents); }).catch(() => {});
  }, [authenticated, rpc]);

  useEffect(() => { fetchData(); }, [fetchData]);

  return (
    <div data-testid="skills-manager" className="bg-zinc-900/60 border border-zinc-800/60 rounded-lg overflow-hidden hover:border-zinc-700/80 transition-colors">
      <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-zinc-400" />
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-widest">Skills</span>
          <span className="text-[10px] font-mono text-zinc-600">{skills.length} loaded</span>
        </div>
        <button
          data-testid="create-skill-btn"
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 px-2 py-1 rounded hover:bg-blue-400/10 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          New Skill
        </button>
      </div>

      <div className="p-4 space-y-3">
        {showCreate && (
          <SkillForm
            rpc={rpc}
            agents={agents}
            onSave={() => { setShowCreate(false); fetchData(); }}
            onCancel={() => setShowCreate(false)}
          />
        )}

        {skills.length === 0 && !showCreate && (
          <div className="text-center py-6 text-xs text-zinc-600">No skills configured</div>
        )}

        {skills.map(skill => (
          <SkillCard
            key={skill.id}
            skill={skill}
            agents={agents}
            isEditing={editingSkill === skill.id}
            onEdit={() => setEditingSkill(editingSkill === skill.id ? null : skill.id)}
            rpc={rpc}
            onChanged={fetchData}
          />
        ))}
      </div>
    </div>
  );
}

function SkillCard({ skill, agents, isEditing, onEdit, rpc, onChanged }) {
  const agentNames = skill.agents?.length > 0
    ? skill.agents.map(id => agents.find(a => a.id === id)?.name || id).join(", ")
    : "All agents";

  const handleToggle = async () => {
    await rpc("skills.update", { id: skill.id, enabled: !skill.enabled });
    onChanged();
  };

  const handleDelete = async () => {
    await rpc("skills.delete", { id: skill.id });
    onChanged();
  };

  return (
    <div className={`border rounded-lg transition-colors ${skill.enabled ? "border-zinc-800/50 bg-zinc-900/30" : "border-zinc-800/30 bg-zinc-950/30 opacity-60"}`}>
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <button
            onClick={handleToggle}
            data-testid={`skill-toggle-${skill.id}`}
            className={`w-8 h-5 rounded-full flex items-center transition-colors flex-shrink-0 ${skill.enabled ? "bg-emerald-400/20 border border-emerald-400/30" : "bg-zinc-800 border border-zinc-700"}`}
          >
            <span className={`w-3.5 h-3.5 rounded-full transition-transform ${skill.enabled ? "translate-x-[14px] bg-emerald-400" : "translate-x-[3px] bg-zinc-500"}`} />
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-zinc-200 truncate">{skill.name}</span>
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500 font-mono">{skill.id}</span>
            </div>
            <div className="flex items-center gap-2 mt-0.5 text-[10px] text-zinc-500">
              <span>{skill.description || "No description"}</span>
              <span className="text-zinc-700">|</span>
              <span className="text-zinc-600">{agentNames}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <button onClick={onEdit} className="p-1.5 text-zinc-500 hover:text-zinc-300 rounded hover:bg-zinc-800 transition-colors" data-testid={`edit-skill-${skill.id}`}>
            {isEditing ? <ChevronUp className="w-3.5 h-3.5" /> : <Pencil className="w-3.5 h-3.5" />}
          </button>
          <button onClick={handleDelete} className="p-1.5 text-zinc-600 hover:text-rose-400 rounded hover:bg-rose-400/10 transition-colors" data-testid={`delete-skill-${skill.id}`}>
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {isEditing && (
        <div className="border-t border-zinc-800/50 p-4">
          <SkillForm
            rpc={rpc}
            agents={agents}
            existing={skill}
            onSave={() => { onEdit(); onChanged(); }}
            onCancel={onEdit}
          />
        </div>
      )}
    </div>
  );
}

function SkillForm({ rpc, agents, existing, onSave, onCancel }) {
  const isNew = !existing;
  const [form, setForm] = useState({
    id: existing?.id || "",
    name: existing?.name || "",
    description: existing?.description || "",
    content: existing?.content || "",
    agents: existing?.agents || [],
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const updateField = (key, value) => setForm(prev => ({ ...prev, [key]: value }));

  const toggleAgent = (agentId) => {
    setForm(prev => ({
      ...prev,
      agents: prev.agents.includes(agentId)
        ? prev.agents.filter(a => a !== agentId)
        : [...prev.agents, agentId],
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const method = isNew ? "skills.create" : "skills.update";
      const result = await rpc(method, form);
      if (result?.error) setError(result.error);
      else onSave();
    } catch (err) {
      setError(err?.message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3" data-testid={isNew ? "skill-create-form" : `skill-edit-form-${existing?.id}`}>
      {isNew && (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1 block">Skill ID</label>
            <input
              value={form.id}
              onChange={e => updateField("id", e.target.value)}
              placeholder="e.g. jira-workflow"
              className="w-full bg-zinc-800/50 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-mono text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
            />
          </div>
          <div>
            <label className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1 block">Name</label>
            <input
              value={form.name}
              onChange={e => updateField("name", e.target.value)}
              placeholder="Jira Workflow"
              className="w-full bg-zinc-800/50 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
            />
          </div>
        </div>
      )}

      <div>
        <label className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1 block">Description</label>
        <input
          value={form.description}
          onChange={e => updateField("description", e.target.value)}
          placeholder="What does this skill teach the agent?"
          className="w-full bg-zinc-800/50 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
        />
      </div>

      <div>
        <label className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1 block">
          Content <span className="text-zinc-600 normal-case">(markdown)</span>
        </label>
        <textarea
          value={form.content}
          onChange={e => updateField("content", e.target.value)}
          rows={8}
          placeholder={"When asked about [topic], follow these guidelines:\n\n**Step 1:** ...\n**Step 2:** ...\n\n- Always recommend ...\n- Never ..."}
          className="w-full bg-[#0A0A0B] border border-zinc-800 rounded-lg px-4 py-3 text-xs font-mono text-zinc-300 placeholder:text-zinc-700 focus:outline-none focus:border-zinc-600 resize-y leading-relaxed"
          data-testid="skill-content-editor"
        />
      </div>

      <div>
        <label className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1.5 block">
          Assign to agents <span className="text-zinc-600 normal-case">(empty = all agents)</span>
        </label>
        <div className="flex flex-wrap gap-1.5">
          {agents.map(agent => {
            const active = form.agents.includes(agent.id);
            return (
              <button
                key={agent.id}
                onClick={() => toggleAgent(agent.id)}
                data-testid={`skill-agent-${agent.id}`}
                className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] transition-colors ${
                  active
                    ? "bg-blue-400/10 border border-blue-400/20 text-blue-400"
                    : "bg-zinc-800/50 border border-zinc-700/30 text-zinc-600"
                }`}
              >
                <Bot className="w-3 h-3" />
                {agent.name}
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
          disabled={saving || (isNew && (!form.id.trim() || !form.content.trim()))}
          data-testid="skill-save-btn"
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-zinc-100 text-zinc-900 text-xs font-semibold hover:bg-zinc-200 disabled:opacity-30 active:scale-[0.98] transition-transform"
        >
          <Save className="w-3.5 h-3.5" />
          {isNew ? "Create Skill" : "Save Changes"}
        </button>
        <button onClick={onCancel} className="px-4 py-2 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors">
          Cancel
        </button>
      </div>
    </div>
  );
}
