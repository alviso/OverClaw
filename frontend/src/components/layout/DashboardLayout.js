import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  LayoutDashboard, Bot, Zap, Brain, Calendar, Bell,
  Mail, Hash, Settings, ChevronLeft, ChevronRight,
  Activity, MessageSquare, Shield, FolderCode,
} from "lucide-react";

const NAV_ITEMS = [
  { id: "overview", label: "Overview", icon: LayoutDashboard, path: "/admin" },
  { id: "workspace", label: "Workspace", icon: FolderCode, path: "/admin/workspace" },
  { id: "agents", label: "Agents", icon: Bot, path: "/admin/agents" },
  { id: "skills", label: "Skills", icon: Zap, path: "/admin/skills" },
  { id: "memory", label: "Memory", icon: Brain, path: "/admin/memory" },
  { id: "tasks", label: "Tasks", icon: Calendar, path: "/admin/tasks" },
  { id: "notifications", label: "Notifications", icon: Bell, path: "/admin/notifications" },
  { id: "gmail", label: "Gmail", icon: Mail, path: "/admin/gmail" },
  { id: "slack", label: "Slack", icon: Hash, path: "/admin/slack" },
  { id: "config", label: "Config", icon: Settings, path: "/admin/config" },
];

export function DashboardSidebar({ collapsed, onToggle }) {
  const location = useLocation();

  return (
    <aside
      data-testid="admin-sidebar"
      className={`h-full border-r border-zinc-800/60 flex flex-col bg-zinc-950 transition-all duration-300 ${
        collapsed ? "w-16" : "w-56"
      }`}
    >
      {/* Logo */}
      <div className="h-16 flex items-center gap-3 px-4 border-b border-zinc-800/60">
        <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center flex-shrink-0">
          <Shield className="w-4 h-4 text-indigo-400" />
        </div>
        {!collapsed && (
          <div className="animate-fade-in">
            <div className="text-sm font-semibold text-zinc-100 tracking-tight" style={{ fontFamily: 'var(--font-heading)' }}>
              OVERCLAW
            </div>
            <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-mono">admin</div>
          </div>
        )}
      </div>

      {/* Chat link */}
      <div className="px-3 pt-3 pb-1">
        <Link
          to="/"
          data-testid="sidebar-chat-link"
          className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all
            bg-indigo-600/10 border border-indigo-500/20 text-indigo-300 hover:bg-indigo-600/20`}
        >
          <MessageSquare className="w-4 h-4 flex-shrink-0" />
          {!collapsed && <span>Open Chat</span>}
        </Link>
      </div>

      {/* Nav items */}
      <nav className="flex-1 px-3 py-2 space-y-0.5 overflow-y-auto">
        {NAV_ITEMS.map(item => {
          const isActive = location.pathname === item.path ||
            (item.path === "/admin" && location.pathname === "/admin");
          return (
            <Link
              key={item.id}
              to={item.path}
              data-testid={`sidebar-nav-${item.id}`}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all group relative ${
                isActive
                  ? "bg-zinc-800/80 text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40"
              }`}
            >
              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-r bg-indigo-500" />
              )}
              <item.icon className={`w-4 h-4 flex-shrink-0 ${isActive ? "text-indigo-400" : "text-zinc-600 group-hover:text-zinc-400"}`} />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Collapse toggle */}
      <div className="px-3 py-3 border-t border-zinc-800/60">
        <button
          data-testid="sidebar-toggle"
          onClick={onToggle}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/40 transition-colors"
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}

export function DashboardHeader({ title, subtitle, children }) {
  return (
    <header
      data-testid="admin-header"
      className="h-16 border-b border-zinc-800/60 px-6 flex items-center justify-between flex-shrink-0 bg-zinc-950/80 backdrop-blur-sm"
    >
      <div>
        <h1 className="text-base font-semibold text-zinc-100" style={{ fontFamily: 'var(--font-heading)' }}>
          {title}
        </h1>
        {subtitle && <p className="text-[10px] text-zinc-600 uppercase tracking-widest">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-3">
        {children}
      </div>
    </header>
  );
}
