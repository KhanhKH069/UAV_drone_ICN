import logging
from collections import defaultdict
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger("uav_drone.connmgr")


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = defaultdict(list)

    async def connect(self, ws: WebSocket, session_id: str, direction: str = ""):
        await ws.accept()
        self._connections[session_id].append(ws)
        logger.debug(
            f"Connect: {session_id[:8]} ({direction}), total={len(self._connections)}"
        )

    def register(self, ws: WebSocket, session_id: str, direction: str = ""):
        self._connections[session_id].append(ws)
        logger.debug(
            f"Register: {session_id[:8]} ({direction}), total={len(self._connections)}"
        )

    def disconnect(self, ws: WebSocket, session_id: str):
        conns = self._connections.get(session_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(session_id, None)

    def count(self, session_id: str | None = None) -> int:
        """Return the number of active connections (total, or per session_id)."""
        if session_id:
            return len(self._connections.get(session_id, []))
        return sum(len(v) for v in self._connections.values())

    async def broadcast(self, session_id: str, message: dict):
        for ws in self._connections.get(session_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                pass
