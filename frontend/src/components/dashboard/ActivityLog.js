import { Activity, Server, Users, Radio, AlertCircle, CheckCircle2 } from "lucide-react";

export function ActivityLog({ events }) {
  const list = events?.events || [];

  const getIcon = (type) => {
    if (type?.includes("gateway")) return <Server className="w-3 h-3" />;
    if (type?.includes("client")) return <Users className="w-3 h-3" />;
    if (type?.includes("channel")) return <Radio className="w-3 h-3" />;
    return <Activity className="w-3 h-3" />;
  };

  const getColor = (type) => {
    if (type?.includes("error")) return "text-rose-400";
    if (type?.includes("warning")) return "text-amber-400";
    if (type?.includes("start") || type?.includes("auth")) return "text-emerald-400";
    if (type?.includes("disconnect")) return "text-zinc-500";
    return "text-blue-400";
  };

  return (
    <div data-testid="activity-log" className="bg-zinc-900/60 border border-zinc-800/60 rounded-lg overflow-hidden hover:border-zinc-700/80 transition-colors h-full flex flex-col">
      <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-zinc-400" />
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-widest">Activity</span>
        </div>
        <span className="text-xs font-mono text-zinc-600">{list.length} events</span>
      </div>
      <div className="flex-1 overflow-auto divide-y divide-zinc-800/30">
        {list.length === 0 ? (
          <div className="px-5 py-8 text-center text-zinc-600 text-sm">
            No recent activity
          </div>
        ) : (
          [...list].reverse().map((event, i) => (
            <div key={i} className="flex items-start gap-3 px-4 py-2.5 hover:bg-white/[0.02] transition-colors">
              <span className={`mt-0.5 ${getColor(event.type)}`}>
                {getIcon(event.type)}
              </span>
              <div className="flex-1 min-w-0">
                <span className="text-xs text-zinc-300 block truncate">{event.detail}</span>
                <span className="text-[10px] text-zinc-600 font-mono">
                  {event.timestamp ? formatTime(event.timestamp) : "—"}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function formatTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "—";
  }
}
