import { useState, useEffect, useCallback, useRef } from "react";
import {
  Folder, FileText, ChevronRight, ArrowLeft, RefreshCw,
  Play, Square, Terminal, Wrench, Trash2, Eye, Clock,
  FileCode, FolderOpen, Cpu, Code2, Radio,
  Rocket, Loader2, Download, ExternalLink, Circle,
  Package, Globe, LayoutGrid
} from "lucide-react";

// ── Utility ──────────────────────────────────────────────────────────────

function timeAgo(ts) {
  if (!ts) return "";
  const sec = Math.floor((Date.now() / 1000) - ts);
  if (sec < 60) return "just now";
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

const TYPE_COLORS = {
  python: { bg: "bg-sky-500/10", text: "text-sky-400", border: "border-sky-500/20", label: "Python" },
  node: { bg: "bg-emerald-500/10", text: "text-emerald-400", border: "border-emerald-500/20", label: "Node.js" },
};

// ── Project Card ─────────────────────────────────────────────────────────

function ProjectCard({ project, onOpen, onRun, onStop, onInstall }) {
  const tc = TYPE_COLORS[project.project_type] || { bg: "bg-zinc-500/10", text: "text-zinc-400", border: "border-zinc-500/20", label: "Other" };
  const isRunning = project.status === "running";

  return (
    <div
      data-testid={`project-card-${project.name}`}
      className="group relative bg-zinc-900/60 border border-zinc-800/50 rounded-xl p-4 hover:border-zinc-700/60 transition-all duration-200 hover:shadow-lg hover:shadow-black/20"
    >
      {/* Status dot */}
      <div className="absolute top-4 right-4">
        <Circle
          className={`w-2.5 h-2.5 ${isRunning ? "text-emerald-400 fill-emerald-400 animate-pulse" : "text-zinc-600 fill-zinc-700"}`}
        />
      </div>

      {/* Header */}
      <div className="mb-3">
        <button
          onClick={() => onOpen(project)}
          data-testid={`project-open-${project.name}`}
          className="text-left group/title"
        >
          <h3 className="text-sm font-semibold text-zinc-200 group-hover/title:text-white transition-colors">
            {project.name}
          </h3>
        </button>
        <div className="flex items-center gap-2 mt-1.5">
          <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono ${tc.bg} ${tc.text} border ${tc.border}`}>
            {tc.label}
          </span>
          {project.has_deps && !project.has_venv && project.project_type === "python" && (
            <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20">
              needs setup
            </span>
          )}
          {isRunning && project.port && (
            <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              :{project.port}
            </span>
          )}
        </div>
      </div>

      {/* Meta */}
      <div className="flex items-center gap-3 text-[10px] text-zinc-500 mb-3">
        {project.entry_point && (
          <span className="flex items-center gap-1">
            <FileCode className="w-3 h-3" /> {project.entry_point}
          </span>
        )}
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3" /> {timeAgo(project.last_modified)}
        </span>
        <span className="flex items-center gap-1">
          <FileText className="w-3 h-3" /> {project.file_count} files
        </span>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-2 border-t border-zinc-800/40">
        <button
          onClick={() => onOpen(project)}
          data-testid={`project-browse-${project.name}`}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[10px] font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 transition-colors"
        >
          <FolderOpen className="w-3 h-3" /> Files
        </button>

        {!isRunning && (
          <button
            onClick={() => onRun(project)}
            data-testid={`project-run-${project.name}`}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[10px] font-medium text-emerald-400 hover:text-emerald-300 bg-emerald-500/5 hover:bg-emerald-500/10 border border-emerald-500/10 hover:border-emerald-500/20 transition-colors"
          >
            <Play className="w-3 h-3" /> Run
          </button>
        )}

        {isRunning && (
          <>
            <button
              onClick={() => onStop(project)}
              data-testid={`project-stop-${project.name}`}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[10px] font-medium text-red-400/80 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            >
              <Square className="w-3 h-3" /> Stop
            </button>
            {project.port && (
              <a
                href={`${process.env.REACT_APP_BACKEND_URL}/api/preview/${project.port}/`}
                target="_blank"
                rel="noopener noreferrer"
                data-testid={`project-preview-${project.name}`}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[10px] font-medium text-indigo-400 hover:text-indigo-300 bg-indigo-500/5 hover:bg-indigo-500/10 border border-indigo-500/10 hover:border-indigo-500/20 transition-colors ml-auto"
              >
                <Globe className="w-3 h-3" /> Preview
                <ExternalLink className="w-2.5 h-2.5" />
              </a>
            )}
          </>
        )}

        {project.has_deps && !project.has_venv && project.project_type === "python" && !isRunning && (
          <button
            onClick={() => onInstall(project)}
            data-testid={`project-install-${project.name}`}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[10px] font-medium text-amber-400 hover:text-amber-300 hover:bg-amber-500/10 transition-colors ml-auto"
          >
            <Download className="w-3 h-3" /> Setup
          </button>
        )}
      </div>
    </div>
  );
}

// ── Run Project Form (reused in drill-down) ──────────────────────────────

function RunProjectForm({ rpc, projectPath, onStarted, onCancel }) {
  const [detecting, setDetecting] = useState(true);
  const [info, setInfo] = useState(null);
  const [command, setCommand] = useState("");
  const [name, setName] = useState("");
  const [port, setPort] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await rpc("workspace.detect_project", { path: projectPath });
        if (cancelled) return;
        setInfo(r);
        setCommand(r.suggested_command || "");
        setName(r.suggested_name || "project");
        if (r.suggested_port) setPort(String(r.suggested_port));
      } catch (e) {
        if (!cancelled) setError("Failed to detect project");
      }
      if (!cancelled) setDetecting(false);
    })();
    return () => { cancelled = true; };
  }, [rpc, projectPath]);

  const handleRun = async () => {
    if (!command.trim() || !name.trim()) return;
    setRunning(true);
    setError(null);
    try {
      const params = { path: projectPath, command: command.trim(), name: name.trim() };
      if (port.trim()) params.port = port.trim();
      const r = await rpc("workspace.run_project", params);
      if (r?.ok) {
        onStarted?.();
      } else {
        setError(r?.error || r?.message || "Failed to start project");
        setRunning(false);
      }
    } catch (e) {
      setError(String(e));
      setRunning(false);
    }
  };

  if (detecting) {
    return (
      <div className="bg-zinc-900/50 border border-zinc-800/60 rounded-lg p-4 flex items-center gap-3" data-testid="run-project-detecting">
        <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />
        <span className="text-xs text-zinc-400">Detecting project...</span>
      </div>
    );
  }

  const tc = TYPE_COLORS[info?.project_type];

  return (
    <div className="bg-zinc-900/60 border border-indigo-500/20 rounded-lg p-4 space-y-3" data-testid="run-project-form">
      <div className="flex items-center gap-2">
        <Rocket className="w-4 h-4 text-indigo-400" />
        <span className="text-sm font-medium text-zinc-200">Run Project</span>
        {tc && (
          <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono ${tc.bg} ${tc.text} border ${tc.border}`}>{tc.label}</span>
        )}
      </div>

      <div className="grid grid-cols-[1fr_auto] gap-2">
        <div>
          <label className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1 block">Name</label>
          <input value={name} onChange={e => setName(e.target.value)} data-testid="run-project-name"
            className="w-full bg-zinc-950/60 border border-zinc-800/60 rounded px-3 py-1.5 text-xs text-zinc-300 font-mono focus:outline-none focus:border-indigo-500/40" />
        </div>
        <div>
          <label className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1 block">Port</label>
          <input value={port} onChange={e => setPort(e.target.value)} placeholder="auto" data-testid="run-project-port"
            className="w-24 bg-zinc-950/60 border border-zinc-800/60 rounded px-3 py-1.5 text-xs text-zinc-300 font-mono focus:outline-none focus:border-indigo-500/40" />
        </div>
      </div>
      <div>
        <label className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1 block">Command</label>
        <textarea value={command} onChange={e => setCommand(e.target.value)} rows={2} data-testid="run-project-command"
          className="w-full bg-zinc-950/60 border border-zinc-800/60 rounded px-3 py-2 text-xs text-zinc-300 font-mono focus:outline-none focus:border-indigo-500/40 resize-none" />
      </div>

      {error && <p className="text-xs text-red-400" data-testid="run-project-error">{error}</p>}

      <div className="flex items-center gap-2">
        <button onClick={handleRun} disabled={!command.trim() || !name.trim() || running} data-testid="run-project-submit"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-500 transition-colors disabled:opacity-40">
          {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
          {running ? "Starting..." : "Run"}
        </button>
        <button onClick={onCancel} data-testid="run-project-cancel"
          className="px-3 py-1.5 rounded-md bg-zinc-800/60 text-zinc-400 text-xs font-medium hover:text-zinc-200 transition-colors">
          Cancel
        </button>
        {port && (
          <span className="text-[10px] text-zinc-500 ml-auto">Preview: <span className="text-indigo-400">/api/preview/{port}/</span></span>
        )}
      </div>
    </div>
  );
}

