from fastapi import FastAPI
from . import routes
from .config import  config
import logging, datetime

logging.Formatter.formatTime = (lambda self, record, datefmt=None: datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).astimezone().isoformat(sep="T",timespec="milliseconds"))
logging.basicConfig(format=config.log_template, level=logging.getLevelName(config.log_level))

def create_app():
    app = FastAPI(title="FastAPI + HTMX + Bulma + WebSockets", version="1.0.0")
    routes.add_routes(app)
    return app
