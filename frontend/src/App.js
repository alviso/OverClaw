import { useState, useEffect, useCallback } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useGatewayWs } from "@/hooks/useGatewayWs";
import { DashboardSidebar, DashboardHeader } from "@/components/layout/DashboardLayout";
import { ConnectionIndicator } from "@/components/dashboard/ConnectionIndicator";
import { GatewayStatusCard } from "@/components/dashboard/GatewayStatusCard";
import { ConfigViewer } from "@/components/dashboard/ConfigViewer";
import { ActiveSessionsList } from "@/components/dashboard/ActiveSessionsList";
import { ChannelStatusPanel } from "@/components/dashboard/ChannelStatusPanel";
import { ActivityLog } from "@/components/dashboard/ActivityLog";
import { QuickTestPanel } from "@/components/dashboard/QuickTestPanel";
import { ModelSelector } from "@/components/dashboard/ModelSelector";
import { SlackConfigWizard } from "@/components/dashboard/SlackConfigWizard";
import { AgentManager } from "@/components/dashboard/AgentManager";
import { SkillsManager } from "@/components/dashboard/SkillsManager";
import { MemoryPanel } from "@/components/dashboard/MemoryPanel";
import { TasksPanel } from "@/components/dashboard/TasksPanel";
import { NotificationsPanel } from "@/components/dashboard/NotificationsPanel";
import { GmailPanel } from "@/components/dashboard/GmailPanel";
import { WorkspacePanel } from "@/components/dashboard/WorkspacePanel";
import { SetupWizard } from "@/components/setup/SetupWizard";
import { RelationshipsPanel } from "@/components/dashboard/RelationshipsPanel";
import ChatPage from "@/pages/ChatPage";

const API = process.env.REACT_APP_BACKEND_URL || "";

function AdminLayout() {
  const { connected, authenticated, reconnecting, gatewayInfo, rpc, onEvent, offEvent } = useGatewayWs();
  const [collapsed, setCollapsed] = useState(false);
  const [health, setHealth] = useState(null);
  const [config, setConfig] = useState(null);
  const [sessions, setSessions] = useState(null);
  const [channels, setChannels] = useState(null);
  const [activity, setActivity] = useState(null);

  const fetchAll = useCallback(async () => {
    if (!authenticated) return;
    try {
      const [h, c, s, ch, a] = await Promise.all([
        rpc("health.get"), rpc("config.get"), rpc("sessions.list"),
        rpc("channels.status"), rpc("activity.recent"),
      ]);
      setHealth(h); setConfig(c); setSessions(s); setChannels(ch); setActivity(a);
    } catch (err) {
      console.error("RPC fetch error:", err);
    }
  }, [authenticated, rpc]);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 5000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  return (
    <div className="h-screen bg-zinc-950 text-zinc-50 flex" data-testid="gateway-dashboard">
      <DashboardSidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
      <div className="flex-1 flex flex-col min-w-0">
        <Routes>
          <Route path="/" element={
            <AdminOverview
              health={health} config={config} sessions={sessions}
              channels={channels} activity={activity} rpc={rpc}
              authenticated={authenticated} connected={connected}
              reconnecting={reconnecting} fetchAll={fetchAll}
            />
          } />
          <Route path="/agents" element={
            <>
              <DashboardHeader title="Agents" subtitle="Manage specialist agents">
                <ConnectionIndicator connected={connected} authenticated={authenticated} reconnecting={reconnecting} />
              </DashboardHeader>
              <main className="flex-1 overflow-y-auto p-6">
                <AgentManager rpc={rpc} authenticated={authenticated} />
              </main>
            </>
          } />
          <Route path="/workspace" element={
            <>
              <DashboardHeader title="Workspace" subtitle="Files, processes & custom tools">
                <ConnectionIndicator connected={connected} authenticated={authenticated} reconnecting={reconnecting} />
              </DashboardHeader>
              <main className="flex-1 overflow-y-auto p-6">
                <WorkspacePanel rpc={rpc} authenticated={authenticated} onEvent={onEvent} offEvent={offEvent} />
              </main>
            </>
          } />
          <Route path="/skills" element={
            <>
              <DashboardHeader title="Skills" subtitle="Prompt-injected capabilities">
                <ConnectionIndicator connected={connected} authenticated={authenticated} reconnecting={reconnecting} />
              </DashboardHeader>
              <main className="flex-1 overflow-y-auto p-6">
                <SkillsManager rpc={rpc} authenticated={authenticated} />
              </main>
            </>
          } />
          <Route path="/memory" element={
            <>
              <DashboardHeader title="Memory" subtitle="Long-term memory & RAG">
                <ConnectionIndicator connected={connected} authenticated={authenticated} reconnecting={reconnecting} />
              </DashboardHeader>
              <main className="flex-1 overflow-y-auto p-6">
                <MemoryPanel rpc={rpc} authenticated={authenticated} />
              </main>
            </>
          } />
          <Route path="/tasks" element={
            <>
              <DashboardHeader title="Tasks" subtitle="Scheduled automation">
                <ConnectionIndicator connected={connected} authenticated={authenticated} reconnecting={reconnecting} />
              </DashboardHeader>
              <main className="flex-1 overflow-y-auto p-6">
                <TasksPanel rpc={rpc} authenticated={authenticated} />
              </main>
            </>
          } />
          <Route path="/notifications" element={
            <>
              <DashboardHeader title="Notifications" subtitle="Alerts & events">
                <ConnectionIndicator connected={connected} authenticated={authenticated} reconnecting={reconnecting} />
              </DashboardHeader>
              <main className="flex-1 overflow-y-auto p-6">
                <NotificationsPanel rpc={rpc} authenticated={authenticated} />
              </main>
            </>
          } />
          <Route path="/gmail" element={
            <>
              <DashboardHeader title="Gmail" subtitle="Email integration">
                <ConnectionIndicator connected={connected} authenticated={authenticated} reconnecting={reconnecting} />
              </DashboardHeader>
              <main className="flex-1 overflow-y-auto p-6">
                <GmailPanel />
              </main>
            </>
          } />
          <Route path="/slack" element={
            <>
              <DashboardHeader title="Slack" subtitle="Channel configuration">
                <ConnectionIndicator connected={connected} authenticated={authenticated} reconnecting={reconnecting} />
              </DashboardHeader>
              <main className="flex-1 overflow-y-auto p-6">
                <SlackConfigWizard rpc={rpc} authenticated={authenticated} onConfigChanged={fetchAll} />
              </main>
            </>
          } />
          <Route path="/config" element={
            <>
              <DashboardHeader title="Configuration" subtitle="Gateway settings">
                <ModelSelector rpc={rpc} authenticated={authenticated} />
                <ConnectionIndicator connected={connected} authenticated={authenticated} reconnecting={reconnecting} />
              </DashboardHeader>
              <main className="flex-1 overflow-y-auto p-6">
                <ConfigViewer config={config} />
              </main>
            </>
          } />
        </Routes>
      </div>
    </div>
  );
}