// ── Terminal View ────────────────────────────────────────────────────────

function TerminalView({ rpc, authenticated, pid, processName, processStatus, onBack, onEvent, offEvent }) {
  const [lines, setLines] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const terminalRef = useRef(null);
  const autoScrollRef = useRef(true);

  useEffect(() => {
    if (!authenticated || !pid) return;
    let cancelled = false;
    const startStreaming = async () => {
      try {
        const r = await rpc("workspace.process_subscribe", { pid });
        if (cancelled) return;
        if (r?.ok) { setLines(r.initial_lines || []); setStreaming(true); }
      } catch (e) { console.error("subscribe error:", e); }
    };
    startStreaming();
    return () => { cancelled = true; rpc("workspace.process_unsubscribe", { pid }).catch(() => {}); };
  }, [authenticated, pid, rpc]);

  useEffect(() => {
    if (!onEvent || !offEvent) return;
    const handler = (params) => {
      if (params.pid === pid && params.line) {
        setLines(prev => { const next = [...prev, params.line]; return next.length > 500 ? next.slice(-500) : next; });
      }
    };
    onEvent("workspace.stream", handler);
    return () => offEvent("workspace.stream", handler);
  }, [pid, onEvent, offEvent]);

  useEffect(() => {
    if (autoScrollRef.current && terminalRef.current) terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
  }, [lines]);

  const handleScroll = () => {
    if (!terminalRef.current) return;
    const el = terminalRef.current;
    autoScrollRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  };

  return (
    <div className="space-y-3" data-testid="terminal-view">
      <div className="flex items-center gap-2">
        <button onClick={onBack} data-testid="terminal-back-btn"
          className="p-1.5 rounded-md bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-400 hover:text-zinc-200 transition-colors">
          <ArrowLeft className="w-3.5 h-3.5" />
        </button>
        <Terminal className="w-4 h-4 text-emerald-400" />
        <span className="text-sm font-medium text-zinc-300">{processName}</span>
        <div className="ml-auto flex items-center gap-2">
          {streaming && processStatus === "running" && (
            <div className="flex items-center gap-1.5" data-testid="live-indicator">
              <Radio className="w-3 h-3 text-red-400 animate-pulse" />
              <span className="text-[10px] font-mono text-red-400 uppercase tracking-wider">live</span>
            </div>
          )}
          <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono ${
            processStatus === "running" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-zinc-700/50 text-zinc-500 border border-zinc-700/40"
          }`}>{processStatus}</span>
        </div>
      </div>

      <div ref={terminalRef} onScroll={handleScroll} data-testid="terminal-output"
        className="bg-[#0a0a0f] border border-zinc-800/60 rounded-lg overflow-auto font-mono text-[11px] leading-[1.6] shadow-inner"
        style={{ height: "400px" }}>
        <div className="sticky top-0 z-10 flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900/95 border-b border-zinc-800/40 backdrop-blur-sm">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500/70" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/70" />
          <span className="ml-2 text-[9px] text-zinc-600">{processName} — PID {pid}</span>
        </div>
        <div className="p-3">
          {lines.length === 0 ? (
            <div className="text-zinc-600 italic">Waiting for output...</div>
          ) : lines.map((line, i) => (
            <div key={i} className={`whitespace-pre-wrap break-all ${line.startsWith("[err]") ? "text-red-400/80" : "text-emerald-300/70"}`}>{line}</div>
          ))}
          {streaming && processStatus === "running" && <div className="inline-block w-2 h-4 bg-emerald-400/80 animate-pulse ml-0.5" />}
        </div>
      </div>
    </div>
  );
}

// ── Project Detail (File Browser + Controls) ─────────────────────────────

function ProjectDetail({ project, rpc, authenticated, onBack, onEvent, offEvent, onRefresh }) {
  const [items, setItems] = useState([]);
  const [currentPath, setCurrentPath] = useState(project.path);
  const [fileContent, setFileContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pathHistory, setPathHistory] = useState([project.path]);
  const [showRunForm, setShowRunForm] = useState(false);
  const [terminalProc, setTerminalProc] = useState(null);
  const [installing, setInstalling] = useState(false);
  const [liveProject, setLiveProject] = useState(project);

  // Refresh project status periodically
  useEffect(() => {
    const refresh = async () => {
      try {
        const r = await rpc("workspace.projects");
        const updated = (r?.projects || []).find(p => p.name === project.name);
        if (updated) setLiveProject(updated);
      } catch (e) { /* ignore */ }
    };
    const iv = setInterval(refresh, 4000);
    return () => clearInterval(iv);
  }, [rpc, project.name]);

  const fetchDir = useCallback(async (path) => {
    if (!authenticated) return;
    setLoading(true);
    setFileContent(null);
    setShowRunForm(false);
    try {
      const r = await rpc("workspace.files", { path });
      if (r?.type === "file") {
        setFileContent(r);
      } else {
        setItems(r?.items || []);
        setCurrentPath(r?.current_path || path);
      }
    } catch (e) { console.error("workspace.files error:", e); }
    setLoading(false);
  }, [authenticated, rpc]);

  useEffect(() => { fetchDir(project.path); }, [fetchDir, project.path]);

  const navigate = (path) => { setPathHistory(prev => [...prev, path]); fetchDir(path); };
  const goBack = () => {
    if (pathHistory.length > 1) {
      const nh = pathHistory.slice(0, -1);
      setPathHistory(nh);
      fetchDir(nh[nh.length - 1]);
    }
  };

  const formatSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleStop = async () => {
    if (!liveProject.process?.pid) return;
    try {
      await rpc("workspace.stop_process", { pid: liveProject.process.pid });
      onRefresh?.();
    } catch (e) { console.error("stop error:", e); }
  };

  const handleInstall = async () => {
    setInstalling(true);
    try {
      await rpc("workspace.install_deps", { path: project.path });
    } catch (e) { console.error("install error:", e); }
    setInstalling(false);
  };

  const isRunning = liveProject.status === "running";
  const tc = TYPE_COLORS[liveProject.project_type] || { bg: "bg-zinc-500/10", text: "text-zinc-400", border: "border-zinc-500/20", label: "Other" };

  if (terminalProc) {
    return (
      <TerminalView
        rpc={rpc} authenticated={authenticated}
        pid={terminalProc.pid} processName={terminalProc.name} processStatus="running"
        onBack={() => setTerminalProc(null)} onEvent={onEvent} offEvent={offEvent}
      />
    );
  }

  return (
    <div className="space-y-4" data-testid="project-detail">
      {/* Project header */}
      <div className="flex items-center gap-3">
        <button onClick={onBack} data-testid="project-back-btn"
          className="p-1.5 rounded-md bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-400 hover:text-zinc-200 transition-colors">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-zinc-100 truncate">{project.name}</h2>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono ${tc.bg} ${tc.text} border ${tc.border}`}>{tc.label}</span>
            <Circle className={`w-2.5 h-2.5 flex-shrink-0 ${isRunning ? "text-emerald-400 fill-emerald-400 animate-pulse" : "text-zinc-600 fill-zinc-700"}`} />
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isRunning && liveProject.port && (
            <a href={`${process.env.REACT_APP_BACKEND_URL}/api/preview/${liveProject.port}/`} target="_blank" rel="noopener noreferrer"
              data-testid="project-detail-preview"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 hover:bg-indigo-500/15 transition-colors">
              <Globe className="w-3.5 h-3.5" /> Preview :{liveProject.port}
            </a>
          )}
          {liveProject.process && (
            <button onClick={() => setTerminalProc(liveProject.process)} data-testid="project-detail-terminal"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 hover:bg-emerald-500/15 transition-colors">
              <Terminal className="w-3.5 h-3.5" /> Logs
            </button>
          )}
          {isRunning && (
            <button onClick={handleStop} data-testid="project-detail-stop"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-red-400 bg-red-500/10 border border-red-500/20 hover:bg-red-500/15 transition-colors">
              <Square className="w-3.5 h-3.5" /> Stop
            </button>
          )}
          {!isRunning && (
            <button onClick={() => setShowRunForm(true)} data-testid="project-detail-run"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 hover:bg-emerald-500/15 transition-colors">
              <Play className="w-3.5 h-3.5" /> Run
            </button>
          )}
          {liveProject.has_deps && !liveProject.has_venv && liveProject.project_type === "python" && (
            <button onClick={handleInstall} disabled={installing} data-testid="project-detail-install"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-amber-400 bg-amber-500/10 border border-amber-500/20 hover:bg-amber-500/15 transition-colors disabled:opacity-40">
              {installing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />} Setup
            </button>
          )}
        </div>
      </div>

      {/* Run form */}
      {showRunForm && (
        <RunProjectForm rpc={rpc} projectPath={project.path}
          onStarted={() => { setShowRunForm(false); onRefresh?.(); }}
          onCancel={() => setShowRunForm(false)} />
      )}

      {/* File browser */}
      {fileContent ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <button onClick={goBack} data-testid="file-back-btn"
              className="p-1.5 rounded-md bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-400 hover:text-zinc-200 transition-colors">
              <ArrowLeft className="w-3.5 h-3.5" />
            </button>
            <FileCode className="w-4 h-4 text-indigo-400" />
            <span className="text-sm font-mono text-zinc-300">{fileContent.name}</span>
            <span className="text-[10px] text-zinc-600 ml-auto">{formatSize(fileContent.size)}</span>
          </div>
          <pre data-testid="file-content-view"
            className="bg-zinc-900/80 border border-zinc-800/60 rounded-lg p-4 text-xs font-mono text-zinc-400 overflow-auto max-h-[500px] whitespace-pre-wrap">
            {fileContent.content}
          </pre>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <button onClick={goBack} disabled={pathHistory.length <= 1} data-testid="dir-back-btn"
              className="p-1.5 rounded-md bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-30">
              <ArrowLeft className="w-3.5 h-3.5" />
            </button>
            <FolderOpen className="w-4 h-4 text-amber-400" />
            <span className="text-xs font-mono text-zinc-500 truncate">/workspace/{currentPath}</span>
            <button onClick={() => fetchDir(currentPath)} data-testid="refresh-files-btn"
              className="ml-auto p-1.5 rounded-md bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-400 hover:text-zinc-200 transition-colors">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>

          {items.length === 0 && !loading ? (
            <div className="text-center py-12 text-zinc-600 text-sm">
              <Folder className="w-8 h-8 mx-auto mb-2 opacity-40" />
              Empty directory
            </div>
          ) : (
            <div className="border border-zinc-800/60 rounded-lg overflow-hidden divide-y divide-zinc-800/40">
              {items.map((item) => (
                <button key={item.path} data-testid={`file-item-${item.name}`}
                  onClick={() => navigate(item.path)}
                  className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-zinc-800/40 transition-colors text-left group">
                  {item.type === "directory"
                    ? <Folder className="w-4 h-4 text-amber-400/80 flex-shrink-0" />
                    : <FileText className="w-4 h-4 text-zinc-500 flex-shrink-0" />}
                  <span className="text-sm text-zinc-300 truncate flex-1 group-hover:text-zinc-100">{item.name}</span>
                  {item.type === "file" && <span className="text-[10px] text-zinc-600 flex-shrink-0">{formatSize(item.size)}</span>}
                  {item.type === "directory" && <ChevronRight className="w-3.5 h-3.5 text-zinc-700 group-hover:text-zinc-500 flex-shrink-0" />}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Project Dashboard (Main View) ────────────────────────────────────────

function ProjectDashboard({ rpc, authenticated, onEvent, offEvent }) {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedProject, setSelectedProject] = useState(null);
  const [runProject, setRunProject] = useState(null);

  const fetchProjects = useCallback(async () => {
    if (!authenticated) return;
    try {
      const r = await rpc("workspace.projects");
      setProjects(r?.projects || []);
    } catch (e) { console.error("workspace.projects error:", e); }
    setLoading(false);
  }, [authenticated, rpc]);

  useEffect(() => {
    fetchProjects();
    const iv = setInterval(fetchProjects, 5000);
    return () => clearInterval(iv);
  }, [fetchProjects]);

  const handleStop = async (project) => {
    if (!project.process?.pid) return;
    try {
      await rpc("workspace.stop_process", { pid: project.process.pid });
      fetchProjects();
    } catch (e) { console.error("stop error:", e); }
  };

  const handleInstall = async (project) => {
    try {
      await rpc("workspace.install_deps", { path: project.path });
      fetchProjects();
    } catch (e) { console.error("install error:", e); }
  };

  // Drill-down into a project
  if (selectedProject) {
    return (
      <ProjectDetail
        project={selectedProject}
        rpc={rpc} authenticated={authenticated}
        onBack={() => { setSelectedProject(null); fetchProjects(); }}
        onEvent={onEvent} offEvent={offEvent}
        onRefresh={fetchProjects}
      />
    );
  }

  // Run form overlay
  if (runProject) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <button onClick={() => setRunProject(null)} data-testid="run-back-btn"
            className="p-1.5 rounded-md bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-400 hover:text-zinc-200 transition-colors">
            <ArrowLeft className="w-4 h-4" />
          </button>
          <h2 className="text-base font-semibold text-zinc-100">Run {runProject.name}</h2>
        </div>
        <RunProjectForm rpc={rpc} projectPath={runProject.path}
          onStarted={() => { setRunProject(null); fetchProjects(); }}
          onCancel={() => setRunProject(null)} />
      </div>
    );
  }

  const runningCount = projects.filter(p => p.status === "running").length;

  return (
    <div className="space-y-4" data-testid="project-dashboard">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-500 uppercase tracking-wider font-mono">
              {projects.length} project{projects.length !== 1 ? "s" : ""}
            </span>
            {runningCount > 0 && (
              <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                {runningCount} running
              </span>
            )}
          </div>
        </div>
        <button onClick={fetchProjects} data-testid="refresh-projects-btn"
          className="p-1.5 rounded-md bg-zinc-800/60 hover:bg-zinc-700/60 text-zinc-400 hover:text-zinc-200 transition-colors">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* Project grid */}
      {projects.length === 0 && !loading ? (
        <div className="text-center py-16 text-zinc-600">
          <Package className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="text-sm mb-1">No projects yet</p>
          <p className="text-xs text-zinc-700">Ask the developer agent to build something, or create a project in /workspace/projects/</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {projects.map(p => (
            <ProjectCard
              key={p.name}
              project={p}
              onOpen={() => setSelectedProject(p)}
              onRun={() => setRunProject(p)}
              onStop={() => handleStop(p)}
              onInstall={() => handleInstall(p)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Custom Tools (small section, not a full tab) ─────────────────────────

function CustomToolsSection({ rpc, authenticated }) {
  const [tools, setTools] = useState([]);
  const [expanded, setExpanded] = useState(false);

  const fetchTools = useCallback(async () => {
    if (!authenticated) return;
    try {
      const r = await rpc("workspace.tools");
      setTools(r?.tools || []);
    } catch (e) { console.error("workspace.tools error:", e); }
  }, [authenticated, rpc]);

  useEffect(() => { fetchTools(); }, [fetchTools]);

  const deleteTool = async (name) => {
    try { await rpc("workspace.tool_delete", { name }); fetchTools(); }
    catch (e) { console.error("delete error:", e); }
  };

  if (tools.length === 0) return null;

  return (
    <div className="border-t border-zinc-800/40 pt-4" data-testid="custom-tools-section">
      <button onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-xs text-zinc-500 hover:text-zinc-300 transition-colors w-full">
        <Code2 className="w-3.5 h-3.5" />
        <span className="uppercase tracking-wider font-mono">{tools.length} custom tool{tools.length !== 1 ? "s" : ""}</span>
        <ChevronRight className={`w-3 h-3 ml-auto transition-transform ${expanded ? "rotate-90" : ""}`} />
      </button>
      {expanded && (
        <div className="mt-3 space-y-2">
          {tools.map(tool => (
            <div key={tool.name} className="flex items-center gap-2 px-3 py-2 bg-zinc-900/40 rounded-lg border border-zinc-800/40" data-testid={`tool-item-${tool.name}`}>
              <Wrench className="w-3 h-3 text-violet-400 flex-shrink-0" />
              <span className="text-xs font-mono text-zinc-300 flex-1 truncate">{tool.name}</span>
              <button onClick={() => deleteTool(tool.name)} data-testid={`delete-tool-${tool.name}`}
                className="p-1 rounded hover:bg-red-500/10 text-zinc-600 hover:text-red-400 transition-colors">
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Panel ──────────────────────────────────────────────────────────

export function WorkspacePanel({ rpc, authenticated, onEvent, offEvent }) {
  return (
    <div className="space-y-6" data-testid="workspace-panel">
      <ProjectDashboard rpc={rpc} authenticated={authenticated} onEvent={onEvent} offEvent={offEvent} />
      <CustomToolsSection rpc={rpc} authenticated={authenticated} />
    </div>
  );
}
