import os

def parse_bool_env_var(var_name, default=False):
    value = os.getenv(var_name)
    if value is not None:
        value_str = str(value).lower()
        return value_str in ('true', '1') or \
               (value_str.isdigit() and int(value_str) != 0)
    return default

class Config:
    def __init__(self):
        self.is_development = os.getenv('TL_ENVIRONMENT', 'prod') in ['dev', 'development']
        self.log_template = os.getenv('TL_LOG_TEMPLATE', '%(name)s: %(message)s' if self.is_development else '[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s')
        self.log_level = os.getenv('TL_LOG_LEVEL', 'INFO')
        self.server_port = int(os.getenv('TL_SERVER_PORT', 5001))
        self.db_path = os.getenv('TL_DB_PATH', 'talaria.db')
        self.webhook_api_key = os.getenv('TL_WEBHOOK_API_KEY', '57d88647-208e-4ee1-88fc-365836f95ee4')

config = Config()
