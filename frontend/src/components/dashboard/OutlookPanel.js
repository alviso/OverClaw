import { useState, useEffect, useCallback } from "react";
import { Mail, ExternalLink, Unplug } from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

export function OutlookPanel() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/oauth/outlook/status`);
      const data = await res.json();
      setStatus(data);
    } catch (err) {
      console.error("Outlook status error:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const handleConnect = () => {
    window.open(`${API_URL}/api/oauth/outlook/login`, "_blank", "width=600,height=700");
    const poll = setInterval(async () => {
      const res = await fetch(`${API_URL}/api/oauth/outlook/status`);
      const data = await res.json();
      if (data.connected) {
        setStatus(data);
        clearInterval(poll);
      }
    }, 2000);
    setTimeout(() => clearInterval(poll), 300000);
  };

  const handleDisconnect = async () => {
    try {
      await fetch(`${API_URL}/api/oauth/outlook/disconnect`, { method: "POST" });
      setStatus({ connected: false });
    } catch (err) {
      console.error("Outlook disconnect error:", err);
    }
  };

  return (
    <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/50 p-5" data-testid="outlook-panel">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center">
            <Mail className="w-4 h-4 text-sky-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-zinc-100">Outlook Integration</h3>
            <p className="text-xs text-zinc-500">Microsoft 365 email access</p>
          </div>
        </div>

        {status?.connected && (
          <button
            onClick={handleDisconnect}
            className="flex items-center gap-1.5 text-xs text-red-400/70 hover:text-red-400 transition-colors"
            data-testid="outlook-disconnect-btn"
          >
            <Unplug size={12} /> Disconnect
          </button>
        )}
      </div>

      {loading ? (
        <div className="h-16 flex items-center justify-center">
          <div className="w-4 h-4 border-2 border-zinc-700 border-t-sky-500 rounded-full animate-spin" />
        </div>
      ) : status?.connected ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500" />
            <span className="text-sm text-emerald-400">Connected</span>
          </div>
          <div className="bg-zinc-800/50 rounded-lg p-3 space-y-1">
            <p className="text-xs text-zinc-500">Account</p>
            <p className="text-sm text-zinc-200 font-mono">{status.email}</p>
            {status.display_name && (
              <p className="text-xs text-zinc-500">{status.display_name}</p>
            )}
          </div>
          <p className="text-xs text-zinc-600">
            The agent can search, read, and send emails on your behalf. Ask it to "check my Outlook inbox" or "search my email for budget report".
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-zinc-500 leading-relaxed">
            Connect your Microsoft 365 account to let OverClaw read, search, and send Outlook emails on your behalf. Requires Azure AD app registration with Client ID and Secret configured in settings.
          </p>
          <button
            onClick={handleConnect}
            className="flex items-center gap-2 bg-sky-600 hover:bg-sky-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            data-testid="outlook-connect-btn"
          >
            <ExternalLink size={14} /> Connect Microsoft Account
          </button>
        </div>
      )}
    </div>
  );
}
