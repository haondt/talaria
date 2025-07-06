import os
import re
from datetime import timedelta

def parse_bool_env_var(var_name, default=False):
    value = os.getenv(var_name)
    if value is not None:
        value_str = str(value).lower()
        return value_str in ('true', '1') or \
               (value_str.isdigit() and int(value_str) != 0)
    return default

_timespan_pattern = re.compile(r"^\s*(?:(?P<d>[0-9]+)d)?\s*(?:(?P<h>[0-9]+)h)?\s*(?:(?P<m>[0-9]+)m)?\s*(?:(?P<s>[0-9]+)s)?\s*$")
def parse_timespan(s):
    time_match = _timespan_pattern.match(s)
    if time_match is None:
        raise ValueError(f'unable to parse timedelta string {s}')
    gd = time_match.groupdict()
    return timedelta(
        days=int(gd['d'] or 0),
        hours=int(gd['h'] or 0),
        minutes=int(gd['m'] or 0),
        seconds=int(gd['s'] or 0)
    )


class Config:
    def __init__(self):
        self.is_development = os.getenv('TL_ENVIRONMENT', 'prod') in ['dev', 'development']
        self.log_template = os.getenv('TL_LOG_TEMPLATE', '%(name)s: %(message)s' if self.is_development else '[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s')
        self.log_level = os.getenv('TL_LOG_LEVEL', 'INFO')
        self.server_port = int(os.getenv('TL_SERVER_PORT', 5001))
        self.db_path = os.getenv('TL_DB_PATH', '/data/talaria.db')
        self.db_path = os.path.abspath(self.db_path)
        self.webhook_api_key = os.getenv('TL_WEBHOOK_API_KEY', '57d88647-208e-4ee1-88fc-365836f95ee4')

        update_delay = os.getenv('TL_UPDATE_DELAY', '1d')
        self.update_delay = parse_timespan(update_delay)

        self.broadcast_loggers = [
            'app.talaria_git',
            'app.scanner',
            'app.docker_compose_file'
        ]

        self.git_repo_path = os.getenv('TL_GIT_REPO_PATH', '/data/repository')
        self.git_repo_path = os.path.abspath(self.git_repo_path)
        self.git_repo_url = os.environ['TL_GIT_REPO_URL']
        self.git_branch = os.getenv('TL_GIT_BRANCH', 'main')
        self.git_auth_token = os.environ['TL_GIT_AUTH_TOKEN']

        self.docker_compose_file_pattern = os.getenv('TL_DOCKER_COMPOSE_FILE_PATTERN', 'docker-compose*.y*ml')

        self.valid_releases = os.getenv('TL_VALID_RELEASES', 'latest|stable|mainline|develop')
        self.enable_talos_short_form_compatibility = parse_bool_env_var('TL_TALOS_SHORT_FORM_COMPAT', False)
        self.maximum_concurrent_pushes = int(os.getenv('TL_MAX_CONCURRENT_PUSHES', 5))

        # Skopeo cache settings
        skopeo_cache_duration = os.getenv('TL_SKOPEO_CACHE_DURATION', '12h')
        self.skopeo_cache_duration = parse_timespan(skopeo_cache_duration).total_seconds()
        
        skopeo_cache_variance = os.getenv('TL_SKOPEO_CACHE_VARIANCE', '0.1')
        self.skopeo_cache_variance = float(skopeo_cache_variance)
        
        # Docker.io authentication for skopeo
        self.docker_username = os.getenv('TL_DOCKER_USERNAME')
        self.docker_password = os.getenv('TL_DOCKER_PASSWORD')
        self.docker_auth_file = os.getenv('TL_DOCKER_AUTH_FILE', '/data/skopeo-auth.json')
        self.docker_auth_file = os.path.abspath(self.docker_auth_file)

    def should_broadcast_logger(self, logger_name: str) -> bool:
        return any(logger_name.startswith(broadcast_logger) for broadcast_logger in self.broadcast_loggers)



config = Config()
