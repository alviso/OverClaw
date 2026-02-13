import { useState, useEffect, useCallback } from "react";
import { Bell, Check, Trash2, Info, AlertTriangle, AlertCircle } from "lucide-react";

export function NotificationsPanel({ rpc, authenticated }) {
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);

  const fetchNotifications = useCallback(() => {
    if (!authenticated) return;
    rpc("notifications.list", { limit: 30 }).then(r => {
      if (r?.notifications) setNotifications(r.notifications);
      if (r?.unread_count !== undefined) setUnreadCount(r.unread_count);
    }).catch(() => {});
  }, [authenticated, rpc]);

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 4000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  const handleMarkAllRead = async () => {
    await rpc("notifications.mark_read", {});
    fetchNotifications();
  };

  const handleMarkRead = async (id) => {
    await rpc("notifications.mark_read", { id });
    fetchNotifications();
  };

  const handleClear = async () => {
    await rpc("notifications.clear");
    fetchNotifications();
  };

  const levelIcon = (level) => {
    switch (level) {
      case "warning": return <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />;
      case "critical": return <AlertCircle className="w-3.5 h-3.5 text-rose-400" />;
      default: return <Info className="w-3.5 h-3.5 text-blue-400" />;
    }
  };

  const levelBorder = (level) => {
    switch (level) {
      case "warning": return "border-l-amber-400";
      case "critical": return "border-l-rose-400";
      default: return "border-l-blue-400";
    }
  };

  return (
    <div className="bg-zinc-900/50 border border-zinc-800/60 rounded-xl overflow-hidden" data-testid="notifications-panel">
      <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800/40">
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <Bell className="w-4 h-4 text-violet-400" />
            {unreadCount > 0 && (
              <span className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-rose-500 text-[9px] text-white flex items-center justify-center font-bold">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </div>
          <h3 className="text-sm font-semibold text-zinc-200" style={{ fontFamily: 'Manrope, sans-serif' }}>
            Notifications
          </h3>
          {unreadCount > 0 && <span className="text-[10px] text-violet-400 font-mono">{unreadCount} unread</span>}
        </div>
        <div className="flex items-center gap-2">
          {unreadCount > 0 && (
            <button
              data-testid="mark-all-read-btn"
              onClick={handleMarkAllRead}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
            >
              <Check className="w-3 h-3" /> Mark all read
            </button>
          )}
          {notifications.length > 0 && (
            <button
              data-testid="clear-notifications-btn"
              onClick={handleClear}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] text-zinc-400 hover:text-rose-400 hover:bg-zinc-800 transition-colors"
            >
              <Trash2 className="w-3 h-3" /> Clear
            </button>
          )}
        </div>
      </div>

      <div className="max-h-[400px] overflow-y-auto divide-y divide-zinc-800/20">
        {notifications.length === 0 ? (
          <div className="px-5 py-8 text-center text-xs text-zinc-600">
            No notifications yet. Scheduled tasks will post alerts here.
          </div>
        ) : notifications.map(n => (
          <div
            key={n.id}
            data-testid={`notification-${n.id}`}
            className={`px-5 py-3 border-l-2 ${levelBorder(n.level)} ${!n.read ? "bg-zinc-800/20" : ""} hover:bg-zinc-800/30 transition-colors cursor-pointer`}
            onClick={() => !n.read && handleMarkRead(n.id)}
          >
            <div className="flex items-start gap-2.5">
              <div className="mt-0.5">{levelIcon(n.level)}</div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-medium ${!n.read ? "text-zinc-100" : "text-zinc-400"}`}>
                    {n.title}
                  </span>
                  <span className="text-[9px] text-zinc-600 font-mono flex-shrink-0">
                    {new Date(n.created_at).toLocaleTimeString()}
                  </span>
                  {!n.read && <span className="w-1.5 h-1.5 rounded-full bg-violet-400 flex-shrink-0" />}
                </div>
                <div className="text-[11px] text-zinc-500 mt-0.5 line-clamp-2">{n.body}</div>
                {n.source && (
                  <div className="text-[9px] text-zinc-600 mt-1 font-mono">{n.source}</div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
