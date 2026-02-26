import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Paperclip, Loader2, ChevronDown, ChevronUp, Bot, User, Wrench } from "lucide-react";
import { ScreenShare, ScreenShareButton } from "./ScreenShare";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

function ToolCallBadge({ call }) {
  const [expanded, setExpanded] = useState(false);
  const name = call.tool || call.function?.name || call.name || "tool";
  const args = call.args || call.function?.arguments || call.arguments;
  let parsedArgs = args;
  if (typeof args === "string") {
    try { parsedArgs = JSON.parse(args); } catch { parsedArgs = args; }
  }
  const result = call.result || call.output;

  return (
    <div className="my-2 rounded-lg border border-zinc-800/80 bg-zinc-900/50 overflow-hidden" data-testid={`tool-call-${name}`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-zinc-800/30 transition-colors"
      >
        <Wrench className="w-3 h-3 text-indigo-400 flex-shrink-0" />
        <span className="text-xs font-mono text-indigo-300">{name}</span>
        {parsedArgs && typeof parsedArgs === "object" && (
          <span className="text-[10px] text-zinc-600 truncate max-w-[200px]">
            {Object.entries(parsedArgs).slice(0, 2).map(([k, v]) =>
              `${k}=${typeof v === "string" ? v.slice(0, 30) : JSON.stringify(v).slice(0, 30)}`
            ).join(", ")}
          </span>
        )}
        <div className="ml-auto flex-shrink-0">
          {expanded ? <ChevronUp className="w-3 h-3 text-zinc-600" /> : <ChevronDown className="w-3 h-3 text-zinc-600" />}
        </div>
      </button>
      {expanded && (
        <div className="border-t border-zinc-800/60 px-3 py-2 space-y-2">
          {parsedArgs && (
            <div>
              <div className="text-[9px] text-zinc-600 uppercase tracking-wider mb-1">arguments</div>
              <pre className="text-[11px] text-zinc-400 font-mono whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
                {typeof parsedArgs === "string" ? parsedArgs : JSON.stringify(parsedArgs, null, 2)}
              </pre>
            </div>
          )}
          {result && (
            <div>
              <div className="text-[9px] text-zinc-600 uppercase tracking-wider mb-1">result</div>
              <pre className="text-[11px] text-emerald-400/80 font-mono whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
                {typeof result === "string" ? result : JSON.stringify(result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MessageBubble({ msg }) {
  const isUser = msg.role === "user";
  const hasToolCalls = msg.tool_calls?.length > 0;

  if (isUser) {
    return (
      <div className="flex justify-end px-4 md:px-16 py-3 animate-fade-in" data-testid="user-message">
        <div className="flex items-start gap-3 max-w-[70%]">
          <div className="bg-zinc-800 text-zinc-100 rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
            {msg.content}
          </div>
          <div className="w-7 h-7 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center flex-shrink-0 mt-0.5">
            <User className="w-3.5 h-3.5 text-zinc-400" />
          </div>
        </div>
      </div>
    );
  }

  // Agent message (may have tool_calls AND content)
  return (
    <div className="animate-fade-in">
      {/* Tool calls first */}
      {hasToolCalls && (
        <div className="px-4 md:px-16 py-1">
          {msg.tool_calls.map((tc, i) => <ToolCallBadge key={i} call={tc} />)}
        </div>
      )}
      {/* Text content */}
      {msg.content && (
        <div className="flex px-4 md:px-16 py-3" data-testid="agent-message">
          <div className="flex items-start gap-3 max-w-[85%]">
            <div className="w-7 h-7 rounded-full bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Bot className="w-3.5 h-3.5 text-indigo-400" />
            </div>
            <div className="bg-zinc-900/60 border border-zinc-800/60 rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed assistant-message">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ node, inline, className, children, ...props }) {
                    if (inline) {
                      return <code className="bg-zinc-800 text-indigo-300 px-1.5 py-0.5 rounded text-xs font-mono" {...props}>{children}</code>;
                    }
                    return (
                      <pre className="bg-zinc-950 border border-zinc-800/60 rounded-lg p-3 my-2 overflow-x-auto">
                        <code className="text-xs text-zinc-300 font-mono" {...props}>{children}</code>
                      </pre>
                    );
                  },
                  p: ({ children }) => <p className="mb-2 last:mb-0 text-zinc-200">{children}</p>,
                  ul: ({ children }) => <ul className="list-disc list-inside mb-2 space-y-1 text-zinc-300">{children}</ul>,
                  ol: ({ children }) => <ol className="list-decimal list-inside mb-2 space-y-1 text-zinc-300">{children}</ol>,
                  h1: ({ children }) => <h1 className="text-lg font-semibold text-zinc-100 mb-2 mt-3" style={{ fontFamily: 'var(--font-heading)' }}>{children}</h1>,
                  h2: ({ children }) => <h2 className="text-base font-semibold text-zinc-100 mb-2 mt-2" style={{ fontFamily: 'var(--font-heading)' }}>{children}</h2>,
                  h3: ({ children }) => <h3 className="text-sm font-semibold text-zinc-200 mb-1 mt-2" style={{ fontFamily: 'var(--font-heading)' }}>{children}</h3>,
                  a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer" className="text-indigo-400 hover:text-indigo-300 underline underline-offset-2">{children}</a>,
                  blockquote: ({ children }) => <blockquote className="border-l-2 border-indigo-500/40 pl-3 italic text-zinc-400 my-2">{children}</blockquote>,
                  table: ({ children }) => <div className="overflow-x-auto my-2"><table className="min-w-full text-xs">{children}</table></div>,
                  th: ({ children }) => <th className="border border-zinc-700 bg-zinc-800/50 px-3 py-1.5 text-left text-zinc-300 font-medium">{children}</th>,
                  td: ({ children }) => <td className="border border-zinc-800 px-3 py-1.5 text-zinc-400">{children}</td>,
                }}
              >
                {msg.content || ""}
              </ReactMarkdown>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex px-4 md:px-16 py-3 animate-fade-in" data-testid="typing-indicator">
      <div className="flex items-start gap-3">
        <div className="w-7 h-7 rounded-full bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center flex-shrink-0">
          <Bot className="w-3.5 h-3.5 text-indigo-400" />
        </div>
        <div className="bg-zinc-900/60 border border-zinc-800/60 rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
          <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
          <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
        </div>
      </div>
    </div>
  );
}

export function ChatView({ rpc, authenticated, sessionId, connected, onEvent, offEvent }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [liveToolCalls, setLiveToolCalls] = useState([]);
  const messagesEndRef = useRef(null);
  const scrollContainerRef = useRef(null);
  const inputRef = useRef(null);
  const isAtBottomRef = useRef(true);
  const fileInputRef = useRef(null);
  const screenShareRef = useRef(null);
  const [screenSharing, setScreenSharing] = useState(false);

  const scrollToBottom = useCallback(() => {
    if (isAtBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, []);

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const threshold = 80;
    isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
  }, []);

  // Load messages for current session
  useEffect(() => {
    setMessages([]);
    if (!authenticated || !sessionId) return;
    rpc("chat.history", { session_id: sessionId }).then((r) => {
      if (r?.messages) {
        setMessages(r.messages);
        setTimeout(() => {
          isAtBottomRef.current = true;
          scrollToBottom();
        }, 50);
      }
    }).catch(() => {});

    const interval = setInterval(() => {
      rpc("chat.history", { session_id: sessionId }).then((r) => {
        if (r?.messages) {
          setMessages((prev) => {
            if (JSON.stringify(prev) !== JSON.stringify(r.messages)) {
              setTimeout(scrollToBottom, 50);
              return r.messages;
            }
            return prev;
          });
        }
      }).catch(() => {});
    }, 2000);

    // Listen for real-time Slack/cross-channel events
    const handleChatEvent = (params) => {
      if (params?.session_id === sessionId) {
        // Capture live tool calls during agent execution
        if (params.type === "tool_call" && params.status === "executing") {
          setLiveToolCalls((prev) => [...prev, {
            tool: params.tool,
            args: params.args,
          }]);
          setTimeout(scrollToBottom, 50);
          return;
        }
        // Immediate refresh when activity on the current session
        rpc("chat.history", { session_id: sessionId }).then((r) => {
          if (r?.messages) {
            setMessages(r.messages);
            setTimeout(scrollToBottom, 50);
          }
        }).catch(() => {});
      }
    };
    if (onEvent) onEvent("chat.event", handleChatEvent);

    return () => {
      clearInterval(interval);
      if (offEvent) offEvent("chat.event", handleChatEvent);
    };
  }, [authenticated, sessionId, rpc, scrollToBottom, onEvent, offEvent]);

  useEffect(scrollToBottom, [messages, scrollToBottom]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || !sessionId || sending) return;

    setInput("");
    setSending(true);

    try {
      // Auto-capture screen if sharing
      let currentAttachments = [...attachments];
      if (screenSharing && screenShareRef.current) {
        const blob = await screenShareRef.current.captureFrame();
        if (blob) {
          const formData = new FormData();
          formData.append("file", blob, `screen-capture-${Date.now()}.png`);
          const res = await fetch(`${BACKEND_URL}/api/upload`, { method: "POST", body: formData });
          if (res.ok) {
            const data = await res.json();
            if (data.ok) {
              currentAttachments.push({ ...data, original_name: "Screen Capture" });
            }
          }
        }
      }

      const payload = { session_id: sessionId, message: text };
      if (currentAttachments.length > 0) {
        payload.attachments = currentAttachments.map((a) => ({
          file_path: a.file_path,
          original_name: a.original_name,
          type: a.type,
        }));
      }
      setAttachments([]);
      setLiveToolCalls([]);
      const r = await rpc("chat.send", payload);
      setLiveToolCalls([]);
      if (r?.messages) {
        setMessages(r.messages);
      }
    } catch (err) {
      console.error("Send error:", err);
      setLiveToolCalls([]);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch(`${BACKEND_URL}/api/upload`, { method: "POST", body: formData });
      const data = await res.json();
      if (data.ok) {
        setAttachments((prev) => [...prev, data]);
      }
    } catch (err) {
      console.error("Upload error:", err);
    }
    e.target.value = "";
  };

  const handleScreenCapture = useCallback(async (blob) => {
    // Upload the captured frame as an attachment
    const formData = new FormData();
    formData.append("file", blob, `screen-capture-${Date.now()}.jpg`);
    try {
      const res = await fetch(`${BACKEND_URL}/api/upload`, { method: "POST", body: formData });
      if (!res.ok) {
        console.error("Screen capture upload failed:", res.status);
        return;
      }
      const data = await res.json();
      if (data.ok) {
        setAttachments((prev) => [...prev, { ...data, original_name: "Screen Capture" }]);
      }
    } catch (err) {
      console.error("Screen capture upload error:", err);
    }
  }, []);

  if (!sessionId) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-indigo-600/10 border border-indigo-500/20 flex items-center justify-center mx-auto">
            <Bot className="w-6 h-6 text-indigo-400" />
          </div>
          <p className="text-sm text-zinc-500">Select a session or start a new chat</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col" data-testid="chat-view">
      {/* Messages */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto py-4"
      >
        {messages.length === 0 && !sending && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-3">
              <div className="w-14 h-14 rounded-2xl bg-indigo-600/10 border border-indigo-500/20 flex items-center justify-center mx-auto">
                <Bot className="w-7 h-7 text-indigo-400" />
              </div>
              <div>
                <p className="text-base font-medium text-zinc-300" style={{ fontFamily: 'var(--font-heading)' }}>
                  How can I help?
                </p>
                <p className="text-xs text-zinc-600 mt-1">Type a message to get started</p>
              </div>
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <MessageBubble key={`${i}-${msg.role}`} msg={msg} />
        ))}
        {sending && liveToolCalls.length > 0 && (
          <div className="animate-fade-in">
            <div className="px-4 md:px-16 py-1">
              {liveToolCalls.map((tc, i) => <ToolCallBadge key={i} call={tc} />)}
            </div>
          </div>
        )}
        {sending && <TypingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {/* Screen share preview (above input when active) */}
      <div className="px-4 md:px-16">
        <ScreenShare ref={screenShareRef} onCapture={handleScreenCapture} />
      </div>

      {/* Attachments preview */}
      {attachments.length > 0 && (
        <div className="px-4 md:px-16 py-2 flex gap-2 flex-wrap">
          {attachments.map((a, i) => (
            <div key={i} className="flex items-center gap-2 bg-zinc-800 rounded-lg px-3 py-1.5 text-xs text-zinc-300 border border-zinc-700">
              <Paperclip className="w-3 h-3 text-zinc-500" />
              <span className="truncate max-w-[150px]">{a.original_name}</span>
              <button
                onClick={() => setAttachments((p) => p.filter((_, idx) => idx !== i))}
                className="text-zinc-600 hover:text-rose-400 ml-1"
              >x</button>
            </div>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className="px-4 md:px-16 pb-4 pt-2" data-testid="chat-input-area">
        <div className="flex items-end gap-2 bg-zinc-900/60 border border-zinc-800/80 rounded-xl px-3 py-2 focus-within:border-indigo-500/40 transition-colors">
          <button
            data-testid="attach-btn"
            onClick={() => fileInputRef.current?.click()}
            className="p-2 text-zinc-600 hover:text-zinc-400 transition-colors flex-shrink-0"
          >
            <Paperclip className="w-4 h-4" />
          </button>
          <ScreenShareButton
            onClick={async () => {
              if (screenSharing) {
                screenShareRef.current?.stop();
                setScreenSharing(false);
              } else {
                await screenShareRef.current?.start();
                setScreenSharing(true);
              }
            }}
            disabled={sending}
            active={screenSharing}
          />
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={handleFileUpload}
          />
          <textarea
            ref={inputRef}
            data-testid="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Message OverClaw..."
            rows={1}
            className="flex-1 bg-transparent text-sm text-zinc-200 placeholder:text-zinc-600 resize-none outline-none py-2 max-h-32"
            style={{ fontFamily: 'var(--font-body)' }}
          />
          <button
            data-testid="send-btn"
            onClick={handleSend}
            disabled={!input.trim() || sending}
            className={`p-2 rounded-lg transition-all flex-shrink-0 ${
              input.trim() && !sending
                ? "bg-indigo-600 text-white hover:bg-indigo-500 shadow-lg shadow-indigo-500/20"
                : "text-zinc-700"
            }`}
          >
            {sending
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : <Send className="w-4 h-4" />
            }
          </button>
        </div>
        <p className="text-center text-[10px] text-zinc-700 mt-2">
          OverClaw can make mistakes. Verify important information.
        </p>
      </div>
    </div>
  );
}
