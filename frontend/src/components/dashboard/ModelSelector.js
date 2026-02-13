import { useState, useEffect } from "react";
import { ChevronDown, Cpu } from "lucide-react";

export function ModelSelector({ rpc, authenticated }) {
  const [models, setModels] = useState([]);
  const [current, setCurrent] = useState("");
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    if (!authenticated) return;
    rpc("models.list").then(result => {
      if (result?.models) setModels(result.models);
      if (result?.current) setCurrent(result.current);
    }).catch(() => {});
  }, [authenticated, rpc]);

  const handleSwitch = async (modelId) => {
    setSwitching(true);
    setOpen(false);
    try {
      await rpc("config.set", { path: "agent.model", value: modelId });
      setCurrent(modelId);
    } catch (err) {
      console.error("Model switch failed:", err);
    } finally {
      setSwitching(false);
    }
  };

  const currentModel = models.find(m => m.id === current);
  const displayName = currentModel ? `${currentModel.provider}/${currentModel.model}` : current || "Loading...";
  const providerColor = current?.startsWith("anthropic") ? "text-orange-400" : "text-emerald-400";

  return (
    <div className="relative" data-testid="model-selector">
      <button
        onClick={() => setOpen(!open)}
        disabled={switching}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-zinc-800/60 border border-zinc-700/50 hover:border-zinc-600 text-xs transition-colors disabled:opacity-50"
      >
        <Cpu className={`w-3.5 h-3.5 ${providerColor}`} />
        <span className={`font-mono ${providerColor}`}>
          {switching ? "switching..." : displayName}
        </span>
        <ChevronDown className={`w-3 h-3 text-zinc-500 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-1 z-50 w-72 bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl overflow-hidden">
            {models.map(m => {
              const isActive = m.id === current;
              const color = m.provider === "anthropic" ? "text-orange-400" : "text-emerald-400";
              return (
                <button
                  key={m.id}
                  onClick={() => handleSwitch(m.id)}
                  data-testid={`model-option-${m.id}`}
                  className={`w-full text-left px-4 py-2.5 flex items-center justify-between hover:bg-zinc-800/80 transition-colors ${isActive ? "bg-zinc-800/50" : ""}`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full ${isActive ? "bg-emerald-400" : "bg-zinc-600"}`} />
                    <span className={`text-xs font-mono ${color}`}>{m.id}</span>
                  </div>
                  <span className="text-[10px] text-zinc-600 uppercase">{m.provider}</span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
