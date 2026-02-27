import { useState, useEffect, useCallback } from "react";
import { Brain, Search, Trash2, Plus, X, BarChart3 } from "lucide-react";

function timeAgo(iso) {
  if (!iso) return "";
  try {
    const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  } catch { return ""; }
}

const TYPE_COLORS = {
  fact: "bg-blue-500/20 text-blue-300",
  decision: "bg-amber-500/20 text-amber-300",
  action_item: "bg-rose-500/20 text-rose-300",
  preference: "bg-violet-500/20 text-violet-300",
  summary: "bg-teal-500/20 text-teal-300",
};

const SOURCE_LABELS = {
  fact_extraction: { label: "extracted", color: "bg-emerald-500/15 text-emerald-400" },
  screen_capture: { label: "screen", color: "bg-violet-500/15 text-violet-400" },
  "email/gmail": { label: "email", color: "bg-red-500/15 text-red-400" },
  manual: { label: "manual", color: "bg-zinc-500/15 text-zinc-400" },
};

export function MemoryPanel({ rpc, authenticated }) {
  const [memories, setMemories] = useState([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [showStats, setShowStats] = useState(false);

  const fetchMemories = useCallback(() => {
    if (!authenticated) return;
    rpc("memory.list", { limit: 20 }).then(r => {
      if (r?.memories) setMemories(r.memories);
      if (r?.total !== undefined) setTotal(r.total);
    }).catch(() => {});
  }, [authenticated, rpc]);

  const fetchStats = useCallback(() => {
    if (!authenticated) return;
    rpc("memory.stats", {}).then(r => {
      if (r && !r.error) setStats(r);
    }).catch(() => {});
  }, [authenticated, rpc]);

  useEffect(() => { fetchMemories(); fetchStats(); }, [fetchMemories, fetchStats]);

  const handleSearch = async () => {
    if (!searchQuery.trim()) { setSearchResults(null); return; }
    setSearching(true);
    try {
      const r = await rpc("memory.search", { query: searchQuery, top_k: 5 });
      setSearchResults(r?.results || []);
    } catch { setSearchResults([]); }
    finally { setSearching(false); }
  };

  const handleAdd = async () => {
    if (!newContent.trim()) return;
    setSaving(true);
    await rpc("memory.store", { content: newContent.trim() });
    setNewContent("");
    setShowAdd(false);
    setSaving(false);
    fetchMemories();
    fetchStats();
  };

  const handleClearAll = async () => {
    await rpc("memory.clear");
    fetchMemories();
    fetchStats();
    setSearchResults(null);
  };

  const displayList = searchResults !== null ? searchResults : memories;

  return (
    <div data-testid="memory-panel" className="bg-zinc-900/60 border border-zinc-800/60 rounded-lg overflow-hidden hover:border-zinc-700/80 transition-colors">
      <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-2">
          <Brain className="w-4 h-4 text-zinc-400" />
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-widest">Knowledge</span>
          <span className="text-[10px] font-mono text-zinc-600">{total} facts</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowStats(!showStats)}
            data-testid="memory-stats-btn"
            className="p-1.5 text-zinc-600 hover:text-zinc-300 rounded hover:bg-zinc-800 transition-colors"
            title="Index stats"
          >
            <BarChart3 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setShowAdd(!showAdd)}
            data-testid="memory-add-btn"
            className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 px-2 py-1 rounded hover:bg-blue-400/10 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Add
          </button>
          {total > 0 && (
            <button
              onClick={handleClearAll}
              data-testid="memory-clear-btn"
              className="flex items-center gap-1 text-xs text-zinc-600 hover:text-rose-400 px-2 py-1 rounded hover:bg-rose-400/10 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Clear
            </button>
          )}
        </div>
      </div>

      <div className="p-4 space-y-3">
        {/* Stats panel */}
        {showStats && stats && (
          <div data-testid="memory-stats-panel" className="bg-zinc-800/40 border border-zinc-700/30 rounded-lg p-3 space-y-2">
            <div className="grid grid-cols-2 gap-2 text-[10px]">
              <div>
                <span className="text-zinc-500">Total facts</span>
                <span className="ml-2 text-zinc-300 font-mono">{stats.total_memories}</span>
              </div>
              <div>
                <span className="text-zinc-500">FAISS indexed</span>
                <span className="ml-2 text-emerald-400 font-mono">{stats.faiss_index_size}</span>
              </div>
              <div>
                <span className="text-zinc-500">Dimensions</span>
                <span className="ml-2 text-zinc-300 font-mono">{stats.embedding_dims}</span>
              </div>
              <div>
                <span className="text-zinc-500">Search mode</span>
                <span className="ml-2 text-zinc-300 font-mono">
                  {Math.round(stats.hybrid_weights?.vector * 100)}% semantic + {Math.round(stats.hybrid_weights?.keyword * 100)}% keyword
                </span>
              </div>
            </div>
            {stats.by_source && Object.keys(stats.by_source).length > 0 && (
              <div className="border-t border-zinc-700/30 pt-2 mt-2">
                <span className="text-[10px] text-zinc-500 uppercase tracking-wider">By Source</span>
                <div className="flex flex-wrap gap-2 mt-1">
                  {Object.entries(stats.by_source).map(([src, count]) => (
                    <span key={src} className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-700/30 text-zinc-400">
                      {src}: {count}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {stats.by_agent && Object.keys(stats.by_agent).length > 1 && (
              <div className="border-t border-zinc-700/30 pt-2 mt-2">
                <span className="text-[10px] text-zinc-500 uppercase tracking-wider">By Agent</span>
                <div className="flex flex-wrap gap-2 mt-1">
                  {Object.entries(stats.by_agent).map(([agent, count]) => (
                    <span key={agent} className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-700/30 text-zinc-400">
                      {agent}: {count}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {stats.pending_migration > 0 && (
              <div className="border-t border-zinc-700/30 pt-2 mt-2 text-[10px] text-amber-400">
                {stats.pending_migration} raw memories being migrated to facts in background...
              </div>
            )}
          </div>
        )}

        {/* Search bar */}
        <div className="flex items-center gap-2">
          <div className="flex-1 relative">
            <input
              data-testid="memory-search-input"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSearch()}
              placeholder="Search knowledge (semantic + keyword)..."
              className="w-full bg-zinc-800/50 border border-zinc-700/50 rounded-lg pl-9 pr-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500"
            />
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500" />
          </div>
          {searchResults !== null && (
            <button onClick={() => { setSearchQuery(""); setSearchResults(null); }} className="p-2 text-zinc-500 hover:text-zinc-300 transition-colors">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            onClick={handleSearch}
            disabled={searching || !searchQuery.trim()}
            data-testid="memory-search-btn"
            className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-30 transition-colors"
          >
            {searching ? "..." : "Search"}
          </button>
        </div>

        {/* Add manual fact */}
        {showAdd && (
          <div className="bg-zinc-800/30 border border-zinc-700/30 rounded-lg p-3 space-y-2">
            <textarea
              value={newContent}
              onChange={e => setNewContent(e.target.value)}
              placeholder="Add a fact or note to knowledge base..."
              rows={3}
              className="w-full bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 resize-none"
              data-testid="memory-add-content"
            />
            <div className="flex items-center gap-2">
              <button
                onClick={handleAdd}
                disabled={saving || !newContent.trim()}
                className="px-3 py-1.5 rounded-lg bg-zinc-100 text-zinc-900 text-xs font-semibold hover:bg-zinc-200 disabled:opacity-30 transition-colors"
              >
                {saving ? "Saving..." : "Save"}
              </button>
              <button onClick={() => setShowAdd(false)} className="text-xs text-zinc-500 hover:text-zinc-300">Cancel</button>
            </div>
          </div>
        )}

        {/* Results label */}
        {searchResults !== null && (
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest">
            {searchResults.length} result{searchResults.length !== 1 ? "s" : ""} for "{searchQuery}"
          </div>
        )}

        {/* Fact list */}
        <div className="space-y-2 max-h-[350px] overflow-y-auto">
          {displayList.length === 0 ? (
            <div className="text-center py-6 text-xs text-zinc-600">
              {searchResults !== null ? "No matching facts" : "No knowledge stored yet. Conversations, emails, and screen captures are automatically distilled into facts."}
            </div>
          ) : (
            displayList.map((mem, i) => (
              <FactCard key={i} fact={mem} isSearch={searchResults !== null} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function FactCard({ fact, isSearch }) {
  const [expanded, setExpanded] = useState(false);
  const content = fact.content || "";
  const preview = content.length > 150 ? content.substring(0, 150) + "..." : content;
  const factType = fact.metadata?.type;
  const source = fact.source || "";
  const sourceInfo = SOURCE_LABELS[source];

  return (
    <div
      className="bg-zinc-800/30 border border-zinc-700/20 rounded-lg px-3 py-2.5 hover:border-zinc-600/30 transition-colors cursor-pointer"
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1">
            {factType && (
              <span className={`text-[9px] font-medium px-1.5 py-0.5 rounded ${TYPE_COLORS[factType] || "bg-zinc-700/30 text-zinc-400"}`}>
                {factType.replace("_", " ")}
              </span>
            )}
            {sourceInfo && (
              <span className={`text-[9px] px-1.5 py-0.5 rounded ${sourceInfo.color}`}>{sourceInfo.label}</span>
            )}
          </div>
          <p className="text-xs text-zinc-300 whitespace-pre-wrap break-words">
            {expanded ? content : preview}
          </p>
          <div className="flex items-center gap-2 mt-1.5 text-[9px] text-zinc-600">
            <span>{timeAgo(fact.created_at)}</span>
            {isSearch && fact.similarity && (
              <>
                <span className="text-zinc-700">|</span>
                <span className="text-emerald-400">{(fact.similarity * 100).toFixed(0)}% match</span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
