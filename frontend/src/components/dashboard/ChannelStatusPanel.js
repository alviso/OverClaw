import { Radio, Hash, MessageCircle } from "lucide-react";

export function ChannelStatusPanel({ channels }) {
  const list = channels?.channels || [];

  return (
    <div data-testid="channels-panel" className="bg-zinc-900/60 border border-zinc-800/60 rounded-lg overflow-hidden hover:border-zinc-700/80 transition-colors">
      <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-2">
          <Radio className="w-4 h-4 text-zinc-400" />
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-widest">Channels</span>
        </div>
      </div>
      <div className="p-4 grid grid-cols-2 gap-3">
        {list.length === 0 ? (
          <div className="col-span-2 text-center text-zinc-600 text-sm py-4">
            No channels configured
          </div>
        ) : (
          list.map((ch) => (
            <ChannelCard key={ch.id} channel={ch} />
          ))
        )}
      </div>
    </div>
  );
}

function ChannelCard({ channel }) {
  const statusColor = channel.status === "active"
    ? "border-emerald-400/20 bg-emerald-400/5"
    : channel.status === "configured"
    ? "border-amber-400/20 bg-amber-400/5"
    : "border-zinc-700/50 bg-zinc-800/30";

  const statusText = channel.status === "active"
    ? "text-emerald-400"
    : channel.status === "configured"
    ? "text-amber-400"
    : "text-zinc-500";

  const Icon = channel.id === "slack" ? Hash : MessageCircle;

  return (
    <div data-testid={`channel-${channel.id}`} className={`border rounded-lg p-3 ${statusColor} transition-colors`}>
      <div className="flex items-center gap-2 mb-2">
        <Icon className={`w-4 h-4 ${statusText}`} />
        <span className="text-sm font-medium text-zinc-200">{channel.name}</span>
      </div>
      <div className="flex items-center justify-between">
        <span className={`text-[10px] uppercase tracking-widest font-medium ${statusText}`}>
          {channel.status.replace("_", " ")}
        </span>
        {channel.enabled && (
          <span className="text-[10px] text-zinc-500 uppercase tracking-widest">enabled</span>
        )}
      </div>
    </div>
  );
}
