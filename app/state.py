import json
import threading
from dataclasses import dataclass, asdict
from .config import config
from enum import Enum
import sqlite3

class PipelineStatus(str, Enum):
    UNKNOWN = "unknown"
    SUCCESS = "success"
    FAILURE = "failure"

@dataclass
class CommitInfo:
    commit_hash: str
    commit_short_hash: str
    commit_url: str
    pipeline_url: str | None
    pipeline_status: PipelineStatus
    commit_timestamp: float
    pipeline_timestamp: float | None
    pipeline_duration: float | None

class State:
    def __init__(self):
        self.db_path = config.db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path, check_same_thread=(not config.is_development))

    def _init_db(self):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS commits (
                    commit_hash TEXT PRIMARY KEY,
                    data TEXT
                )
            ''')
            conn.commit()

    @property
    def next_run(self) -> float | None:
        with self._lock, self._get_conn() as conn:
            c = conn.cursor()
            c.execute('SELECT value FROM state WHERE key = ?', ('next_run',))
            row = c.fetchone()
            if row:
                return float(row[0]) if row[0] is not None else None
            return None

    @next_run.setter
    def next_run(self, value: float | None):
        with self._lock, self._get_conn() as conn:
            c = conn.cursor()
            if value is None:
                c.execute('DELETE FROM state WHERE key = ?', ('next_run',))
            else:
                c.execute('REPLACE INTO state (key, value) VALUES (?, ?)', ('next_run', str(value)))
            conn.commit()

    class CommitDict:
        def __init__(self, state):
            self.state = state

        def __getitem__(self, commit_hash: str) -> CommitInfo | None:
            with self.state._lock, self.state._get_conn() as conn:
                c = conn.cursor()
                c.execute('SELECT data FROM commits WHERE commit_hash = ?', (commit_hash,))
                row = c.fetchone()
                if row:
                    data = json.loads(row[0])
                    # Convert pipeline_status back to enum
                    data['pipeline_status'] = PipelineStatus(data['pipeline_status'])
                    return CommitInfo(**data)
                return None

        def __setitem__(self, commit_hash: str, value: CommitInfo):
            with self.state._lock, self.state._get_conn() as conn:
                c = conn.cursor()
                data = asdict(value)
                # Store pipeline_status as string
                data['pipeline_status'] = data['pipeline_status'].value
                c.execute('REPLACE INTO commits (commit_hash, data) VALUES (?, ?)', (commit_hash, json.dumps(data)))
                conn.commit()

        def __delitem__(self, commit_hash: str):
            with self.state._lock, self.state._get_conn() as conn:
                c = conn.cursor()
                c.execute('DELETE FROM commits WHERE commit_hash = ?', (commit_hash,))
                conn.commit()

        def get(self, commit_hash: str, default=None) -> CommitInfo | None:
            result = self.__getitem__(commit_hash)
            return result if result is not None else default

    @property
    def commit(self) -> 'State.CommitDict':
        return self.CommitDict(self)

state = State()
