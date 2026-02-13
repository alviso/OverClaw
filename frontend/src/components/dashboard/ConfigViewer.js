import { Terminal, Copy, Check } from "lucide-react";
import { useState } from "react";

export function ConfigViewer({ config }) {
  const [copied, setCopied] = useState(false);
  const configStr = config ? JSON.stringify(config, null, 2) : "Loading...";

  const handleCopy = () => {
    navigator.clipboard.writeText(configStr);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div data-testid="config-viewer" className="bg-zinc-900/60 border border-zinc-800/60 rounded-lg overflow-hidden hover:border-zinc-700/80 transition-colors h-full flex flex-col">
      <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-zinc-400" />
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-widest">System Config</span>
        </div>
        <button
          data-testid="config-copy-btn"
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 px-2 py-1 rounded hover:bg-zinc-800 transition-colors"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <div className="flex-1 overflow-auto p-4 bg-[#0A0A0B]">
        <pre className="text-xs leading-relaxed font-mono">
          <ConfigHighlight json={configStr} />
        </pre>
      </div>
    </div>
  );
}

function ConfigHighlight({ json }) {
  if (!json || json === "Loading...") {
    return <span className="text-zinc-600">{json}</span>;
  }
  // Simple JSON syntax highlighting
  const highlighted = json
    .replace(/"([^"]+)":/g, '<span class="text-blue-400">"$1"</span>:')
    .replace(/: "([^"]*)"/g, ': <span class="text-emerald-400">"$1"</span>')
    .replace(/: (\d+)/g, ': <span class="text-amber-400">$1</span>')
    .replace(/: (true|false)/g, ': <span class="text-purple-400">$1</span>');

  return <code dangerouslySetInnerHTML={{ __html: highlighted }} />;
}
