import { useState, useCallback, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useGatewayWs } from "@/hooks/useGatewayWs";
import { ChatView } from "@/components/chat/ChatView";
import { SessionSidebar } from "@/components/chat/SessionSidebar";
import { Shield, Settings, PanelLeftClose, PanelLeft, Bell } from "lucide-react";

export default function ChatPage() {
  const { connected, authenticated, reconnecting, gatewayInfo, rpc, latestNotification, onEvent, offEvent } = useGatewayWs();
  const [currentSession, setCurrentSession] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [hasUnread, setHasUnread] = useState(false);
  const sessionCreatingRef = useRef(false);

  // Create or load a default session
  useEffect(() => {
    if (!authenticated || currentSession || sessionCreatingRef.current) return;
    sessionCreatingRef.current = true;
    rpc("sessions.list").then((r) => {
      if (r?.sessions?.length > 0) {
        const sorted = [...r.sessions].sort((a, b) =>
          (b.last_active || "").localeCompare(a.last_active || "")
        );
        setCurrentSession(sorted[0].session_id);
      }
      sessionCreatingRef.current = false;
    }).catch(() => { sessionCreatingRef.current = false; });
  }, [authenticated, currentSession, rpc]);

  useEffect(() => {
    if (latestNotification) setHasUnread(true);
  }, [latestNotification]);

  const handleNewSession = useCallback(async (agentId) => {
    const ts = Date.now();
    const sessionId = `chat-${ts}`;
    await rpc("chat.send", {
      session_id: sessionId,
      message: "",
      agent_id: agentId || "default",
    }).catch(() => {});
    setCurrentSession(sessionId);
  }, [rpc]);

  return (
    <div className="h-screen bg-zinc-950 flex" data-testid="chat-page">
      {/* Sidebar */}
      <div className={`transition-all duration-300 flex-shrink-0 ${sidebarOpen ? "w-64" : "w-0"} overflow-hidden`}>
        <SessionSidebar
          rpc={rpc}
          authenticated={authenticated}
          currentSession={currentSession}
          onSelectSession={setCurrentSession}
          onNewSession={handleNewSession}
        />
      </div>

      {/* Main area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-14 flex items-center justify-between px-4 border-b border-zinc-800/60 flex-shrink-0 bg-zinc-950/80 backdrop-blur-sm" data-testid="chat-header">
          <div className="flex items-center gap-3">
            <button
              data-testid="toggle-sidebar-btn"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-2 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 transition-colors"
            >
              {sidebarOpen ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeft className="w-4 h-4" />}
            </button>
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center">
                <Shield className="w-3.5 h-3.5 text-indigo-400" />
              </div>
              <span className="text-sm font-semibold text-zinc-200 tracking-tight" style={{ fontFamily: 'var(--font-heading)' }}>
                OVERCLAW
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Connection status */}
            <div className="flex items-center gap-2 mr-2">
              <div className={`w-1.5 h-1.5 rounded-full ${
                connected && authenticated ? "bg-emerald-400 animate-pulse-glow" :
                reconnecting ? "bg-amber-400 animate-pulse" : "bg-zinc-600"
              }`} />
              <span className="text-[10px] text-zinc-600 uppercase tracking-wider font-mono">
                {connected && authenticated ? "live" : reconnecting ? "reconnecting" : "offline"}
              </span>
            </div>

            {/* Notifications */}
            <button
              data-testid="notifications-btn"
              onClick={() => setHasUnread(false)}
              className="relative p-2 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 transition-colors"
            >
              <Bell className="w-4 h-4" />
              {hasUnread && <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-indigo-500 rounded-full" />}
            </button>

            {/* Admin link */}
            <Link
              to="/admin"
              data-testid="admin-link"
              className="p-2 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 transition-colors"
              title="Admin Dashboard"
            >
              <Settings className="w-4 h-4" />
            </Link>
          </div>
        </header>

        {/* Chat area */}
        <div className="flex-1 min-h-0">
          <ChatView
            rpc={rpc}
            authenticated={authenticated}
            sessionId={currentSession}
            connected={connected}
            onEvent={onEvent}
            offEvent={offEvent}
          />
        </div>
      </div>
    </div>
  );
}
