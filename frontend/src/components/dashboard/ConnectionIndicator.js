import { Activity, CheckCircle2, AlertCircle, WifiOff, RefreshCw } from "lucide-react";

export function ConnectionIndicator({ connected, authenticated, reconnecting }) {
  // During seamless reconnect, show a subtle "syncing" state instead of DISCONNECTED
  if (reconnecting) {
    return (
      <div data-testid="connection-indicator" className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-zinc-800/60 border border-zinc-700/40">
        <RefreshCw className="w-3.5 h-3.5 text-zinc-400 animate-spin" style={{ animationDuration: "1.5s" }} />
        <span className="text-xs font-medium text-zinc-400 tracking-wide">SYNCING</span>
      </div>
    );
  }
  if (!connected) {
    return (
      <div data-testid="connection-indicator" className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-rose-400/10 border border-rose-400/20">
        <WifiOff className="w-3.5 h-3.5 text-rose-400" />
        <span className="text-xs font-medium text-rose-400 tracking-wide">DISCONNECTED</span>
      </div>
    );
  }
  if (!authenticated) {
    return (
      <div data-testid="connection-indicator" className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-400/10 border border-amber-400/20">
        <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
        <span className="text-xs font-medium text-amber-400 tracking-wide">AUTHENTICATING</span>
      </div>
    );
  }
  return (
    <div data-testid="connection-indicator" className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-400/10 border border-emerald-400/20">
      <span className="relative flex h-2.5 w-2.5">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-50"></span>
        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-400"></span>
      </span>
      <span className="text-xs font-medium text-emerald-400 tracking-wide">CONNECTED</span>
    </div>
  );
}
