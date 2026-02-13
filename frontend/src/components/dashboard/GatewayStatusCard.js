import { Server, Clock, Cpu, Activity } from "lucide-react";

export function GatewayStatusCard({ health }) {
  const isHealthy = health?.status === "healthy";

  return (
    <div data-testid="gateway-status-card" className="bg-zinc-900/60 border border-zinc-800/60 rounded-lg p-5 hover:border-zinc-700/80 transition-colors">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Server className="w-4 h-4 text-zinc-400" />
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-widest">Gateway Health</span>
        </div>
        {isHealthy ? (
          <span className="text-xs font-semibold text-emerald-400 bg-emerald-400/10 px-2.5 py-0.5 rounded-full border border-emerald-400/20">
            HEALTHY
          </span>
        ) : (
          <span className="text-xs font-semibold text-amber-400 bg-amber-400/10 px-2.5 py-0.5 rounded-full border border-amber-400/20">
            {health ? "DEGRADED" : "LOADING"}
          </span>
        )}
      </div>

      <div className="grid grid-cols-3 gap-4">
        <MetricCell
          icon={<Clock className="w-3.5 h-3.5" />}
          label="Uptime"
          value={health?.uptime || "—"}
        />
        <MetricCell
          icon={<Activity className="w-3.5 h-3.5" />}
          label="Version"
          value={health?.version || "—"}
        />
        <MetricCell
          icon={<Cpu className="w-3.5 h-3.5" />}
          label="Memory"
          value={health?.system ? `${health.system.memory_percent}%` : "—"}
        />
      </div>
    </div>
  );
}

function MetricCell({ icon, label, value }) {
  return (
    <div className="text-center">
      <div className="flex items-center justify-center gap-1.5 text-zinc-500 mb-1">
        {icon}
        <span className="text-[10px] uppercase tracking-widest">{label}</span>
      </div>
      <span className="text-sm font-semibold text-zinc-100 font-mono">{value}</span>
    </div>
  );
}