function AdminOverview({ health, config, sessions, channels, activity, rpc, authenticated, connected, reconnecting, fetchAll }) {
  return (
    <>
      <DashboardHeader title="Overview" subtitle="System health & activity">
        <ModelSelector rpc={rpc} authenticated={authenticated} />
        <ConnectionIndicator connected={connected} authenticated={authenticated} reconnecting={reconnecting} />
      </DashboardHeader>
      <main className="flex-1 overflow-y-auto p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div className="animate-fade-in" style={{ animationDelay: "0ms" }}>
            <GatewayStatusCard health={health} />
          </div>
          <div className="animate-fade-in" style={{ animationDelay: "60ms" }}>
            <ChannelStatusPanel channels={channels} />
          </div>
          <div className="animate-fade-in" style={{ animationDelay: "120ms" }}>
            <ActiveSessionsList sessions={sessions} />
          </div>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4">
          <div className="lg:col-span-2 animate-fade-in" style={{ animationDelay: "180ms" }}>
            <QuickTestPanel rpc={rpc} authenticated={authenticated} />
          </div>
          <div className="animate-fade-in" style={{ animationDelay: "240ms" }}>
            <ActivityLog events={activity} />
          </div>
        </div>
      </main>
    </>
  );
}

function App() {
  const [setupNeeded, setSetupNeeded] = useState(null); // null = loading, true/false

  useEffect(() => {
    fetch(`${API}/api/setup/status`)
      .then((r) => r.json())
      .then((data) => setSetupNeeded(data.needs_setup))
      .catch(() => setSetupNeeded(false)); // If backend is down, don't block with wizard
  }, []);

  if (setupNeeded === null) {
    // Loading state
    return (
      <div className="h-screen bg-zinc-950 flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-zinc-700 border-t-red-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (setupNeeded) {
    return <SetupWizard onComplete={() => setSetupNeeded(false)} />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/admin/*" element={<AdminLayout />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
