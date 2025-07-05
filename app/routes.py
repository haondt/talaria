from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import logging
import json
from .state import state

_logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        client_ip = getattr(websocket.client, 'host', None)
        _logger.info(f'New WS connection: {client_ip}')

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        client_ip = getattr(websocket.client, 'host', None)
        _logger.info(f'WS disconnected: {client_ip}')

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # Remove dead connections
                self.active_connections.remove(connection)

def add_routes(app: FastAPI):
    templates = Jinja2Templates(directory="app/templates")
    manager = ConnectionManager()

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        return templates.TemplateResponse("index.html", {"request": request, "state": state})

    @app.get("/chat", response_class=HTMLResponse)
    async def chat_page(request: Request):
        return templates.TemplateResponse("chat.html", {"request": request})

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                # message_data = json.loads(data)
                
                # Broadcast the message to all connected clients
                # await manager.broadcast(json.dumps({
                #     "type": "message",
                #     "user": message_data.get("user", "Anonymous"),
                #     "message": message_data.get("message", ""),
                #     "timestamp": message_data.get("timestamp", "")
                # }))
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    # Counter for HTMX examples
    counter_value = 0

    @app.get("/api/health")
    async def health_check():
        return {"status": "healthy", "connections": len(manager.active_connections)}

    @app.post("/api/counter/increment")
    async def increment_counter():
        global counter_value
        counter_value += 1
        return f"{counter_value}"

    @app.post("/api/counter/decrement")
    async def decrement_counter():
        global counter_value
        counter_value -= 1
        return f"{counter_value}"

    @app.post("/api/counter/reset")
    async def reset_counter():
        global counter_value
        counter_value = 0
        return f"{counter_value}"

    @app.get("/api/realtime-data")
    async def get_realtime_data():
        import time
        return f"""
        <div class="notification is-info">
            <i class="fas fa-clock"></i>
            <strong>Last Updated:</strong> {time.strftime('%H:%M:%S')}
        </div>
        <div class="content">
            <p><strong>Active Connections:</strong> {len(manager.active_connections)}</p>
            <p><strong>Counter Value:</strong> {counter_value}</p>
            <p><strong>Server Time:</strong> {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        """

    @app.post("/api/notify")
    async def send_notification():
        return """
        <div class="notification is-success">
            <button class="delete" onclick="this.parentElement.remove()"></button>
            <i class="fas fa-bell"></i>
            <strong>Notification sent!</strong> This is a test notification.
        </div>
        """
