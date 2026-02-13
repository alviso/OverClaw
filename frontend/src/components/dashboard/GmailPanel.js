import { useState, useEffect, useCallback } from "react";
import { Mail, ExternalLink, Unplug } from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

export function GmailPanel() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/oauth/gmail/status`);
      const data = await res.json();
      setStatus(data);
    } catch (err) {
      console.error("Gmail status error:", err);
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
    window.open(`${API_URL}/api/oauth/gmail/login`, "_blank", "width=600,height=700");
    // Poll for status change
    const poll = setInterval(async () => {
      const res = await fetch(`${API_URL}/api/oauth/gmail/status`);
      const data = await res.json();
      if (data.connected) {
        setStatus(data);
        clearInterval(poll);
      }
    }, 2000);
    // Stop polling after 5 minutes
    setTimeout(() => clearInterval(poll), 300000);
  };

  const handleDisconnect = async () => {
    try {
      await fetch(`${API_URL}/api/oauth/gmail/disconnect`, { method: "POST" });
      setStatus({ connected: false });
    } catch (err) {
      console.error("Gmail disconnect error:", err);
    }
  };

  return (
    <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/50 p-5" data-testid="gmail-panel">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center justify-center">
            <Mail className="w-4 h-4 text-red-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-zinc-100">Gmail Integration</h3>
            <p className="text-[10px] text-zinc-600 uppercase tracking-wider">OAuth 2.0</p>
          </div>
        </div>
        <div className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider ${
          status?.connected
            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
            : "bg-zinc-800 text-zinc-500 border border-zinc-700"
        }`}>
          {loading ? "..." : status?.connected ? "connected" : "disconnected"}
        </div>
      </div>

      {status?.connected ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-800/50 border border-zinc-700/50">
            <Mail className="w-3.5 h-3.5 text-zinc-400" />
            <span className="text-xs text-zinc-300 font-mono">{status.email}</span>
          </div>
          {status.connected_at && (
            <p className="text-[10px] text-zinc-600">
              Connected: {new Date(status.connected_at).toLocaleDateString()}
            </p>
          )}
          <p className="text-xs text-zinc-500">
            The assistant can now read, search, and send emails on your behalf.
          </p>
          <button
            onClick={handleDisconnect}
            data-testid="gmail-disconnect-btn"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-red-400 hover:text-red-300 bg-red-500/5 hover:bg-red-500/10 border border-red-500/10 transition-colors"
          >
            <Unplug className="w-3 h-3" />
            Disconnect
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-zinc-500 leading-relaxed">
            Connect your Gmail account to let the assistant read, search, and send emails.
            Uses OAuth 2.0 — your password is never stored.
          </p>
          <button
            onClick={handleConnect}
            data-testid="gmail-connect-btn"
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium text-white bg-red-600 hover:bg-red-500 transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Connect Gmail
          </button>
          <p className="text-[10px] text-zinc-600 leading-relaxed">
            Requires Google Cloud OAuth credentials (GOOGLE_CLIENT_ID & GOOGLE_CLIENT_SECRET) in the backend .env file.
          </p>
        </div>
      )}
    </div>
  );
}
