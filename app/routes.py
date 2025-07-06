from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response
import logging
from .state import state
import asyncio
from .config import config
from . import gitlab
from . import jinja_filters

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
    jinja_filters.add_filters(templates)
    manager = ConnectionManager()

    def broadcaster_listener(msg: str):
        nonlocal manager
        # if "[INFO]" in msg, then msg = <span>msg up to [INFO]</span><span class="has-text-info">[INFO]</span></span>msg for everything after [INFO]</span>
        log_levels = [
            ("[INFO]", "has-text-info"),
            ("[WARNING]", "has-text-warning"),
            ("[ERROR]", "has-text-danger"),
            ("[DEBUG]", "has-text-grey")
        ]

        for level, color_class in log_levels:
            if level in msg:
                parts = msg.split(level, 1)
                if len(parts) == 2:
                    before_level, after_level = parts
                    html = f"""
                        <div id='scan-output' hx-swap-oob='beforeend'>
                            <div><span>{before_level}</span><span class="{color_class}">{level}</span><span>{after_level}</span></div>
                        </div>
                    """
                else:
                    html = f"""
                        <div id='scan-output' hx-swap-oob='beforeend'>
                            <div>{msg}</div>
                        </div>
                    """
                asyncio.create_task(manager.broadcast(html))
                return

        # No log level found, use default format
        html = f"""
            <div id='scan-output' hx-swap-oob='beforeend'>
                <div>{msg}</div>
            </div>
        """
        asyncio.create_task(manager.broadcast(html))
    state.broadcaster.register(broadcaster_listener)

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        # Get pagination parameters
        page = int(request.query_params.get("page", 1))
        per_page = int(request.query_params.get("per_page", 2))
        
        # Ensure page is at least 1
        page = max(1, page)
        per_page = max(1, min(100, per_page))  # Limit per_page between 1 and 100
        
        # Get paginated commits
        commits, total_count = state.commit.items(page=page, per_page=per_page)
        
        # Calculate pagination info
        total_pages = (total_count + per_page - 1) // per_page
        has_prev = page > 1
        has_next = page < total_pages
        
        return templates.TemplateResponse("index.html", {
            "request": request, 
            "state": state,
            "commits": commits,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_prev": has_prev,
                "has_next": has_next,
                "prev_page": page - 1 if has_prev else None,
                "next_page": page + 1 if has_next else None
            }
        })

    @app.post("/api/webhooks/gitlab", response_class=HTMLResponse)
    async def gitlab_webhook(request: Request):
        auth = request.headers.get("authorization")
        if not auth or not auth.lower().startswith("bearer ") or auth[7:] != config.webhook_api_key:
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)

        body = (await request.body()).decode('utf-8')
        _logger.info(f"GitLab webhook body: {body}")
        try:
            data = await request.json()
        except Exception:
            _logger.error(f"Failed to parse GitLab webhook body as json")
            return Response(status_code=400)

        event = request.headers.get("x-gitlab-event")
        gitlab.handle_deployment_webhook(data, event)
        return Response(status_code=200)

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


    @app.get("/hc")
    async def health_check():
        return "OK"

    @app.post("/run-scan")
    async def force_start_scan(request: Request):
        await state.scanner_message_queue.put("scan_now")
        return templates.TemplateResponse("next_scan.html", {"request": request, "state": state, "swap": True})

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
