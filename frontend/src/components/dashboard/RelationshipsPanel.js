import { useState, useEffect, useCallback } from "react";
import { Users, RefreshCw, User, Briefcase, ArrowRight, Mail } from "lucide-react";

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

function PersonCard({ person }) {
  const rel = RELATIONSHIP_COLORS[person.relationship] || RELATIONSHIP_COLORS.unknown;
  const latestContext = person.context_history?.slice(-1)[0]?.text || "";

  return (
    <div
      data-testid={`person-card-${person.name_key}`}
      className={`${rel.bg} ${rel.border} border rounded-xl p-4 hover:brightness-110 transition-all`}
    >
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

          <div className="flex items-center gap-1.5 text-xs text-zinc-500">
            {person.email_address && (
              <>
                <Mail size={10} className="text-zinc-600" />
                <span className="truncate">{person.email_address}</span>
              </>
            )}
          </div>

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

  const fetchPeople = useCallback(async () => {
    if (!authenticated) return;
    try {
      const r = await rpc("relationships.list");
      if (r?.people) setPeople(r.people);
    } catch {}
    setLoading(false);
  }, [authenticated, rpc]);

  useEffect(() => {
    fetchPeople();
  }, [fetchPeople]);

  // Group by relationship type
  const grouped = {};
  people.forEach((p) => {
    const rel = p.relationship || "unknown";
    if (!grouped[rel]) grouped[rel] = [];
    grouped[rel].push(p);
  });

  const groupOrder = ["manager", "report", "peer", "colleague", "client", "vendor", "external", "unknown"];

  return (
    <div className="max-w-4xl" data-testid="relationships-panel">
      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="text-sm text-zinc-500">
            People discovered from your conversations and emails. OverClaw passively builds this map as you chat.
          </p>
        </div>
        <button
          onClick={fetchPeople}
          className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          data-testid="relationships-refresh"
        >
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

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
                    <PersonCard key={p.name_key} person={p} />
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
