import subprocess
import os
import shutil
from pathlib import Path
from .config import config
import logging

_logger = logging.getLogger(__name__)

class TalariaGit:
    def __init__(self):
        self.repo_path = Path(config.git_repo_path)
        self.repo_url = config.git_repo_url
        self.branch = config.git_branch
        self.auth_token = config.git_auth_token

    def _run_git(self, *args, cwd=None) -> str:
        """Run a git command and return the result"""
        if cwd is None:
            cwd = self.repo_path
        cmd = ['git'] + list(args)
        _logger.info(f"Running git command: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            _logger.error(f"Git command failed: {result.stderr}")
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
        return result.stdout.strip()


    def delete(self):
        """Delete the repository directory and all its contents"""
        if self.repo_path.exists():
            shutil.rmtree(self.repo_path)
            _logger.info(f"Deleted repository at {self.repo_path}")

    def clone(self):
        if self.repo_path.exists():
            _logger.warning(f"Repository already exists at {self.repo_path}")
            return
        
        # Create parent directory if it doesn't exist
        self.repo_path.mkdir(parents=True, exist_ok=True)
        
        # Clone with depth=1 for shallow clone
        self._run_git('clone', '--depth', '1', '--branch', self.branch, self.repo_url, str(self.repo_path))
        _logger.info(f"Cloned repository to {self.repo_path}")

    def add(self, files=None):
        """Stage changes. If files is None, stage all changes"""
        if files is None:
            self._run_git('add', '.')
        else:
            for file in files:
                self._run_git('add', file)
        _logger.info(f"Staged changes: {files if files else 'all'}")

    def commit(self, title: str, description: str | None = None):
        """Commit staged changes"""
        if description is None:
            self._run_git('commit', '-m', title)
            _logger.info(f"Committed with message: {title}")
        else:
            self._run_git('commit', '-m', title, '-m', description)
            _logger.info(f"Committed with message: {title}\n{description}")

    def push(self):
        """Push changes to remote"""
        self._run_git('push', 'origin', self.branch)
        _logger.info(f"Pushed changes to {self.branch}")

    def get_current_commit(self):
        """Get the current commit hash"""
        return self._run_git('rev-parse', 'HEAD')

    def get_short_commit(self):
        """Get the short commit hash"""
        return self._run_git('rev-parse', '--short', 'HEAD')

    def setup_auth(self):
        """Setup authentication for the repository"""
        if not self.auth_token:
            _logger.warning("No auth token configured")
            return
        
        auth_url = self.repo_url.replace('https://', f'https://oauth2:{self.auth_token}@')
        self._run_git('remote', 'set-url', 'origin', auth_url)
        _logger.info("Configured authentication for repository")
