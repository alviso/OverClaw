import { useState, useEffect } from "react";
import { Eye, EyeOff, ChevronRight, ChevronLeft, Check, Loader2, KeyRound, Shield, Mail, MessageSquare, Sparkles, Building2 } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL || "";

const STEPS = [
  {
    id: "welcome",
    title: "Welcome to OverClaw",
    subtitle: "Let's get your assistant configured in a few steps.",
  },
  {
    id: "llm",
    title: "LLM Provider Keys",
    subtitle: "OverClaw needs at least one LLM provider to function.",
    fields: [
      {
        key: "anthropic_api_key",
        label: "Anthropic API Key",
        placeholder: "sk-ant-...",
        icon: Sparkles,
        description: "Powers the orchestrator and specialist agents. This is the primary LLM provider.",
        helpUrl: "https://console.anthropic.com/settings/keys",
        helpText: "Get your key from the Anthropic Console",
      },
      {
        key: "openai_api_key",
        label: "OpenAI API Key",
        placeholder: "sk-proj-...",
        icon: Sparkles,
        description: "Used for embeddings (long-term memory) and as a fallback LLM. Needed for the memory/RAG system to work.",
        helpUrl: "https://platform.openai.com/api-keys",
        helpText: "Get your key from the OpenAI Dashboard",
      },
    ],
  },
  {
    id: "security",
    title: "Gateway Security",
    subtitle: "Protect your OverClaw instance from unauthorized access.",
    fields: [
      {
        key: "gateway_token",
        label: "Gateway Token",
        placeholder: "my-secret-token-123",
        icon: Shield,
        description: "A password for the WebSocket connection between the frontend and backend. Anyone with this token can send messages to your agent. Pick something strong — this is the front door to your assistant.",
        helpText: "Choose any strong passphrase. This is NOT an API key — you make it up.",
      },
    ],
  },
  {
    id: "optional",
    title: "Optional Integrations",
    subtitle: "These are not required to get started. You can configure them later from the admin panel.",
    fields: [
      {
        key: "google_client_id",
        label: "Google Client ID",
        placeholder: "123456789-abc.apps.googleusercontent.com",
        icon: Mail,
        description: "Required for Gmail integration. OverClaw can search, read, and summarize your email if you connect a Google OAuth app.",
        helpUrl: "https://console.cloud.google.com/apis/credentials",
        helpText: "Create OAuth credentials in Google Cloud Console",
      },
      {
        key: "google_client_secret",
        label: "Google Client Secret",
        placeholder: "GOCSPX-...",
        icon: Mail,
        description: "The companion secret to the Client ID above. Found in the same Google Cloud Console page.",
      },
      {
        key: "slack_bot_token",
        label: "Slack Bot Token",
        placeholder: "xoxb-...",
        icon: MessageSquare,
        description: "Lets OverClaw send and receive messages in your Slack workspace. You'll need to create a Slack App first.",
        helpUrl: "https://api.slack.com/apps",
        helpText: "Create a Slack App at api.slack.com",
      },
      {
        key: "slack_app_token",
        label: "Slack App-Level Token",
        placeholder: "xapp-...",
        icon: MessageSquare,
        description: "Required for Slack's Socket Mode (real-time messaging). Generated in your Slack App's settings under 'Basic Information'.",
      },
    ],
  },
  {
    id: "done",
    title: "You're all set!",
    subtitle: "OverClaw is configured and ready to go.",
  },
];

