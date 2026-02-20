import { useState, useEffect, useCallback } from "react";
import { Download, Upload, Brain, Database, Users, FileText, CheckCircle, AlertCircle, Loader2 } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL || "";

export function BrainPanel() {
  const [stats, setStats] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/brain/stats`);
      const data = await res.json();
      setStats(data);
    } catch (e) {
      console.error("Failed to fetch brain stats:", e);
    }
  }, []);

  useEffect(() => { fetchStats(); }, [fetchStats]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await fetch(`${API}/api/brain/export`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "overclaw-brain.json";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("Export failed:", e);
    }
    setExporting(false);
  };

  const handleImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportResult(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API}/api/brain/import`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      setImportResult(data);
      if (data.ok) fetchStats();
    } catch (err) {
      setImportResult({ ok: false, error: "Upload failed" });
    }
    setImporting(false);
    e.target.value = "";
  };

  const total = stats
    ? (stats.memories || 0) + (stats.user_profiles || 0) + (stats.relationships || 0)
      + (stats.tasks || 0) + (stats.chat_messages || 0) + (stats.sessions || 0)
    : 0;

  const STAT_ITEMS = [
    { key: "memories", label: "Memories", icon: Brain, color: "text-violet-400", bg: "bg-violet-500/10" },
    { key: "user_profiles", label: "User Profiles", icon: FileText, color: "text-sky-400", bg: "bg-sky-500/10" },
    { key: "relationships", label: "People", icon: Users, color: "text-amber-400", bg: "bg-amber-500/10" },
    { key: "tasks", label: "Tasks", icon: FileText, color: "text-emerald-400", bg: "bg-emerald-500/10" },
    { key: "conversation_sessions", label: "Conversations", icon: Users, color: "text-rose-400", bg: "bg-rose-500/10" },
  ];

  return (
    <div className="space-y-6" data-testid="brain-panel">
      {/* Header card */}
      <div className="bg-zinc-900/50 border border-zinc-800/60 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center">
              <Database className="w-5 h-5 text-indigo-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-zinc-100">Brain Export / Import</h3>
              <p className="text-xs text-zinc-500">Transfer knowledge between OverClaw deployments</p>
            </div>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold text-zinc-100">{total}</div>
            <div className="text-[10px] text-zinc-500 uppercase tracking-widest">total entries</div>
          </div>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-5 gap-3 mb-6">
          {STAT_ITEMS.map(({ key, label, icon: Icon, color, bg }) => (
            <div key={key} className="bg-zinc-800/40 rounded-lg p-3 flex items-center gap-3">
              <div className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center`}>
                <Icon className={`w-4 h-4 ${color}`} />
              </div>
              <div>
                <div className="text-lg font-bold text-zinc-100">{stats?.[key] ?? "—"}</div>
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div className="flex gap-3">
          <button
            data-testid="brain-export-btn"
            onClick={handleExport}
            disabled={exporting || total === 0}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium
              bg-indigo-600/20 border border-indigo-500/30 text-indigo-300 hover:bg-indigo-600/30 transition-colors
              disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            {exporting ? "Exporting..." : "Export Brain"}
          </button>

          <label
            data-testid="brain-import-btn"
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium
              bg-zinc-800/60 border border-zinc-700/60 text-zinc-300 hover:bg-zinc-800 transition-colors cursor-pointer
              ${importing ? "opacity-40 pointer-events-none" : ""}`}
          >
            {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            {importing ? "Importing..." : "Import Brain"}
            <input
              type="file"
              accept=".json"
              onChange={handleImport}
              className="hidden"
              disabled={importing}
            />
          </label>
        </div>
      </div>

      {/* Import result */}
      {importResult && (
        <div
          data-testid="brain-import-result"
          className={`rounded-xl p-4 border ${
            importResult.ok
              ? "bg-emerald-500/10 border-emerald-500/30"
              : "bg-red-500/10 border-red-500/30"
          }`}
        >
          <div className="flex items-center gap-2 mb-2">
            {importResult.ok ? (
              <CheckCircle className="w-4 h-4 text-emerald-400" />
            ) : (
              <AlertCircle className="w-4 h-4 text-red-400" />
            )}
            <span className={`text-sm font-semibold ${importResult.ok ? "text-emerald-300" : "text-red-300"}`}>
              {importResult.ok ? "Import successful" : "Import failed"}
            </span>
          </div>
          {importResult.ok && importResult.results && (
            <div className="grid grid-cols-3 gap-3 mt-3">
              {Object.entries(importResult.results).map(([key, val]) => (
                <div key={key} className="text-xs text-zinc-400">
                  <span className="font-medium text-zinc-300 capitalize">{key.replace("_", " ")}</span>
                  <br />
                  {val.imported} imported, {val.skipped} skipped
                </div>
              ))}
            </div>
          )}
          {importResult.error && (
            <p className="text-xs text-red-400 mt-1">{importResult.error}</p>
          )}
        </div>
      )}

      {/* Info card */}
      <div className="bg-zinc-900/30 border border-zinc-800/40 rounded-xl p-4">
        <h4 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">How it works</h4>
        <ul className="space-y-1.5 text-xs text-zinc-500">
          <li><strong className="text-zinc-400">Export</strong> downloads all memories, profile facts, and relationships as a single JSON file.</li>
          <li><strong className="text-zinc-400">Import</strong> merges the file into the current database — existing data is preserved, duplicates are skipped.</li>
          <li><strong className="text-zinc-400">Embeddings</strong> are regenerated on import if missing (requires OpenAI key).</li>
          <li><strong className="text-zinc-400">OAuth tokens</strong> are excluded — you'll need to reconnect Gmail/Outlook on the new machine.</li>
        </ul>
      </div>
    </div>
  );
}
