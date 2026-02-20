import { useState, useEffect, useCallback } from "react";
import { Users, RefreshCw, User, Briefcase, ArrowRight, Mail, Merge, Trash2, X, Check } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL || "";

const RELATIONSHIP_COLORS = {
  manager: { bg: "bg-amber-500/10", border: "border-amber-500/20", text: "text-amber-400", label: "Manager" },
  report: { bg: "bg-sky-500/10", border: "border-sky-500/20", text: "text-sky-400", label: "Report" },
  peer: { bg: "bg-emerald-500/10", border: "border-emerald-500/20", text: "text-emerald-400", label: "Peer" },
  colleague: { bg: "bg-indigo-500/10", border: "border-indigo-500/20", text: "text-indigo-400", label: "Colleague" },
  client: { bg: "bg-violet-500/10", border: "border-violet-500/20", text: "text-violet-400", label: "Client" },
  vendor: { bg: "bg-rose-500/10", border: "border-rose-500/20", text: "text-rose-400", label: "Vendor" },
  external: { bg: "bg-zinc-500/10", border: "border-zinc-500/20", text: "text-zinc-400", label: "External" },
  unknown: { bg: "bg-zinc-500/10", border: "border-zinc-800", text: "text-zinc-500", label: "Unknown" },
};

function timeAgo(isoString) {
  if (!isoString) return "";
  const diff = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(isoString).toLocaleDateString();
}