function FieldInput({ field, value, onChange }) {
  const [visible, setVisible] = useState(false);
  const Icon = field.icon;

  return (
    <div className="mb-5 last:mb-0" data-testid={`setup-field-${field.key}`}>
      <div className="flex items-center gap-2 mb-1.5">
        <Icon size={15} className="text-zinc-400" />
        <label className="text-sm font-medium text-zinc-200">{field.label}</label>
      </div>
      <p className="text-xs text-zinc-500 mb-2 leading-relaxed pl-[23px]">{field.description}</p>
      <div className="relative pl-[23px]">
        <input
          type={visible ? "text" : "password"}
          value={value || ""}
          onChange={(e) => onChange(field.key, e.target.value)}
          placeholder={field.placeholder}
          className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500 transition-colors font-mono"
          data-testid={`setup-input-${field.key}`}
          autoComplete="off"
          spellCheck={false}
        />
        <button
          onClick={() => setVisible(!visible)}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors"
          tabIndex={-1}
          type="button"
        >
          {visible ? <EyeOff size={15} /> : <Eye size={15} />}
        </button>
      </div>
      {field.helpUrl && (
        <a
          href={field.helpUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block text-xs text-sky-500 hover:text-sky-400 mt-1.5 pl-[23px] transition-colors"
        >
          {field.helpText || "Where to get this"} &rarr;
        </a>
      )}
    </div>
  );
}

export function SetupWizard({ onComplete }) {
  const [stepIndex, setStepIndex] = useState(0);
  const [values, setValues] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [existingStatus, setExistingStatus] = useState(null);

  const step = STEPS[stepIndex];

  // Load existing status to show what's already configured
  useEffect(() => {
    fetch(`${API}/api/setup/status`)
      .then((r) => r.json())
      .then((data) => setExistingStatus(data))
      .catch(() => {});
  }, []);

  const handleChange = (key, val) => {
    setValues((prev) => ({ ...prev, [key]: val }));
    setError("");
  };

  const canProceed = () => {
    if (step.id === "llm") {
      // Need at least one LLM key
      const hasAnthropic = !!(values.anthropic_api_key?.trim());
      const hasOpenai = !!(values.openai_api_key?.trim());
      const existingAnthropic = existingStatus?.fields?.anthropic_api_key?.is_set;
      const existingOpenai = existingStatus?.fields?.openai_api_key?.is_set;
      return hasAnthropic || hasOpenai || existingAnthropic || existingOpenai;
    }
    if (step.id === "security") {
      const hasToken = !!(values.gateway_token?.trim());
      const existingToken = existingStatus?.fields?.gateway_token?.is_set;
      return hasToken || existingToken;
    }
    return true;
  };

  const handleNext = async () => {
    if (stepIndex < STEPS.length - 2) {
      setStepIndex((i) => i + 1);
    } else if (step.id === "optional" || step.id === "security") {
      // Save everything
      setSaving(true);
      setError("");
      try {
        // Filter out empty values
        const payload = {};
        for (const [k, v] of Object.entries(values)) {
          if (v?.trim()) payload[k] = v.trim();
        }

        if (Object.keys(payload).length > 0) {
          const res = await fetch(`${API}/api/setup/save`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const data = await res.json();
          if (!data.ok) {
            setError(data.error || "Failed to save");
            setSaving(false);
            return;
          }
          // Store gateway token in localStorage for WebSocket auth
          if (payload.gateway_token) {
            localStorage.setItem("overclaw_gateway_token", payload.gateway_token);
          }
        }
        setStepIndex(STEPS.length - 1); // Go to "done" step
      } catch (err) {
        setError("Connection failed. Is the backend running?");
      }
      setSaving(false);
    }
  };

  const handleFinish = () => {
    // Reload the page so the WebSocket reconnects with the new gateway token
    window.location.reload();
  };

  const handleBack = () => {
    if (stepIndex > 0) setStepIndex((i) => i - 1);
  };

  const handleSkipOptional = async () => {
    // Save what we have so far and skip optional
    setSaving(true);
    setError("");
    try {
      const payload = {};
      for (const [k, v] of Object.entries(values)) {
        if (v?.trim()) payload[k] = v.trim();
      }
      if (Object.keys(payload).length > 0) {
        const res = await fetch(`${API}/api/setup/save`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!data.ok) {
          setError(data.error || "Failed to save");
          setSaving(false);
          return;
        }
        if (payload.gateway_token) {
          localStorage.setItem("overclaw_gateway_token", payload.gateway_token);
        }
      }
      setStepIndex(STEPS.length - 1);
    } catch (err) {
      setError("Connection failed.");
    }
    setSaving(false);
  };

  // Progress dots
  const totalSteps = STEPS.length;

  return (
    <div className="h-screen bg-zinc-950 flex items-center justify-center p-4" data-testid="setup-wizard">
      <div className="w-full max-w-lg">
        {/* Progress */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                i === stepIndex
                  ? "w-8 bg-red-500"
                  : i < stepIndex
                  ? "w-4 bg-red-500/40"
                  : "w-4 bg-zinc-800"
              }`}
            />
          ))}
        </div>

        {/* Card */}
        <div className="bg-zinc-900/50 border border-zinc-800 rounded-2xl p-8">
          {/* Header */}
          <div className="mb-6">
            <h1 className="text-2xl font-bold text-zinc-100 mb-1">{step.title}</h1>
            <p className="text-sm text-zinc-500">{step.subtitle}</p>
          </div>

          {/* Welcome step */}
          {step.id === "welcome" && (
            <div className="space-y-4 text-sm text-zinc-400 leading-relaxed mb-6">
              <p>
                OverClaw needs a few API keys to connect to LLM providers and secure itself.
                This takes about 2 minutes.
              </p>
              <div className="bg-zinc-800/50 rounded-lg p-4 space-y-2">
                <div className="flex items-center gap-2">
                  <KeyRound size={14} className="text-red-400" />
                  <span className="text-zinc-300">LLM keys</span>
                  <span className="text-zinc-600">— at least one provider (Anthropic or OpenAI)</span>
                </div>
                <div className="flex items-center gap-2">
                  <Shield size={14} className="text-red-400" />
                  <span className="text-zinc-300">Gateway token</span>
                  <span className="text-zinc-600">— a password you choose to secure access</span>
                </div>
                <div className="flex items-center gap-2">
                  <Mail size={14} className="text-zinc-600" />
                  <span className="text-zinc-500">Gmail & Slack</span>
                  <span className="text-zinc-600">— optional, can be added later</span>
                </div>
              </div>
            </div>
          )}

          {/* Field steps */}
          {step.fields && (
            <div className="mb-6">
              {step.fields.map((field) => (
                <FieldInput
                  key={field.key}
                  field={field}
                  value={values[field.key] || ""}
                  onChange={handleChange}
                />
              ))}
              {step.id === "llm" && (
                <p className="text-xs text-zinc-600 mt-3 pl-[23px]">
                  You need at least one. Anthropic powers the orchestrator; OpenAI is used for memory embeddings.
                </p>
              )}
            </div>
          )}

          {/* Done step */}
          {step.id === "done" && (
            <div className="text-center py-4 mb-6">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/20 mb-4">
                <Check size={28} className="text-emerald-400" />
              </div>
              <p className="text-sm text-zinc-400">
                Your keys have been saved. You can update them anytime from the admin panel at <code className="text-zinc-300">/admin/config</code>.
              </p>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2 mb-4">
              {error}
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between">
            {stepIndex > 0 && step.id !== "done" ? (
              <button
                onClick={handleBack}
                className="flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
                data-testid="setup-back-btn"
              >
                <ChevronLeft size={16} /> Back
              </button>
            ) : (
              <div />
            )}

            <div className="flex items-center gap-3">
              {step.id === "optional" && (
                <button
                  onClick={handleSkipOptional}
                  disabled={saving}
                  className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
                  data-testid="setup-skip-btn"
                >
                  Skip for now
                </button>
              )}

              {step.id === "done" ? (
                <button
                  onClick={handleFinish}
                  className="flex items-center gap-2 bg-red-600 hover:bg-red-500 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
                  data-testid="setup-finish-btn"
                >
                  Start using OverClaw
                </button>
              ) : (
                <button
                  onClick={handleNext}
                  disabled={!canProceed() || saving}
                  className="flex items-center gap-2 bg-red-600 hover:bg-red-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white px-5 py-2.5 rounded-lg text-sm font-medium transition-colors"
                  data-testid="setup-next-btn"
                >
                  {saving ? (
                    <>
                      <Loader2 size={15} className="animate-spin" /> Saving...
                    </>
                  ) : (
                    <>
                      {step.id === "optional" ? "Save & Finish" : "Continue"}
                      <ChevronRight size={16} />
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Footer hint */}
        <p className="text-center text-xs text-zinc-700 mt-4">
          All keys are stored in your database and never leave your infrastructure.
        </p>
      </div>
    </div>
  );
}
