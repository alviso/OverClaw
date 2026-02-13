"""
WebSocket connection manager for the Gateway.
Tracks connected clients, handles broadcast.
Inspired by OpenClaw's server-ws-runtime.ts.
"""
import json
import time
import uuid
import logging
from typing import Optional
from fastapi import WebSocket

logger = logging.getLogger("gateway.ws")


class GatewayClient:
    def __init__(self, ws: WebSocket, client_id: str, client_type: str = "dashboard"):
        self.ws = ws
        self.client_id = client_id
        self.client_type = client_type
        self.connected_at = time.time()
        self.authenticated = False
        self.last_ping = time.time()


class WsManager:
    def __init__(self):
        self._clients: dict[str, GatewayClient] = {}

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def clients(self) -> list[dict]:
        return [
            {
                "client_id": c.client_id,
                "client_type": c.client_type,
                "connected_at": c.connected_at,
                "authenticated": c.authenticated,
            }
            for c in self._clients.values()
        ]

    def add(self, ws: WebSocket, client_type: str = "dashboard") -> GatewayClient:
        client_id = str(uuid.uuid4())[:8]
        client = GatewayClient(ws, client_id, client_type)
        self._clients[client_id] = client
        logger.info(f"Client connected: {client_id} ({client_type})")
        return client

    def remove(self, client_id: str):
        if client_id in self._clients:
            del self._clients[client_id]
            logger.info(f"Client disconnected: {client_id}")

    async def send_to(self, client_id: str, data: dict):
        client = self._clients.get(client_id)
        if client:
            try:
                await client.ws.send_json(data)
            except Exception:
                self.remove(client_id)

    async def broadcast(self, data: dict, exclude: Optional[str] = None):
        disconnected = []
        for cid, client in self._clients.items():
            if cid == exclude:
                continue
            if not client.authenticated:
                continue
            try:
                await client.ws.send_json(data)
            except Exception:
                disconnected.append(cid)
        for cid in disconnected:
            self.remove(cid)

    def get_all_clients(self) -> list[GatewayClient]:
        """Return all authenticated clients."""
        return [c for c in self._clients.values() if c.authenticated]
