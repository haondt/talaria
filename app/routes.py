from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
import logging
from .state import state
import asyncio
from .config import config
from . import gitlab
from . import jinja_filters
import os
import html

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
                    level, before_level, after_level = html.escape(level), html.escape(before_level), html.escape(after_level)
                    text = f"""
                        <div id='scan-output' hx-swap-oob='beforeend'>
                            <div><span>{before_level}</span><span class="{color_class}">{level}</span><span>{after_level}</span></div>
                        </div>
                    """
                else:
                    msg = html.escape(msg)
                    text = f"""
                        <div id='scan-output' hx-swap-oob='beforeend'>
                            <div>{msg}</div>
                        </div>
                    """
                asyncio.create_task(manager.broadcast(text))
                return

        # No log level found, use default format
        text = f"""
            <div id='scan-output' hx-swap-oob='beforeend'>
                <div>{msg}</div>
            </div>
        """
        asyncio.create_task(manager.broadcast(text))
    state.broadcaster.register(broadcaster_listener)

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        # Get pagination parameters
        page = int(request.query_params.get("page", 1))
        per_page = int(request.query_params.get("per_page", config.default_update_history_page_size))
        
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
                _ = await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)


    @app.get("/hc")
    async def health_check():
        return "OK"

    @app.post("/run-scan")
    async def force_start_scan(request: Request):
        await state.scanner_message_queue.put("scan_now")
        return templates.TemplateResponse("next_scan.html", {"request": request, "state": state, "swap": True})

    @app.get("/static/logo.svg")
    async def serve_logo():
        logo_path = os.path.join(os.path.dirname(__file__), "static", "logo.svg")
        if not os.path.exists(logo_path):
            return Response(status_code=404)
        return FileResponse(path=logo_path)

