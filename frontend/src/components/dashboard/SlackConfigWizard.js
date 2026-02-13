import { useState, useEffect } from "react";
import { Hash, ExternalLink, Eye, EyeOff, CheckCircle2, AlertCircle, Loader2, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";

const STEPS = [
  {
    title: "Create a Slack App",
    instruction: "Go to api.slack.com/apps and click 'Create New App' → 'From scratch'. Name it anything (e.g., 'OverClaw').",
    link: "https://api.slack.com/apps",
  },
  {
    title: "Enable Socket Mode",
    instruction: "In your app settings → Socket Mode → toggle it ON. Generate an app-level token with 'connections:write' scope. Copy the xapp-... token.",
  },
  {
    title: "Add Bot Scopes",
    instruction: "Go to OAuth & Permissions → Bot Token Scopes. Add: chat:write, app_mentions:read, channels:history, groups:history, im:history, mpim:history.",
  },
  {
    title: "Subscribe to Events",
    instruction: "Go to Event Subscriptions → toggle ON. Subscribe to bot events: message.channels, message.groups, message.im, message.mpim, app_mention.",
  },
  {
    title: "Install to Workspace",
    instruction: "Go to Install App → Install to Workspace. Copy the Bot User OAuth Token (xoxb-...).",
  },
];

export function SlackConfigWizard({ rpc, authenticated, onConfigChanged }) {
  const [botToken, setBotToken] = useState("");
  const [appToken, setAppToken] = useState("");
  const [showBotToken, setShowBotToken] = useState(false);
  const [showAppToken, setShowAppToken] = useState(false);
  const [saving, setSaving] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [status, setStatus] = useState(null); // { type: 'success'|'error', message }
  const [slackStatus, setSlackStatus] = useState(null);
  const [stepsOpen, setStepsOpen] = useState(false);
  const [currentConfig, setCurrentConfig] = useState(null);

  // Load current config
  useEffect(() => {
    if (!authenticated) return;
    rpc("config.get").then(cfg => {
      setCurrentConfig(cfg?.channels?.slack);
      if (cfg?.channels?.slack?.bot_token) {
        setBotToken(cfg.channels.slack.bot_token);
      }
      if (cfg?.channels?.slack?.app_token) {
        setAppToken(cfg.channels.slack.app_token);
      }
    }).catch(() => {});

    rpc("channels.status").then(r => {
      const slack = r?.channels?.find(c => c.id === "slack");
      setSlackStatus(slack);
    }).catch(() => {});
  }, [authenticated, rpc]);

  const isConfigured = botToken && appToken && botToken.startsWith("xoxb-") && appToken.startsWith("xapp-");
  const isConnected = slackStatus?.connected;

  const handleSave = async () => {
    if (!botToken.trim() || !appToken.trim()) {
      setStatus({ type: "error", message: "Both tokens are required" });
      return;
    }
    if (!botToken.startsWith("xoxb-")) {
      setStatus({ type: "error", message: "Bot token should start with xoxb-" });
      return;
    }
    if (!appToken.startsWith("xapp-")) {
      setStatus({ type: "error", message: "App token should start with xapp-" });
      return;
    }

    setSaving(true);
    setStatus(null);

    try {
      await rpc("config.set", { path: "channels.slack.bot_token", value: botToken.trim() });
      await rpc("config.set", { path: "channels.slack.app_token", value: appToken.trim() });
      await rpc("config.set", { path: "channels.slack.enabled", value: true });

      setStatus({ type: "success", message: "Slack config saved. Click 'Connect' to start." });
      onConfigChanged?.();
    } catch (err) {
      setStatus({ type: "error", message: `Save failed: ${err?.message || err}` });
    } finally {
      setSaving(false);
    }
  };

  const handleConnect = async () => {
    setRestarting(true);
    setStatus(null);

    try {
      const result = await rpc("channels.restart");
      if (result?.ok) {
        const slack = result.channels?.find(c => c.id === "slack");
        setSlackStatus(slack);
        if (slack?.connected) {
          setStatus({ type: "success", message: "Slack connected successfully!" });
        } else {
          setStatus({ type: "error", message: "Slack started but isn't connected. Check your tokens." });
        }
      } else {
        setStatus({ type: "error", message: "Restart failed" });
      }
      onConfigChanged?.();
    } catch (err) {
      setStatus({ type: "error", message: `Connect failed: ${err?.message || err}` });
    } finally {
      setRestarting(false);
    }
  };

  const handleDisable = async () => {
    setSaving(true);
    try {
      await rpc("config.set", { path: "channels.slack.enabled", value: false });
      await rpc("channels.restart");
      setSlackStatus({ ...slackStatus, connected: false, status: "disconnected" });
      setStatus({ type: "success", message: "Slack disabled" });
      onConfigChanged?.();
    } catch (err) {
      setStatus({ type: "error", message: `Disable failed: ${err?.message || err}` });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid="slack-config-wizard" className="bg-zinc-900/60 border border-zinc-800/60 rounded-lg overflow-hidden hover:border-zinc-700/80 transition-colors">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-2">
          <Hash className="w-4 h-4 text-zinc-400" />
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-widest">Slack Setup</span>
        </div>
        <StatusBadge connected={isConnected} configured={isConfigured} enabled={currentConfig?.enabled} />
      </div>

      <div className="p-5 space-y-4">
        {/* Setup Steps (collapsible) */}
        <button
          onClick={() => setStepsOpen(!stepsOpen)}
          data-testid="slack-steps-toggle"
          className="w-full flex items-center justify-between text-left px-3 py-2 rounded-lg bg-zinc-800/40 border border-zinc-700/30 hover:border-zinc-600/50 transition-colors"
        >
          <span className="text-xs text-zinc-400">
            {stepsOpen ? "Hide setup instructions" : "How to create a Slack app (5 steps)"}
          </span>
          {stepsOpen ? <ChevronUp className="w-3.5 h-3.5 text-zinc-500" /> : <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />}
        </button>

        {stepsOpen && (
          <div className="space-y-3 pl-1">
            {STEPS.map((step, i) => (
              <div key={i} className="flex items-start gap-3">
                <span className="w-5 h-5 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <span className="text-[10px] font-mono text-zinc-400">{i + 1}</span>
                </span>
                <div>
                  <p className="text-xs font-medium text-zinc-300">{step.title}</p>
                  <p className="text-[11px] text-zinc-500 mt-0.5 leading-relaxed">{step.instruction}</p>
                  {step.link && (
                    <a
                      href={step.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] text-blue-400 hover:text-blue-300 mt-1"
                    >
                      <ExternalLink className="w-3 h-3" />
                      {step.link.replace("https://", "")}
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Token Inputs */}
        <div className="space-y-3">
          <TokenInput
            label="Bot Token"
            placeholder="xoxb-..."
            value={botToken}
            onChange={setBotToken}
            show={showBotToken}
            onToggleShow={() => setShowBotToken(!showBotToken)}
            testId="slack-bot-token"
            valid={botToken.startsWith("xoxb-")}
          />
          <TokenInput
            label="App Token"
            placeholder="xapp-..."
            value={appToken}
            onChange={setAppToken}
            show={showAppToken}
            onToggleShow={() => setShowAppToken(!showAppToken)}
            testId="slack-app-token"
            valid={appToken.startsWith("xapp-")}
          />
        </div>

        {/* Status message */}
        {status && (
          <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs ${
            status.type === "success"
              ? "bg-emerald-400/10 border border-emerald-400/20 text-emerald-400"
              : "bg-rose-400/10 border border-rose-400/20 text-rose-400"
          }`}>
            {status.type === "success" ? <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" /> : <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />}
            {status.message}
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex items-center gap-2 pt-1">
          <button
            data-testid="slack-save-btn"
            onClick={handleSave}
            disabled={saving || !botToken.trim() || !appToken.trim()}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-zinc-100 text-zinc-900 text-xs font-semibold hover:bg-zinc-200 disabled:opacity-30 disabled:cursor-not-allowed active:scale-[0.98] transition-transform"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            Save Config
          </button>
          <button
            data-testid="slack-connect-btn"
            onClick={handleConnect}
            disabled={restarting || !isConfigured}
            className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-400/10 border border-emerald-400/20 text-emerald-400 text-xs font-semibold hover:bg-emerald-400/20 disabled:opacity-30 disabled:cursor-not-allowed active:scale-[0.98] transition-transform"
          >
            {restarting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Connect
          </button>
          {currentConfig?.enabled && (
            <button
              data-testid="slack-disable-btn"
              onClick={handleDisable}
              disabled={saving}
              className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-400 text-xs hover:text-zinc-200 hover:border-zinc-600 active:scale-[0.98] transition-transform"
            >
              Disable
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function TokenInput({ label, placeholder, value, onChange, show, onToggleShow, testId, valid }) {
  const hasValue = value.length > 0;
  return (
    <div>
      <label className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1 block">{label}</label>
      <div className="flex items-center gap-2">
        <div className="flex-1 relative">
          <input
            data-testid={testId}
            type={show ? "text" : "password"}
            value={value}
            onChange={e => onChange(e.target.value)}
            placeholder={placeholder}
            className="w-full bg-zinc-800/50 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-mono text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500 transition-colors"
          />
          {hasValue && valid && (
            <CheckCircle2 className="absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-emerald-400" />
          )}
        </div>
        <button
          onClick={onToggleShow}
          className="p-2 text-zinc-500 hover:text-zinc-300 transition-colors"
          title={show ? "Hide" : "Show"}
        >
          {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
        </button>
      </div>
    </div>
  );
}

function StatusBadge({ connected, configured, enabled }) {
  if (connected) {
    return (
      <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-400/10 px-2.5 py-0.5 rounded-full border border-emerald-400/20 uppercase tracking-wider">
        Connected
      </span>
    );
  }
  if (enabled && configured) {
    return (
      <span className="text-[10px] font-semibold text-amber-400 bg-amber-400/10 px-2.5 py-0.5 rounded-full border border-amber-400/20 uppercase tracking-wider">
        Enabled
      </span>
    );
  }
  if (configured) {
    return (
      <span className="text-[10px] font-semibold text-blue-400 bg-blue-400/10 px-2.5 py-0.5 rounded-full border border-blue-400/20 uppercase tracking-wider">
        Configured
      </span>
    );
  }
  return (
    <span className="text-[10px] font-semibold text-zinc-500 bg-zinc-800/50 px-2.5 py-0.5 rounded-full border border-zinc-700/50 uppercase tracking-wider">
      Not Set Up
    </span>
  );
}
