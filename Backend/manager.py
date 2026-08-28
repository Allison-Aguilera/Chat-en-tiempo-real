from fastapi import WebSocket
from typing import Dict, List, Tuple

class ConnectionManager:
    def __init__(self):
        # { sala_id: [(user_id, websocket), ...] }
        self.active_connections: Dict[int, List[Tuple[int, WebSocket]]] = {}

    async def connect(self, websocket: WebSocket, sala_id: int, user_id: int):
        await websocket.accept()
        if sala_id not in self.active_connections:
            self.active_connections[sala_id] = []
        self.active_connections[sala_id].append((user_id, websocket))

    def disconnect(self, websocket: WebSocket, sala_id: int):
        if sala_id in self.active_connections:
            self.active_connections[sala_id] = [
                (uid, ws) for uid, ws in self.active_connections[sala_id] if ws != websocket
            ]
            if not self.active_connections[sala_id]:
                del self.active_connections[sala_id]

    async def broadcast(self, message: dict, sala_id: int):
        if sala_id in self.active_connections:
            for _, connection in self.active_connections[sala_id]:
                await connection.send_json(message)

    def usuarios_conectados(self, sala_id: int) -> set:
        """IDs de usuarios actualmente conectados a esta sala."""
        if sala_id not in self.active_connections:
            return set()
        return {uid for uid, _ in self.active_connections[sala_id]}

manager = ConnectionManager()

class NotificationManager:
    def __init__(self):
        # { user_id: websocket }
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int):
        self.active_connections.pop(user_id, None)

    async def notificar(self, user_id: int, payload: dict):
        websocket = self.active_connections.get(user_id)
        if websocket:
            await websocket.send_json(payload)

notification_manager = NotificationManager()