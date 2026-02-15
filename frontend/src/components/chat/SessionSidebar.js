import { useState, useEffect, useCallback } from "react";
import { Plus, MessageSquare, Trash2, Bot, ChevronDown, Hash } from "lucide-react";

function timeAgo(isoString) {
  if (!isoString) return "";
  try {
    const now = Date.now();
    const then = new Date(isoString).getTime();
    const diff = Math.floor((now - then) / 1000);
    if (diff < 60) return "now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
    if (diff < 604800) return `${Math.floor(diff / 86400)}d`;
    return new Date(isoString).toLocaleDateString();
  } catch {
    return "";
  }
}

function parseSessionId(sessionId) {
  if (sessionId.startsWith("slack:")) {
    const parts = sessionId.split(":");
    return {
      type: "slack",
      label: `#${parts[1]?.slice(-4) || "chan"}`,
      sublabel: `Slack`,
    };
  }
  return { type: "webchat", label: null, sublabel: null };
}

export function SessionSidebar({ rpc, authenticated, currentSession, onSelectSession, onNewSession }) {
  const [sessions, setSessions] = useState([]);
  const [agents, setAgents] = useState([]);
  const [showNewChat, setShowNewChat] = useState(false);

  const fetchData = useCallback(() => {
    if (!authenticated) return;
    rpc("sessions.list").then(r => {
      if (r?.sessions) setSessions(r.sessions);
    }).catch(() => {});
    rpc("agents.list").then(r => {
      if (r?.agents) setAgents(r.agents);
    }).catch(() => {});
  }, [authenticated, rpc]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleDelete = async (e, sessionId) => {
    e.stopPropagation();
    await rpc("chat.delete", { session_id: sessionId });
    const remaining = sessions.filter(s => s.session_id !== sessionId);
    if (sessionId === currentSession && remaining.length > 0) {
      const sorted = [...remaining].sort((a, b) =>
        (b.last_active || "").localeCompare(a.last_active || "")
      );
      onSelectSession(sorted[0].session_id);
    }
    fetchData();
  };

  const handleNewWithAgent = (agentId) => {
    setShowNewChat(false);
    onNewSession(agentId);
  };

  const agentMap = {};
  agents.forEach(a => { agentMap[a.id] = a; });

  const sortedSessions = [...sessions].sort((a, b) =>
    (b.last_active || b.created_at || "").localeCompare(a.last_active || a.created_at || "")
  );

  return (
    <div data-testid="session-sidebar" className="w-64 h-full bg-zinc-950 border-r border-zinc-800/60 flex flex-col">
      {/* New Chat */}
      <div className="p-3 border-b border-zinc-800/60">
        <button
          data-testid="new-session-btn"
          onClick={() => setShowNewChat(!showNewChat)}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 text-sm text-white font-medium hover:bg-indigo-500 transition-all shadow-lg shadow-indigo-500/20 active:scale-[0.97]"
        >
          <Plus className="w-4 h-4" />
          New Chat
          <ChevronDown className={`w-3.5 h-3.5 text-indigo-200 transition-transform ${showNewChat ? "rotate-180" : ""}`} />
        </button>

        {showNewChat && (
          <div className="mt-2 border border-zinc-800 rounded-lg overflow-hidden bg-zinc-900/80 animate-fade-in" data-testid="agent-picker">
            <div className="px-3 py-2 border-b border-zinc-800/50">
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest">Choose agent</span>
            </div>
            {agents.map(agent => (
              <button
                key={agent.id}
                data-testid={`pick-agent-${agent.id}`}
                onClick={() => handleNewWithAgent(agent.id)}
                className="w-full text-left px-3 py-2.5 flex items-center gap-3 hover:bg-zinc-800/60 transition-colors"
              >
                <div className="w-6 h-6 rounded-md bg-indigo-600/10 border border-indigo-500/20 flex items-center justify-center flex-shrink-0">
                  <Bot className="w-3 h-3 text-indigo-400" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-zinc-200 truncate">{agent.name}</div>
                  <div className="text-[10px] font-mono text-zinc-600">{agent.model}</div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Sessions */}
      <div className="flex-1 overflow-y-auto py-1">
        {sortedSessions.length === 0 ? (
          <div className="text-center py-12 text-xs text-zinc-600">No sessions yet</div>
        ) : (
          sortedSessions.map(s => {
            const isActive = s.session_id === currentSession;
            const agentId = s.agent_id || "default";
            const agent = agentMap[agentId];
            const agentName = agent?.name || agentId;
            const lastTime = timeAgo(s.last_active || s.created_at);

            return (
              <div
                key={s.session_id}
                data-testid={`session-${s.session_id}`}
                onClick={() => onSelectSession(s.session_id)}
                role="button"
                tabIndex={0}
                className={`w-full text-left px-3 py-2.5 flex items-center gap-2.5 hover:bg-zinc-800/40 transition-all group cursor-pointer relative ${
                  isActive ? "bg-zinc-800/60" : ""
                }`}
              >
                {isActive && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6 rounded-r bg-indigo-500" />
                )}
                <MessageSquare className={`w-3.5 h-3.5 flex-shrink-0 ${isActive ? "text-indigo-400" : "text-zinc-700"}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <span className={`text-xs truncate ${isActive ? "text-zinc-100 font-medium" : "text-zinc-400"}`}>
                      {s.session_id}
                    </span>
                    <span className="text-[9px] text-zinc-700 flex-shrink-0 tabular-nums font-mono">{lastTime}</span>
                  </div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="text-[9px] text-zinc-600">{agentName}</span>
                    <span className="text-[9px] text-zinc-800">|</span>
                    <span className="text-[9px] text-zinc-700">{s.messages} msgs</span>
                  </div>
                </div>
                <button
                  onClick={(e) => handleDelete(e, s.session_id)}
                  className="opacity-0 group-hover:opacity-100 p-1 text-zinc-700 hover:text-rose-400 transition-all"
                  title="Delete session"
                  data-testid={`delete-session-${s.session_id}`}
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-zinc-800/60 text-[10px] text-zinc-700 uppercase tracking-widest text-center font-mono">
        {sessions.length} sessions
      </div>
    </div>
  );
}
