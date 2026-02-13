import { useState, useEffect, useRef, useCallback } from "react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

function buildWsUrl() {
  if (BACKEND_URL) {
    return BACKEND_URL.replace(/^http/, "ws") + "/api/gateway";
  }
  // No backend URL configured — derive from current page origin (Docker/production)
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/gateway`;
}

const WS_URL = buildWsUrl();
const GATEWAY_TOKEN = "dev-token-change-me";

export function useGatewayWs() {
  const [connected, setConnected] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [gatewayInfo, setGatewayInfo] = useState(null);
  const [latestNotification, setLatestNotification] = useState(null);
  // Bumps on every reconnect so consumers can re-fetch data
  const [reconnectCount, setReconnectCount] = useState(0);
  const wsRef = useRef(null);
  const pendingRef = useRef({});
  const idCounter = useRef(0);
  const reconnectTimer = useRef(null);
  const mountedRef = useRef(true);
  // Track whether we've ever been authenticated (for reconnect vs first connect)
  const wasAuthenticatedRef = useRef(false);
  // Queue RPCs issued while reconnecting, replay once re-authenticated
  const rpcQueueRef = useRef([]);
  // Event listeners for server push events (e.g., workspace.stream)
  const eventListenersRef = useRef({});

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) return;

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) { ws.close(); return; }
        setConnected(true);
        // Client-side keepalive: send ping every 20s to keep proxy alive
        const pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ jsonrpc: "2.0", method: "ping" }));
          } else {
            clearInterval(pingInterval);
          }
        }, 20000);
        ws._pingInterval = pingInterval;
      };

      ws.onmessage = (evt) => {
        if (!mountedRef.current) return;
        try {
          const msg = JSON.parse(evt.data);

          // Handle server push events (no id)
          if (!msg.id && msg.method) {
            if (msg.method === "gateway.welcome") {
              setGatewayInfo(msg.params?.gateway);
              // Auto-authenticate
              const authId = `auth-${Date.now()}`;
              ws.send(JSON.stringify({
                jsonrpc: "2.0",
                id: authId,
                method: "connect",
                params: { token: GATEWAY_TOKEN, client_type: "dashboard" },
              }));
              pendingRef.current[authId] = {
                resolve: (result) => {
                  if (result?.ok) {
                    setAuthenticated(true);
                    setReconnecting(false);
                    setGatewayInfo(result.gateway);
                    wasAuthenticatedRef.current = true;
                    // Signal reconnection to consumers
                    setReconnectCount(c => c + 1);
                    // Flush any queued RPCs
                    const queue = rpcQueueRef.current.splice(0);
                    queue.forEach(({ method, params, resolve, reject }) => {
                      const id = `rpc-${++idCounter.current}-${Date.now()}`;
                      pendingRef.current[id] = { resolve, reject };
                      ws.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
                      const timeoutMs = method === "chat.send" ? 180000 : 15000;
                      setTimeout(() => {
                        if (pendingRef.current[id]) {
                          delete pendingRef.current[id];
                          reject(new Error("RPC timeout"));
                        }
                      }, timeoutMs);
                    });
                  }
                },
                reject: () => {},
              };
            }
            // gateway.ping — just ignore (keepalive)
            if (msg.method === "notification.new") {
              setLatestNotification(msg.params);
            }
            // Dispatch to registered event listeners
            const listeners = eventListenersRef.current[msg.method];
            if (listeners) {
              listeners.forEach(fn => { try { fn(msg.params); } catch(e) { console.error(e); } });
            }
            return;
          }

          // Handle RPC response (has id)
          if (msg.id && pendingRef.current[msg.id]) {
            const { resolve, reject } = pendingRef.current[msg.id];
            delete pendingRef.current[msg.id];
            if (msg.error) {
              reject(msg.error);
            } else {
              resolve(msg.result);
            }
          }
        } catch (e) {
          console.error("[GW] WS parse error:", e);
        }
      };

      ws.onclose = () => {
        if (ws._pingInterval) clearInterval(ws._pingInterval);
        wsRef.current = null;

        // Reject only in-flight RPCs (queued ones survive the reconnect)
        Object.values(pendingRef.current).forEach(p => p.reject?.(new Error("Connection closed")));
        pendingRef.current = {};

        if (wasAuthenticatedRef.current && mountedRef.current) {
          // Seamless reconnect: keep authenticated=true, show reconnecting state
          setConnected(false);
          setReconnecting(true);
          reconnectTimer.current = setTimeout(connect, 1500);
        } else {
          setConnected(false);
          setAuthenticated(false);
          if (mountedRef.current) {
            reconnectTimer.current = setTimeout(connect, 2000);
          }
        }
      };

      ws.onerror = () => {};
    } catch (err) {
      console.error("[GW] WS connect error:", err);
      if (mountedRef.current) {
        reconnectTimer.current = setTimeout(connect, 2000);
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  const rpc = useCallback((method, params = {}) => {
    return new Promise((resolve, reject) => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        const id = `rpc-${++idCounter.current}-${Date.now()}`;
        pendingRef.current[id] = { resolve, reject };
        ws.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
        const timeoutMs = method === "chat.send" ? 180000 : 15000;
        setTimeout(() => {
          if (pendingRef.current[id]) {
            delete pendingRef.current[id];
            reject(new Error("RPC timeout"));
          }
        }, timeoutMs);
      } else if (wasAuthenticatedRef.current) {
        // Connection dropped but we expect to reconnect — queue the RPC
        rpcQueueRef.current.push({ method, params, resolve, reject });
        // Timeout even queued RPCs so callers aren't stuck forever
        setTimeout(() => {
          const idx = rpcQueueRef.current.findIndex(q => q.resolve === resolve);
          if (idx !== -1) {
            rpcQueueRef.current.splice(idx, 1);
            reject(new Error("RPC timeout (queued)"));
          }
        }, 15000);
      } else {
        reject(new Error("Not connected"));
      }
    });
  }, []);

  const onEvent = useCallback((method, fn) => {
    if (!eventListenersRef.current[method]) {
      eventListenersRef.current[method] = new Set();
    }
    eventListenersRef.current[method].add(fn);
  }, []);

  const offEvent = useCallback((method, fn) => {
    const set = eventListenersRef.current[method];
    if (set) {
      set.delete(fn);
      if (set.size === 0) delete eventListenersRef.current[method];
    }
  }, []);

  return { connected, authenticated, reconnecting, gatewayInfo, rpc, reconnectCount, latestNotification, onEvent, offEvent };
}
