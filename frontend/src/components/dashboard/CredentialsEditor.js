import { useState, useEffect, useCallback } from "react";
import { Eye, EyeOff, Save, Loader2, CheckCircle, KeyRound, Mail, MessageSquare, Sparkles, Shield, Building2 } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL || "";

const CREDENTIAL_GROUPS = [
  {
    id: "llm",
    title: "LLM Providers",
    fields: [
      { key: "anthropic_api_key", label: "Anthropic API Key", placeholder: "sk-ant-...", icon: Sparkles },
      { key: "openai_api_key", label: "OpenAI API Key", placeholder: "sk-proj-...", icon: Sparkles },
    ],
  },
  {
    id: "security",
    title: "Security",
    fields: [
      { key: "gateway_token", label: "Gateway Token", placeholder: "my-secret-token", icon: Shield },
    ],
  },
  {
    id: "google",
    title: "Google / Gmail",
    fields: [
      { key: "google_client_id", label: "Google Client ID", placeholder: "...apps.googleusercontent.com", icon: Mail },
      { key: "google_client_secret", label: "Google Client Secret", placeholder: "GOCSPX-...", icon: Mail },
    ],
  },
  {
    id: "slack",
    title: "Slack",
    fields: [
      { key: "slack_bot_token", label: "Slack Bot Token", placeholder: "xoxb-...", icon: MessageSquare },
      { key: "slack_app_token", label: "Slack App Token", placeholder: "xapp-...", icon: MessageSquare },
    ],
  },
  {
    id: "azure",
    title: "Azure / Outlook",
    fields: [
      { key: "azure_client_id", label: "Azure Client ID", placeholder: "00000000-...", icon: Building2 },
      { key: "azure_client_secret", label: "Azure Client Secret", placeholder: "~abc123...", icon: Building2 },
      { key: "azure_tenant_id", label: "Azure Tenant ID", placeholder: "00000000-... or common", icon: Building2 },
    ],
  },
];

export function CredentialsEditor() {
  const [status, setStatus] = useState(null);
  const [values, setValues] = useState({});
  const [visible, setVisible] = useState({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/setup/status`);
      const data = await res.json();
      setStatus(data.fields || {});
    } catch {}
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const handleChange = (key, val) => {
    setValues((prev) => ({ ...prev, [key]: val }));
    setSaved(false);
    setError("");
  };

  const handleSave = async () => {
    const payload = {};
    for (const [k, v] of Object.entries(values)) {
      if (v?.trim()) payload[k] = v.trim();
    }
    if (Object.keys(payload).length === 0) return;

    setSaving(true);
    setError("");
    try {
      const res = await fetch(`${API}/api/setup/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.ok) {
        setSaved(true);
        setValues({});
        if (payload.gateway_token) {
          localStorage.setItem("overclaw_gateway_token", payload.gateway_token);
        }
        fetchStatus();
        setTimeout(() => setSaved(false), 3000);
      } else {
        setError(data.error || "Save failed");
      }
    } catch {
      setError("Connection failed");
    }
    setSaving(false);
  };

  const changedCount = Object.values(values).filter((v) => v?.trim()).length;

  return (
    <div className="space-y-4" data-testid="credentials-editor">
      {CREDENTIAL_GROUPS.map((group) => (
        <div key={group.id} className="bg-zinc-900/50 border border-zinc-800/60 rounded-xl p-5">
          <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-4">{group.title}</h4>
          <div className="space-y-3">
            {group.fields.map((field) => {
              const existing = status?.[field.key];
              const isSet = existing?.is_set;
              const masked = existing?.masked_value;
              const Icon = field.icon;

              return (
                <div key={field.key} className="flex items-center gap-3" data-testid={`cred-field-${field.key}`}>
                  <Icon className="w-4 h-4 text-zinc-500 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm text-zinc-300">{field.label}</span>
                      {isSet && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          configured
                        </span>
                      )}
                    </div>
                    <div className="relative">
                      <input
                        type={visible[field.key] ? "text" : "password"}
                        value={values[field.key] ?? ""}
                        onChange={(e) => handleChange(field.key, e.target.value)}
                        placeholder={isSet ? masked || "********" : field.placeholder}
                        className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500 transition-colors font-mono"
                        data-testid={`cred-input-${field.key}`}
                        autoComplete="off"
                        spellCheck={false}
                      />
                      <button
                        onClick={() => setVisible((p) => ({ ...p, [field.key]: !p[field.key] }))}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
                        type="button"
                        tabIndex={-1}
                      >
                        {visible[field.key] ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Save bar */}
      <div className="flex items-center justify-between bg-zinc-900/50 border border-zinc-800/60 rounded-xl px-5 py-3">
        <div className="text-xs text-zinc-500">
          {changedCount > 0
            ? `${changedCount} field${changedCount > 1 ? "s" : ""} changed — save to apply`
            : "Enter new values above to update credentials"}
        </div>
        <div className="flex items-center gap-3">
          {error && <span className="text-xs text-red-400">{error}</span>}
          {saved && (
            <span className="flex items-center gap-1 text-xs text-emerald-400">
              <CheckCircle size={13} /> Saved
            </span>
          )}
          <button
            data-testid="cred-save-btn"
            onClick={handleSave}
            disabled={changedCount === 0 || saving}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
              bg-indigo-600/20 border border-indigo-500/30 text-indigo-300 hover:bg-indigo-600/30 transition-colors
              disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            {saving ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
