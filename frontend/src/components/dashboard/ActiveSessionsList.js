import { Users, MessageSquare } from "lucide-react";

export function ActiveSessionsList({ sessions }) {
  const list = sessions?.sessions || [];

  return (
    <div data-testid="sessions-list" className="bg-zinc-900/60 border border-zinc-800/60 rounded-lg overflow-hidden hover:border-zinc-700/80 transition-colors">
      <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-zinc-400" />
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-widest">Active Sessions</span>
        </div>
        <span className="text-xs font-mono text-zinc-500">{list.length} session{list.length !== 1 ? "s" : ""}</span>
      </div>
      <div className="divide-y divide-zinc-800/40">
        {list.length === 0 ? (
          <div className="px-5 py-8 text-center text-zinc-600 text-sm">
            No active sessions
          </div>
        ) : (
          list.map((session, i) => (
            <div key={session.session_id || i} className="flex items-center justify-between px-5 py-3 hover:bg-white/[0.02] transition-colors">
              <div className="flex items-center gap-3">
                <MessageSquare className="w-3.5 h-3.5 text-zinc-500" />
                <div>
                  <span className="text-sm text-zinc-200 font-medium">{session.session_id}</span>
                  <span className="text-xs text-zinc-600 ml-2">{session.channel}</span>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-zinc-500 font-mono">{session.messages} msgs</span>
                <StatusDot status={session.status} />
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function StatusDot({ status }) {
  const color = status === "active" ? "bg-emerald-400" : status === "idle" ? "bg-zinc-500" : "bg-amber-400";
  return (
    <div className="flex items-center gap-1.5">
      <span className={`w-1.5 h-1.5 rounded-full ${color}`} />
      <span className="text-[10px] text-zinc-500 uppercase tracking-widest">{status}</span>
    </div>
  );
}
