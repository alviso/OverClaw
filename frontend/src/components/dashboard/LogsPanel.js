import { useState, useEffect, useCallback, useRef } from "react";
import { RefreshCw, Trash2, Copy, Check, Filter, X } from "lucide-react";

const LEVEL_STYLES = {
  ERROR: { bg: "bg-red-500/10", border: "border-red-500/30", text: "text-red-400", dot: "bg-red-500" },
  WARNING: { bg: "bg-amber-500/10", border: "border-amber-500/30", text: "text-amber-400", dot: "bg-amber-500" },
  CRITICAL: { bg: "bg-red-600/15", border: "border-red-600/40", text: "text-red-300", dot: "bg-red-600" },
};

export function LogsPanel({ rpc, authenticated }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [filterLevel, setFilterLevel] = useState("");
  const [filterComponent, setFilterComponent] = useState("");
  const [copiedIdx, setCopiedIdx] = useState(null);
  const [limit, setLimit] = useState(100);
  const scrollRef = useRef();

  const fetchLogs = useCallback(async () => {
    if (!authenticated) return;
    try {
      const result = await rpc("debug.logs", {
        limit,
        level: filterLevel || undefined,
        component: filterComponent || undefined,
      });
      if (result?.logs) {
        setLogs(result.logs);
      }
    } catch (err) {
      console.error("debug.logs error:", err);
    }
  }, [authenticated, rpc, limit, filterLevel, filterComponent]);

  // Initial fetch
  useEffect(() => {
    setLoading(true);
    fetchLogs().finally(() => setLoading(false));
  }, [fetchLogs]);

  // Auto-refresh every 5s
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(fetchLogs, 5000);
    return () => clearInterval(id);
  }, [autoRefresh, fetchLogs]);

  // Auto-scroll to bottom on new logs
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const clearLogs = async () => {
    try {
      await rpc("debug.clear");
      setLogs([]);
    } catch (err) {
      console.error("debug.clear error:", err);
    }
  };

  const copyEntry = (entry, idx) => {
    const text = [
      `[${entry.timestamp}] ${entry.level} ${entry.component}`,
      `${entry.func}: ${entry.message}`,
      entry.traceback ? entry.traceback.join("") : "",
    ].filter(Boolean).join("\n");
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 1500);
  };

  const copyAll = () => {
    const text = logs.map((e) => {
      let line = `[${e.timestamp}] ${e.level} ${e.component} | ${e.func}: ${e.message}`;
      if (e.traceback) line += "\n" + e.traceback.join("");
      return line;
    }).join("\n");
    navigator.clipboard.writeText(text);
    setCopiedIdx(-1);
    setTimeout(() => setCopiedIdx(null), 1500);
  };

  const errorCount = logs.filter((l) => l.level === "ERROR" || l.level === "CRITICAL").length;
  const warnCount = logs.filter((l) => l.level === "WARNING").length;

  return (
    <div className="flex flex-col h-full" data-testid="logs-panel">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800/60 gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs">
            {errorCount > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-red-500/15 text-red-400 font-medium">
                {errorCount} error{errorCount > 1 ? "s" : ""}
              </span>
            )}
            {warnCount > 0 && (
              <span className="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 font-medium">
                {warnCount} warning{warnCount > 1 ? "s" : ""}
              </span>
            )}
            <span className="text-zinc-600">{logs.length} entries</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Level filter */}
          <select
            data-testid="logs-filter-level"
            value={filterLevel}
            onChange={(e) => setFilterLevel(e.target.value)}
            className="bg-zinc-800/60 border border-zinc-700/40 rounded-md px-2 py-1 text-xs text-zinc-300 outline-none"
          >
            <option value="">All levels</option>
            <option value="WARNING">Warning</option>
            <option value="ERROR">Error</option>
            <option value="CRITICAL">Critical</option>
          </select>

          {/* Component filter */}
          <div className="relative">
            <input
              data-testid="logs-filter-component"
              type="text"
              value={filterComponent}
              onChange={(e) => setFilterComponent(e.target.value)}
              placeholder="Filter component..."
              className="bg-zinc-800/60 border border-zinc-700/40 rounded-md px-2 py-1 text-xs text-zinc-300 outline-none w-36 placeholder:text-zinc-600"
            />
            {filterComponent && (
              <button
                onClick={() => setFilterComponent("")}
                className="absolute right-1 top-1/2 -translate-y-1/2 text-zinc-600 hover:text-zinc-400"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>

          {/* Auto-refresh toggle */}
          <button
            data-testid="logs-auto-refresh"
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors ${
              autoRefresh
                ? "bg-indigo-600/20 text-indigo-400 border border-indigo-500/30"
                : "text-zinc-500 border border-zinc-700/40 hover:text-zinc-300"
            }`}
          >
            <RefreshCw className={`w-3 h-3 ${autoRefresh ? "animate-spin" : ""}`} style={autoRefresh ? { animationDuration: "3s" } : {}} />
            Live
          </button>

          <button
            data-testid="logs-copy-all"
            onClick={copyAll}
            className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-zinc-500 border border-zinc-700/40 hover:text-zinc-300 transition-colors"
          >
            {copiedIdx === -1 ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
            Copy all
          </button>

          <button
            data-testid="logs-refresh"
            onClick={() => { setLoading(true); fetchLogs().finally(() => setLoading(false)); }}
            className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-zinc-500 border border-zinc-700/40 hover:text-zinc-300 transition-colors"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          </button>

          <button
            data-testid="logs-clear"
            onClick={clearLogs}
            className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-red-500/70 border border-red-500/20 hover:text-red-400 hover:border-red-500/40 transition-colors"
          >
            <Trash2 className="w-3 h-3" />
            Clear
          </button>
        </div>
      </div>

      {/* Log entries */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto font-mono text-xs" data-testid="logs-entries">
        {logs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-zinc-600">
            {loading ? "Loading..." : "No log entries. Errors and warnings will appear here."}
          </div>
        ) : (
          <div className="divide-y divide-zinc-800/30">
            {logs.map((entry, idx) => {
              const style = LEVEL_STYLES[entry.level] || LEVEL_STYLES.WARNING;
              return (
                <div
                  key={idx}
                  data-testid={`log-entry-${idx}`}
                  className={`group px-4 py-2 hover:bg-zinc-800/30 transition-colors ${style.bg} border-l-2 ${style.border}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${style.dot}`} />
                        <span className="text-zinc-600">{formatTime(entry.timestamp)}</span>
                        <span className={`font-semibold ${style.text}`}>{entry.level}</span>
                        <span className="text-zinc-500">{entry.component}</span>
                        <span className="text-zinc-700">{entry.func}</span>
                      </div>
                      <div className="text-zinc-300 pl-3.5 break-words whitespace-pre-wrap">
                        {entry.message}
                      </div>
                      {entry.traceback && (
                        <details className="pl-3.5 mt-1">
                          <summary className="text-zinc-600 cursor-pointer hover:text-zinc-400 text-[10px]">
                            Traceback
                          </summary>
                          <pre className="text-[10px] text-red-400/80 mt-1 overflow-x-auto whitespace-pre">
                            {entry.traceback.join("")}
                          </pre>
                        </details>
                      )}
                    </div>
                    <button
                      onClick={() => copyEntry(entry, idx)}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-zinc-700/50 text-zinc-600 hover:text-zinc-300 transition-all flex-shrink-0"
                    >
                      {copiedIdx === idx ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function formatTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" })
      + "." + String(d.getMilliseconds()).padStart(3, "0");
  } catch {
    return iso;
  }
}
