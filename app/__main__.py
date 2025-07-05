from .config import config
import uvicorn

# Mount static files
# app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates



if __name__ == "__main__":
    uvicorn.run("app:create_app",
                factory=True,
                host="0.0.0.0",
                port=config.server_port,
                reload=config.is_development,
                log_config=None) 
