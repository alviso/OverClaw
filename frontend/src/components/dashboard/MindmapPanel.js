import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { RefreshCw, ChevronUp, ChevronDown, Minus, Info, X } from "lucide-react";

const CATEGORY_COLORS = {
  work: "#6366f1",
  personal: "#10b981",
  urgent: "#ef4444",
  planning: "#f59e0b",
  communication: "#3b82f6",
  learning: "#8b5cf6",
};

const IMPORTANCE_SCALE = { high: 1.4, medium: 1.0, low: 0.7 };
const IMPORTANCE_RING = { high: "#ef4444", medium: "#a1a1aa", low: "#52525b" };

const NODE_TYPE_CONFIG = {
  topic: { baseRadius: 18, shape: "circle" },
  person: { baseRadius: 10, shape: "circle" },
};

function useForceGraph() {
  const [ForceGraph, setForceGraph] = useState(null);
  useEffect(() => {
    import("react-force-graph-2d").then((mod) => setForceGraph(() => mod.default));
  }, []);
  return ForceGraph;
}

export function MindmapPanel({ rpc, authenticated }) {
  const [graphData, setGraphData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [error, setError] = useState(null);
  const graphRef = useRef();
  const containerRef = useRef();
  const [dimensions, setDimensions] = useState(null);
  const ForceGraph = useForceGraph();

  const fetchMindmap = useCallback(async () => {
    if (!authenticated) return;
    setLoading(true);
    setError(null);
    try {
      const result = await rpc("mindmap.get");
      if (result && (result.nodes?.length || !result.empty)) {
        setGraphData(result);
      } else {
        setGraphData(null);
      }
    } catch (err) {
      console.error("mindmap.get error:", err);
    } finally {
      setLoading(false);
    }
  }, [authenticated, rpc]);

  useEffect(() => { fetchMindmap(); }, [fetchMindmap]);

  // Track container size for the graph
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          setContainerSize({ width: Math.floor(width), height: Math.floor(height) });
        }
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const generateMindmap = async () => {
    setGenerating(true);
    setError(null);
    try {
      const result = await rpc("mindmap.generate");
      if (result?.error) {
        setError(result.error);
      } else if (result?.nodes?.length) {
        setGraphData(result);
      } else {
        setError("No data to generate mindmap from. Start chatting to build memories.");
      }
    } catch (err) {
      setError(err.message || "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const setImportance = async (nodeId, importance) => {
    try {
      await rpc("mindmap.set_importance", { node_id: nodeId, importance });
      setGraphData((prev) => {
        if (!prev) return prev;
        const nodes = prev.nodes.map((n) =>
          n.id === nodeId ? { ...n, importance } : n
        );
        return { ...prev, nodes };
      });
      if (selectedNode?.id === nodeId) {
        setSelectedNode((prev) => ({ ...prev, importance }));
      }
    } catch (err) {
      console.error("set_importance error:", err);
    }
  };

  const forceData = useMemo(() => {
    if (!graphData?.nodes?.length) return null;
    const nodeIds = new Set(graphData.nodes.map((n) => n.id));
    return {
      nodes: graphData.nodes.map((n) => ({ ...n })),
      links: graphData.edges
        .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
        .map((e) => ({ ...e })),
    };
  }, [graphData]);

  const nodeCanvasObject = useCallback((node, ctx, globalScale) => {
    const cfg = NODE_TYPE_CONFIG[node.type] || NODE_TYPE_CONFIG.topic;
    const scale = IMPORTANCE_SCALE[node.importance] || 1;
    const r = cfg.baseRadius * scale;

    // Glow for selected
    if (selectedNode?.id === node.id) {
      ctx.shadowColor = "#818cf8";
      ctx.shadowBlur = 16;
    }

    // Importance ring
    const ringColor = IMPORTANCE_RING[node.importance] || IMPORTANCE_RING.medium;
    ctx.beginPath();
    ctx.arc(node.x, node.y, r + 2, 0, 2 * Math.PI);
    ctx.strokeStyle = ringColor;
    ctx.lineWidth = node.importance === "high" ? 2.5 : 1;
    ctx.stroke();

    // Main fill
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    if (node.type === "topic") {
      ctx.fillStyle = CATEGORY_COLORS[node.category] || "#6366f1";
    } else {
      ctx.fillStyle = "#27272a";
    }
    ctx.fill();

    // Person inner dot
    if (node.type === "person") {
      ctx.beginPath();
      ctx.arc(node.x, node.y, r * 0.5, 0, 2 * Math.PI);
      ctx.fillStyle = "#71717a";
      ctx.fill();
    }

    ctx.shadowColor = "transparent";
    ctx.shadowBlur = 0;

    // Label — centered inside the circle
    const label = node.label || "";
    const maxFontSize = node.type === "topic" ? r * 0.45 : r * 0.55;
    const fontSize = Math.max(Math.min(maxFontSize, 14 / globalScale), 2);
    ctx.font = `${node.type === "topic" ? "600" : "400"} ${fontSize}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#fff";

    // Word-wrap label inside circle
    const maxWidth = r * 1.5;
    const words = label.split(" ");
    const lines = [];
    let currentLine = "";
    for (const word of words) {
      const testLine = currentLine ? currentLine + " " + word : word;
      if (ctx.measureText(testLine).width > maxWidth && currentLine) {
        lines.push(currentLine);
        currentLine = word;
      } else {
        currentLine = testLine;
      }
    }
    if (currentLine) lines.push(currentLine);

    const lineHeight = fontSize * 1.2;
    const totalHeight = lines.length * lineHeight;
    const startY = node.y - totalHeight / 2 + lineHeight / 2;
    for (let i = 0; i < lines.length; i++) {
      ctx.fillText(lines[i], node.x, startY + i * lineHeight);
    }
  }, [selectedNode]);

  const linkCanvasObject = useCallback((link, ctx) => {
    const start = link.source;
    const end = link.target;
    if (typeof start !== "object" || typeof end !== "object") return;

    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.lineTo(end.x, end.y);
    ctx.strokeStyle = "rgba(113, 113, 122, 0.2)";
    ctx.lineWidth = 0.8;
    ctx.stroke();

    if (link.label) {
      const mx = (start.x + end.x) / 2;
      const my = (start.y + end.y) / 2;
      ctx.font = "3px sans-serif";
      ctx.fillStyle = "rgba(161, 161, 170, 0.5)";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(link.label, mx, my);
    }
  }, []);

  const handleNodeHover = useCallback((node) => {
    const canvas = document.querySelector('[data-testid="mindmap-canvas"] canvas');
    if (canvas) {
      canvas.style.cursor = node ? "pointer" : "default";
    }
  }, []);

  const handleNodeClick = useCallback((node) => {
    setSelectedNode((prev) => (prev?.id === node.id ? null : node));
    if (graphRef.current) {
      graphRef.current.centerAt(node.x, node.y, 400);
      graphRef.current.zoom(2.5, 400);
    }
  }, []);

  // Empty state
  if (!loading && !graphData) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[400px] gap-6" data-testid="mindmap-empty">
        <div className="w-20 h-20 rounded-2xl bg-zinc-800/60 border border-zinc-700/40 flex items-center justify-center">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-zinc-500">
            <circle cx="12" cy="12" r="3" />
            <circle cx="4" cy="6" r="2" />
            <circle cx="20" cy="6" r="2" />
            <circle cx="4" cy="18" r="2" />
            <circle cx="20" cy="18" r="2" />
            <line x1="9.5" y1="10.5" x2="5.5" y2="7.5" />
            <line x1="14.5" y1="10.5" x2="18.5" y2="7.5" />
            <line x1="9.5" y1="13.5" x2="5.5" y2="16.5" />
            <line x1="14.5" y1="13.5" x2="18.5" y2="16.5" />
          </svg>
        </div>
        <div className="text-center space-y-2">
          <p className="text-sm text-zinc-400">No mindmap generated yet</p>
          <p className="text-xs text-zinc-600 max-w-xs">
            Generate a visual map of your work streams, projects, and the people involved.
          </p>
        </div>
        <button
          data-testid="mindmap-generate-btn"
          onClick={generateMindmap}
          disabled={generating}
          className="px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
        >
          {generating ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          {generating ? "Generating..." : "Generate Mindmap"}
        </button>
        {error && <p className="text-xs text-red-400 max-w-sm text-center">{error}</p>}
      </div>
    );
  }

  if (loading && !graphData) {
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <RefreshCw className="w-5 h-5 animate-spin text-zinc-500" />
      </div>
    );
  }

  const topicCount = graphData?.nodes?.filter((n) => n.type === "topic").length || 0;
  const peopleCount = graphData?.nodes?.filter((n) => n.type === "person").length || 0;

  return (
    <div className="flex flex-col h-full" data-testid="mindmap-panel">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-zinc-500">{topicCount} topics</span>
            <span className="text-zinc-700">-</span>
            <span className="text-xs text-zinc-500">{peopleCount} people</span>
          </div>
          {graphData?.generated_at && (
            <span className="text-[10px] text-zinc-600">
              {new Date(graphData.generated_at).toLocaleString()}
            </span>
          )}
        </div>
        <button
          data-testid="mindmap-regenerate-btn"
          onClick={generateMindmap}
          disabled={generating}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${generating ? "animate-spin" : ""}`} />
          {generating ? "Generating..." : "Regenerate"}
        </button>
      </div>

      {error && (
        <div className="px-4 py-2 bg-red-500/10 border-b border-red-500/20">
          <p className="text-xs text-red-400">{error}</p>
        </div>
      )}

      {/* Legend */}
      <div className="flex items-center gap-4 px-4 py-2 border-b border-zinc-800/40">
        {Object.entries(CATEGORY_COLORS).map(([cat, color]) => (
          <div key={cat} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-[10px] text-zinc-600 capitalize">{cat}</span>
          </div>
        ))}
        <div className="flex items-center gap-1.5 ml-2 pl-2 border-l border-zinc-800/40">
          <div className="w-2.5 h-2.5 rounded-full bg-zinc-700 border border-zinc-600" />
          <span className="text-[10px] text-zinc-600">Person</span>
        </div>
      </div>

      {/* Graph + Detail panel */}
      <div className="flex-1 relative flex min-h-0 overflow-hidden">
        <div ref={containerRef} className="flex-1 min-w-0 bg-zinc-950" data-testid="mindmap-canvas">
          {ForceGraph && forceData && (
            <ForceGraph
              ref={graphRef}
              graphData={forceData}
              nodeCanvasObject={nodeCanvasObject}
              linkCanvasObject={linkCanvasObject}
              nodePointerAreaPaint={(node, color, ctx) => {
                const cfg = NODE_TYPE_CONFIG[node.type] || NODE_TYPE_CONFIG.topic;
                const scale = IMPORTANCE_SCALE[node.importance] || 1;
                const r = cfg.baseRadius * scale + 6;
                ctx.beginPath();
                ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
                ctx.fillStyle = color;
                ctx.fill();
              }}
              onNodeClick={handleNodeClick}
              onNodeHover={handleNodeHover}
              nodeLabel={(node) => node.type === "topic"
                ? `${node.label}${node.summary ? ' — ' + node.summary : ''}`
                : `${node.label}${node.role ? ' (' + node.role + ')' : ''}`
              }
              onBackgroundClick={() => setSelectedNode(null)}
              backgroundColor="#09090b"
              linkDirectionalParticles={0}
              cooldownTicks={80}
              d3AlphaDecay={0.03}
              d3VelocityDecay={0.3}
              warmupTicks={40}
              width={containerSize.width}
              height={containerSize.height}
            />
          )}
        </div>

        {/* Right panel: detail only, shown on node click */}
        {selectedNode && (
          <NodeDetail
            node={selectedNode}
            onClose={() => setSelectedNode(null)}
            onSetImportance={setImportance}
          />
        )}
      </div>
    </div>
  );
}

function NodeDetail({ node, onClose, onSetImportance }) {
  const isTopic = node.type === "topic";
  const color = isTopic
    ? CATEGORY_COLORS[node.category] || "#6366f1"
    : "#71717a";

  return (
    <div
      data-testid="mindmap-node-detail"
      className="absolute right-0 top-0 bottom-0 w-72 border-l border-zinc-800/60 bg-zinc-900/95 backdrop-blur-md p-4 overflow-y-auto flex flex-col gap-4 z-10 shadow-xl shadow-black/30"
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <div
            className="w-4 h-4 rounded-full flex-shrink-0"
            style={{ backgroundColor: color }}
          />
          <span className="text-sm font-medium text-zinc-100">{node.label}</span>
        </div>
        <button
          data-testid="mindmap-detail-close"
          onClick={onClose}
          className="p-1 rounded hover:bg-zinc-800 text-zinc-500 hover:text-zinc-300 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Type badge */}
      <div className="flex items-center gap-2">
        <span
          className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full font-medium"
          style={{
            backgroundColor: `${color}20`,
            color: color,
            border: `1px solid ${color}40`,
          }}
        >
          {node.type}
        </span>
        {isTopic && node.category && (
          <span className="text-[10px] text-zinc-500 capitalize">{node.category}</span>
        )}
        {!isTopic && node.role && (
          <span className="text-[10px] text-zinc-500">{node.role}</span>
        )}
      </div>

      {/* Summary */}
      {node.summary && (
        <div className="flex items-start gap-2">
          <Info className="w-3.5 h-3.5 text-zinc-600 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-zinc-400 leading-relaxed">{node.summary}</p>
        </div>
      )}

      {/* Person details */}
      {!isTopic && node.team && (
        <div className="text-xs text-zinc-500">Team: {node.team}</div>
      )}

      {/* Importance control */}
      {isTopic && (
        <div className="space-y-2">
          <label className="text-[10px] uppercase tracking-wider text-zinc-600 font-medium">
            Importance
          </label>
          <div className="flex gap-1">
            {["high", "medium", "low"].map((level) => {
              const active = (node.importance || "medium") === level;
              const colors = {
                high: "bg-red-500/20 border-red-500/40 text-red-400",
                medium: "bg-zinc-700/30 border-zinc-600/40 text-zinc-300",
                low: "bg-zinc-800/30 border-zinc-700/40 text-zinc-500",
              };
              return (
                <button
                  key={level}
                  data-testid={`mindmap-importance-${level}`}
                  onClick={() => onSetImportance(node.id, level)}
                  className={`flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-md text-[11px] font-medium border transition-all ${
                    active
                      ? colors[level]
                      : "border-zinc-800 text-zinc-600 hover:border-zinc-700 hover:text-zinc-400"
                  }`}
                >
                  {level === "high" && <ChevronUp className="w-3 h-3" />}
                  {level === "medium" && <Minus className="w-3 h-3" />}
                  {level === "low" && <ChevronDown className="w-3 h-3" />}
                  {level}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}


function NodeList({ nodes, onSelectNode }) {
  const topics = nodes.filter((n) => n.type === "topic");
  const people = nodes.filter((n) => n.type === "person");

  return (
    <div
      data-testid="mindmap-node-list"
      className="w-72 border-l border-zinc-800/60 bg-zinc-900/80 backdrop-blur-sm overflow-y-auto"
    >
      <div className="px-3 py-2.5 border-b border-zinc-800/40">
        <span className="text-[10px] uppercase tracking-wider text-zinc-600 font-medium">
          Topics
        </span>
      </div>
      {topics.map((node) => {
        const color = CATEGORY_COLORS[node.category] || "#6366f1";
        return (
          <button
            key={node.id}
            data-testid={`mindmap-node-${node.id}`}
            onClick={() => onSelectNode(node)}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-zinc-800/50 transition-colors border-b border-zinc-800/20"
          >
            <div
              className="w-3 h-3 rounded-full flex-shrink-0"
              style={{ backgroundColor: color }}
            />
            <div className="min-w-0 flex-1">
              <div className="text-xs text-zinc-200 truncate">{node.label}</div>
              {node.summary && (
                <div className="text-[10px] text-zinc-600 truncate">{node.summary}</div>
              )}
            </div>
            {node.importance === "high" && (
              <ChevronUp className="w-3 h-3 text-red-400 flex-shrink-0" />
            )}
          </button>
        );
      })}

      {people.length > 0 && (
        <>
          <div className="px-3 py-2.5 border-b border-zinc-800/40 mt-1">
            <span className="text-[10px] uppercase tracking-wider text-zinc-600 font-medium">
              People
            </span>
          </div>
          {people.map((node) => (
            <button
              key={node.id}
              data-testid={`mindmap-node-${node.id}`}
              onClick={() => onSelectNode(node)}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-zinc-800/50 transition-colors border-b border-zinc-800/20"
            >
              <div className="w-3 h-3 rounded-full bg-zinc-700 border border-zinc-600 flex-shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="text-xs text-zinc-200 truncate">{node.label}</div>
                {node.role && (
                  <div className="text-[10px] text-zinc-600 truncate">{node.role}</div>
                )}
              </div>
            </button>
          ))}
        </>
      )}
    </div>
  );
}