function PersonCard({ person, mergeMode, selected, onToggle, onDelete }) {
  const rel = RELATIONSHIP_COLORS[person.relationship] || RELATIONSHIP_COLORS.unknown;
  const latestContext = person.context_history?.slice(-1)[0]?.text || "";

  return (
    <div
      data-testid={`person-card-${person.name_key || person.id}`}
      onClick={mergeMode ? () => onToggle(person.id) : undefined}
      className={`${rel.bg} ${rel.border} border rounded-xl p-4 transition-all relative group
        ${mergeMode ? "cursor-pointer" : ""}
        ${selected ? "ring-2 ring-indigo-500 brightness-125" : "hover:brightness-110"}`}
    >
      {/* Delete button (visible on hover, not in merge mode) */}
      {!mergeMode && (
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(person.id, person.name); }}
          className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 p-1 rounded-md bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-all"
          data-testid={`delete-person-${person.id}`}
          title="Remove"
        >
          <Trash2 size={12} />
        </button>
      )}

      {/* Selection indicator in merge mode */}
      {mergeMode && (
        <div className={`absolute top-2 right-2 w-5 h-5 rounded-full border-2 flex items-center justify-center
          ${selected ? "bg-indigo-500 border-indigo-500" : "border-zinc-600"}`}>
          {selected && <Check size={10} className="text-white" />}
        </div>
      )}

      <div className="flex items-start gap-3">
        <div className={`w-9 h-9 rounded-full ${rel.bg} ${rel.border} border flex items-center justify-center flex-shrink-0`}>
          <User size={16} className={rel.text} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-sm font-medium text-zinc-100 truncate">{person.name}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${rel.bg} ${rel.border} border ${rel.text} font-medium`}>
              {rel.label}
            </span>
          </div>

          {person.email_address && (
            <div className="flex items-center gap-1.5 text-xs text-zinc-500">
              <Mail size={10} className="text-zinc-600" />
              <span className="truncate">{person.email_address}</span>
            </div>
          )}

          <div className="flex items-center gap-1.5 text-xs text-zinc-500">
            {person.role && (
              <>
                <Briefcase size={10} className="text-zinc-600" />
                <span className="truncate">{person.role}</span>
              </>
            )}
            {person.role && person.team && <span className="text-zinc-700">@</span>}
            {person.team && <span className="truncate text-zinc-500">{person.team}</span>}
          </div>

          {latestContext && (
            <div className="flex items-start gap-1.5 mt-2">
              <ArrowRight size={10} className="text-zinc-700 mt-0.5 flex-shrink-0" />
              <p className="text-xs text-zinc-500 leading-relaxed">{latestContext}</p>
            </div>
          )}

          {person.aliases?.length > 0 && (
            <div className="mt-1 text-[10px] text-zinc-600">
              aka: {person.aliases.join(", ")}
            </div>
          )}

          <div className="flex items-center gap-3 mt-2 text-[10px] text-zinc-700">
            <span>{person.mention_count || 1}x mentioned</span>
            {person.last_seen && <span>{timeAgo(person.last_seen)}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

export function RelationshipsPanel({ rpc, authenticated }) {
  const [people, setPeople] = useState([]);
  const [loading, setLoading] = useState(true);
  const [mergeMode, setMergeMode] = useState(false);
  const [selected, setSelected] = useState(new Set());

  const fetchPeople = useCallback(async () => {
    if (!authenticated) return;
    try {
      const r = await rpc("relationships.list");
      if (r?.people) setPeople(r.people);
    } catch {}
    setLoading(false);
  }, [authenticated, rpc]);

  useEffect(() => { fetchPeople(); }, [fetchPeople]);

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleMerge = async () => {
    const ids = Array.from(selected);
    if (ids.length < 2) return;
    // The first selected is the "keep" entry
    const keepId = ids[0];
    const mergeIds = ids.slice(1);

    try {
      const res = await fetch(`${API}/api/people/merge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keep_id: keepId, merge_ids: mergeIds }),
      });
      const data = await res.json();
      if (data.ok) {
        setMergeMode(false);
        setSelected(new Set());
        fetchPeople();
      }
    } catch {}
  };

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Remove "${name}" from people?`)) return;
    try {
      await fetch(`${API}/api/people/${id}`, { method: "DELETE" });
      fetchPeople();
    } catch {}
  };

  const cancelMerge = () => {
    setMergeMode(false);
    setSelected(new Set());
  };

  // Group by relationship type
  const grouped = {};
  people.forEach((p) => {
    const rel = p.relationship || "unknown";
    if (!grouped[rel]) grouped[rel] = [];
    grouped[rel].push(p);
  });

  const groupOrder = ["manager", "report", "peer", "colleague", "client", "vendor", "external", "unknown"];
  const selectedNames = people.filter((p) => selected.has(p.id)).map((p) => p.name);

  return (
    <div className="max-w-4xl" data-testid="relationships-panel">
      <div className="flex items-center justify-between mb-6">
        <p className="text-sm text-zinc-500">
          People discovered from your conversations and emails. OverClaw passively builds this map as you chat.
        </p>
        <div className="flex items-center gap-2">
          {mergeMode ? (
            <>
              <button
                onClick={cancelMerge}
                className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 px-2.5 py-1.5 rounded-md border border-zinc-700"
              >
                <X size={12} /> Cancel
              </button>
              <button
                onClick={handleMerge}
                disabled={selected.size < 2}
                data-testid="merge-confirm-btn"
                className="flex items-center gap-1.5 text-xs text-indigo-300 hover:text-indigo-200 px-2.5 py-1.5 rounded-md border border-indigo-500/30 bg-indigo-500/10 disabled:opacity-30"
              >
                <Merge size={12} /> Merge {selected.size} selected
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setMergeMode(true)}
                className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                data-testid="merge-mode-btn"
              >
                <Merge size={12} /> Merge
              </button>
              <button
                onClick={fetchPeople}
                className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                data-testid="relationships-refresh"
              >
                <RefreshCw size={12} /> Refresh
              </button>
            </>
          )}
        </div>
      </div>

      {mergeMode && selected.size > 0 && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-xs text-indigo-300">
          <strong>Merge into:</strong> {selectedNames[0] || "..."}{" "}
          {selectedNames.length > 1 && (
            <span className="text-zinc-400">
              (absorbing: {selectedNames.slice(1).join(", ")})
            </span>
          )}
          <br />
          <span className="text-zinc-500">First selected = keep, others merge into it</span>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-5 h-5 border-2 border-zinc-700 border-t-indigo-500 rounded-full animate-spin" />
        </div>
      ) : people.length === 0 ? (
        <div className="text-center py-20">
          <Users size={32} className="mx-auto text-zinc-800 mb-3" />
          <p className="text-sm text-zinc-600 mb-1">No people discovered yet</p>
          <p className="text-xs text-zinc-700">
            As you mention people in conversations, OverClaw will map out your network here.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {groupOrder.filter((g) => grouped[g]).map((group) => {
            const rel = RELATIONSHIP_COLORS[group] || RELATIONSHIP_COLORS.unknown;
            return (
              <div key={group}>
                <div className="flex items-center gap-2 mb-3">
                  <div className={`w-2 h-2 rounded-full ${rel.text.replace("text-", "bg-")}`} />
                  <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider">
                    {rel.label}s
                  </h3>
                  <span className="text-[10px] text-zinc-700">({grouped[group].length})</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {grouped[group].map((p) => (
                    <PersonCard
                      key={p.id || p.name_key}
                      person={p}
                      mergeMode={mergeMode}
                      selected={selected.has(p.id)}
                      onToggle={toggleSelect}
                      onDelete={handleDelete}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
