import json
import asyncio
import hashlib
import threading
import random
from dataclasses import dataclass, asdict
from .config import config
from enum import Enum
import sqlite3
import queue
import time

class PipelineStatus(str, Enum):
    UNKNOWN = "unknown"
    SUCCESS = "success"
    FAILURE = "failure"

@dataclass
class CommitInfo:
    commit_hash: str
    commit_short_hash: str
    commit_url: str | None
    pipeline_url: str | None
    pipeline_status: PipelineStatus
    commit_timestamp: float
    pipeline_timestamp: float | None
    pipeline_duration: float | None

class Broadcaster:
    def __init__(self):
        self._listeners = set()
        self._lock = threading.Lock()

    def push(self, msg: str):
        with self._lock:
            listeners = list(self._listeners)
        if not listeners:
            return
        for cb in listeners:
            try:
                cb(msg)
            except Exception:
                pass

    def register(self, cb):
        with self._lock:
            self._listeners.add(cb)

    def unregister(self, cb):
        with self._lock:
            self._listeners.discard(cb)

class State:
    def __init__(self):
        self.db_path = config.db_path
        self._lock = threading.Lock()
        self._init_db()
        self.broadcaster = Broadcaster()
        self.scanner_message_queue = asyncio.Queue()

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
                    data TEXT,
                    commit_timestamp REAL
                )
            ''')
            c.execute('''
                CREATE TABLE IF NOT EXISTS skopeo_cache (
                    command_hash TEXT PRIMARY KEY,
                    result TEXT,
                    timestamp REAL
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

        def __contains__(self, commit_hash: str) -> bool:
            return self.__getitem__(commit_hash) is not None

        def __getitem__(self, commit_hash: str) -> CommitInfo | None:
            with self.state._lock, self.state._get_conn() as conn:
                c = conn.cursor()
                c.execute('SELECT data, commit_timestamp FROM commits WHERE commit_hash = ?', (commit_hash,))
                row = c.fetchone()
                if row:
                    data = json.loads(row[0])
                    # Convert pipeline_status back to enum
                    data['pipeline_status'] = PipelineStatus(data['pipeline_status'])
                    # Use the dedicated timestamp column if available, otherwise fall back to JSON data
                    if row[1] is not None:
                        data['commit_timestamp'] = row[1]
                    return CommitInfo(**data)
                return None

        def __setitem__(self, commit_hash: str, value: CommitInfo):
            with self.state._lock, self.state._get_conn() as conn:
                c = conn.cursor()
                data = asdict(value)
                # Store pipeline_status as string
                data['pipeline_status'] = data['pipeline_status'].value
                c.execute('REPLACE INTO commits (commit_hash, data, commit_timestamp) VALUES (?, ?, ?)', 
                         (commit_hash, json.dumps(data), value.commit_timestamp))
                conn.commit()

        def __delitem__(self, commit_hash: str):
            with self.state._lock, self.state._get_conn() as conn:
                c = conn.cursor()
                c.execute('DELETE FROM commits WHERE commit_hash = ?', (commit_hash,))
                conn.commit()

        def get(self, commit_hash: str, default=None) -> CommitInfo | None:
            result = self.__getitem__(commit_hash)
            return result if result is not None else default

        def items(self) -> list[tuple[str, CommitInfo]]:
            """Get all commits as (commit_hash, CommitInfo) pairs"""
            with self.state._lock, self.state._get_conn() as conn:
                c = conn.cursor()
                c.execute('SELECT commit_hash, data, commit_timestamp FROM commits ORDER BY commit_timestamp DESC, commit_hash')
                rows = c.fetchall()
                items = []
                for commit_hash, data, commit_timestamp in rows:
                    data_dict = json.loads(data)
                    # Convert pipeline_status back to enum
                    data_dict['pipeline_status'] = PipelineStatus(data_dict['pipeline_status'])
                    # Use the dedicated timestamp column if available, otherwise fall back to JSON data
                    if commit_timestamp is not None:
                        data_dict['commit_timestamp'] = commit_timestamp
                    commit_info = CommitInfo(**data_dict)
                    items.append((commit_hash, commit_info))
                return items

    class SkopeoCacheDict:
        def __init__(self, state):
            self.state = state

        def _hash_command(self, command: str, args: list[str]) -> str:
            """Create a hash of the command and arguments for caching"""
            command = command.replace(':', '::')
            args = [a.replace(':', '::') for a in args]
            command_str = f"{command}:{':'.join(args)}"
            return hashlib.sha256(command_str.encode()).hexdigest()

        def get(self, command: str, args: list[str]) -> str | None:
            """Get cached result for a skopeo command, returns None if not found or expired"""
            command_hash = self._hash_command(command, args)
            current_time = time.time()
            
            with self.state._lock, self.state._get_conn() as conn:
                c = conn.cursor()
                c.execute('SELECT result, timestamp FROM skopeo_cache WHERE command_hash = ?', (command_hash,))
                row = c.fetchone()
                
                if row:
                    result, expiration_time = row
                    max_expiration = current_time + config.skopeo_cache_duration
                    if current_time < expiration_time and expiration_time <= max_expiration:
                        return result
                    else:
                        c.execute('DELETE FROM skopeo_cache WHERE command_hash = ?', (command_hash,))
                        conn.commit()
                        return None
                return None

        def set(self, command: str, args: list[str], result: str):
            """Cache the result of a skopeo command"""
            command_hash = self._hash_command(command, args)
            current_time = time.time()
            
            variance_factor = 1.0 + random.uniform(-config.skopeo_cache_variance, config.skopeo_cache_variance)
            cache_duration = config.skopeo_cache_duration * variance_factor

            with self.state._lock, self.state._get_conn() as conn:
                c = conn.cursor()
                expiration_time = current_time + cache_duration
                c.execute('REPLACE INTO skopeo_cache (command_hash, result, timestamp) VALUES (?, ?, ?)', 
                         (command_hash, result, expiration_time))
                conn.commit()

        def cleanup_expired(self):
            """Remove all expired cache entries and entries beyond current max duration"""
            current_time = time.time()
            max_expiration = current_time + config.skopeo_cache_duration
            
            with self.state._lock, self.state._get_conn() as conn:
                c = conn.cursor()
                c.execute('DELETE FROM skopeo_cache WHERE timestamp < ? OR timestamp > ?', 
                         (current_time, max_expiration))
                conn.commit()

    @property
    def commit(self) -> 'State.CommitDict':
        return self.CommitDict(self)

    @property
    def skopeo_cache(self) -> 'State.SkopeoCacheDict':
        return self.SkopeoCacheDict(self)

state = State()
