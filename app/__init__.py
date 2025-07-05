from fastapi import FastAPI
from . import routes
from .config import  config
import logging, datetime

# Custom logging filter that broadcasts certain log messages
class BroadcastFilter(logging.Filter):
    def __init__(self, state):
        super().__init__()
        self.state = state

    def filter(self, record):
        if config.should_broadcast_logger(record.name):
            message = f"[{record.name}] {record.getMessage()}"
            self.state.broadcaster.push(message)
        return False


logging.Formatter.formatTime = (lambda self, record, datefmt=None: datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).astimezone().isoformat(sep="T",timespec="milliseconds"))

def create_app():
    app = FastAPI(title="FastAPI + HTMX + Bulma + WebSockets", version="1.0.0")
    logging.basicConfig(format=config.log_template, level=logging.getLevelName(config.log_level))

    from .state import state
    broadcast_handler = logging.StreamHandler()
    broadcast_handler.addFilter(BroadcastFilter(state))
    logging.getLogger().addHandler(broadcast_handler)

    routes.add_routes(app)

    from . import scanner
    scanner.start()

    return app
