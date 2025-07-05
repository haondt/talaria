from .config import config
import uvicorn

if __name__ == "__main__":
    kwargs = {
        'factory': True,
        'host': '0.0.0.0',
        'port': config.server_port,
        'log_config': None
    }
    if (config.is_development):
        kwargs['reload'] = True
        kwargs['reload_excludes'] = 'data'
    uvicorn.run("app:create_app", **kwargs)
