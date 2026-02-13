import { useState, useRef, useEffect } from "react";
import { Send, Trash2, Bot, User, Loader2, AlertCircle, Wrench, Search, FileText, Terminal } from "lucide-react";

export function QuickTestPanel({ rpc, authenticated }) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Load history on mount
  useEffect(() => {
    if (!authenticated) return;
    rpc("chat.history", { session_id: "main", limit: 50 })
      .then((result) => {
        if (result?.messages) {
          setMessages(result.messages.map(m => ({
            role: m.role,
            content: m.content,
            timestamp: m.timestamp,
          })));
        }
      })
      .catch(() => {});
  }, [authenticated, rpc]);

  const handleSend = async () => {
    if (!input.trim() || loading || !authenticated) return;

    const userText = input.trim();
    setInput("");
    setError(null);

    // Optimistic: add user message
    setMessages(prev => [...prev, { role: "user", content: userText, timestamp: new Date().toISOString() }]);
    setLoading(true);

    try {
      const result = await rpc("chat.send", { session_id: "main", text: userText });
      if (result?.error) {
        setError(result.error);
        setLoading(false);
        return;
      }
      // Add assistant response with tool calls
      setMessages(prev => [...prev, {
        role: "assistant",
        content: result.response,
        tool_calls: result.tool_calls || [],
        timestamp: new Date().toISOString(),
      }]);
    } catch (err) {
      setError(err?.message || "Failed to send message");
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleClear = async () => {
    try {
      await rpc("chat.clear", { session_id: "main" });
      setMessages([]);
      setError(null);
    } catch (err) {
      setError("Failed to clear session");
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div data-testid="quick-test-panel" className="bg-zinc-900/60 border border-zinc-800/60 rounded-lg overflow-hidden hover:border-zinc-700/80 transition-colors h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-zinc-400" />
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-widest">Quick Test</span>
          {loading && (
            <span className="flex items-center gap-1.5 text-[10px] text-blue-400 bg-blue-400/10 px-2 py-0.5 rounded-full">
              <Loader2 className="w-3 h-3 animate-spin" />
              thinking
            </span>
          )}
        </div>
        <button
          data-testid="clear-chat-btn"
          onClick={handleClear}
          className="flex items-center gap-1.5 text-xs text-zinc-600 hover:text-zinc-400 px-2 py-1 rounded hover:bg-zinc-800 transition-colors"
          title="Clear session"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 min-h-[300px] max-h-[500px]">
        {messages.length === 0 && !loading && (
          <div className="text-center py-12">
            <Bot className="w-8 h-8 text-zinc-700 mx-auto mb-3" />
            <p className="text-sm text-zinc-600">Send a message to test the agent</p>
            <p className="text-xs text-zinc-700 mt-1 font-mono">session: main / model: openai/gpt-4o</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}

        {loading && (
          <div className="flex items-start gap-3">
            <div className="w-6 h-6 rounded-md bg-blue-400/10 border border-blue-400/20 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Bot className="w-3.5 h-3.5 text-blue-400" />
            </div>
            <div className="bg-zinc-800/40 border border-zinc-700/30 rounded-lg px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" style={{ animationDelay: "0.2s" }} />
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" style={{ animationDelay: "0.4s" }} />
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 px-3 py-2 bg-rose-400/10 border border-rose-400/20 rounded-lg text-xs text-rose-400">
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
            {error}
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-zinc-800/60 p-3">
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            data-testid="chat-input"
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={authenticated ? "Send a message..." : "Connecting..."}
            disabled={!authenticated || loading}
            className="flex-1 bg-zinc-800/50 border border-zinc-700/50 rounded-lg px-4 py-2.5 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 transition-colors disabled:opacity-50"
          />
          <button
            data-testid="send-btn"
            onClick={handleSend}
            disabled={!input.trim() || loading || !authenticated}
            className="w-10 h-10 rounded-lg bg-zinc-100 text-zinc-900 flex items-center justify-center hover:bg-zinc-200 disabled:opacity-30 disabled:cursor-not-allowed active:scale-95 transition-transform"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }) {
  const isUser = message.role === "user";
  const toolCalls = message.tool_calls || [];

  if (isUser) {
    return (
      <div className="flex items-start gap-3 flex-row-reverse">
        <div className="w-6 h-6 rounded-md bg-zinc-700 border border-zinc-600 flex items-center justify-center flex-shrink-0 mt-0.5">
          <User className="w-3.5 h-3.5 text-zinc-300" />
        </div>
        <div className="max-w-[85%] rounded-lg px-3 py-2 text-xs leading-relaxed bg-zinc-800 text-zinc-200 border border-zinc-700/50">
          <span className="whitespace-pre-wrap break-words">{message.content}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3">
      <div className="w-6 h-6 rounded-md bg-blue-400/10 border border-blue-400/20 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Bot className="w-3.5 h-3.5 text-blue-400" />
      </div>
      <div className="flex-1 min-w-0 space-y-1.5">
        {toolCalls.length > 0 && (
          <div className="space-y-1">
            {toolCalls.map((tc, i) => (
              <ToolCallBadge key={i} toolCall={tc} />
            ))}
          </div>
        )}
        <div className="text-xs leading-relaxed text-zinc-300 whitespace-pre-wrap break-words"
          dangerouslySetInnerHTML={{ __html: simpleMarkdown(message.content) }}
        />
      </div>
    </div>
  );
}

function simpleMarkdown(text) {
  if (!text) return "";
  return text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-zinc-100 font-semibold">$1</strong>')
    .replace(/`([^`]+)`/g, '<code class="bg-zinc-800 text-emerald-400 px-1 py-0.5 rounded text-[11px] font-mono">$1</code>')
    .replace(/^### (.+)$/gm, '<div class="text-zinc-200 font-semibold mt-2 mb-1">$1</div>')
    .replace(/^## (.+)$/gm, '<div class="text-zinc-100 font-bold mt-3 mb-1.5 text-sm">$1</div>')
    .replace(/^- (.+)$/gm, '<div class="flex items-start gap-1.5 ml-1"><span class="text-zinc-600 mt-[5px] w-1 h-1 rounded-full bg-zinc-500 flex-shrink-0"></span><span>$1</span></div>')
    .replace(/^\d+\. (.+)$/gm, '<div class="ml-1">$&</div>');
}

function ToolCallBadge({ toolCall }) {
  const [expanded, setExpanded] = useState(false);
  const iconMap = {
    web_search: <Search className="w-3 h-3" />,
    read_file: <FileText className="w-3 h-3" />,
    write_file: <FileText className="w-3 h-3" />,
    list_files: <FileText className="w-3 h-3" />,
    execute_command: <Terminal className="w-3 h-3" />,
  };

  return (
    <div className="bg-zinc-800/60 border border-zinc-700/40 rounded-md text-xs">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 px-3 py-1.5 w-full text-left hover:bg-zinc-700/30 transition-colors rounded-md"
        data-testid={`tool-call-${toolCall.tool}`}
      >
        <Wrench className="w-3 h-3 text-amber-400" />
        <span className="text-amber-400 font-medium">{toolCall.tool}</span>
        <span className="text-zinc-500">
          {toolCall.tool === "web_search" && toolCall.args?.query ? `"${toolCall.args.query}"` : ""}
          {toolCall.tool === "execute_command" && toolCall.args?.command ? `$ ${toolCall.args.command}` : ""}
          {(toolCall.tool === "read_file" || toolCall.tool === "write_file") && toolCall.args?.path ? toolCall.args.path : ""}
        </span>
        <span className="ml-auto text-zinc-600">{expanded ? "−" : "+"}</span>
      </button>
      {expanded && toolCall.result && (
        <div className="px-3 py-2 border-t border-zinc-700/30 bg-[#0A0A0B] rounded-b-md">
          <pre className="text-[11px] text-zinc-400 whitespace-pre-wrap font-mono max-h-[200px] overflow-auto">{toolCall.result}</pre>
        </div>
      )}
    </div>
  );
}
