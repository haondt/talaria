import subprocess
import shutil
import asyncio
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

    async def _run_git(self, *args, cwd=None) -> str:
        """Run a git command asynchronously and return the result"""
        if cwd is None:
            cwd = self.repo_path
        cmd = ['git'] + list(args)

        log_message = f"Running git command: {' '.join(cmd)}"
        if self.auth_token in log_message:
            log_message = log_message.replace(self.auth_token, '<git-auth-token>')
        _logger.info(log_message)
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            log_message = f"Git command failed: {stderr}"
            if self.auth_token in log_message:
                log_message = log_message.replace(self.auth_token, '<git-auth-token>')
            _logger.error(log_message)
            raise subprocess.CalledProcessError(process.returncode or 1, cmd, stdout, stderr)
        
        return stdout.strip().decode('utf-8')

    def delete(self):
        """Delete the repository directory and all its contents"""
        if self.repo_path.exists():
            shutil.rmtree(self.repo_path)
            _logger.info(f"Deleted repository at {self.repo_path}")

    async def clone(self):
        if self.repo_path.exists():
            _logger.warning(f"Repository already exists at {self.repo_path}")
            return
        
        # Create parent directory if it doesn't exist
        self.repo_path.mkdir(parents=True, exist_ok=True)
        
        # Use authenticated URL if token is present
        clone_url = self.repo_url
        if self.auth_token:
            clone_url = self.repo_url.replace('https://', f'https://oauth2:{self.auth_token}@')
        
        # Clone with depth=1 for shallow clone
        await self._run_git('clone', '--depth', '1', '--branch', self.branch, clone_url, str(self.repo_path))
        _logger.info(f"Cloned repository to {self.repo_path}")

    async def add(self, files=None):
        """Stage changes. If files is None, stage all changes"""
        if files is None:
            await self._run_git('add', '.')
        else:
            for file in files:
                await self._run_git('add', file)
        _logger.info(f"Staged changes: {files if files else 'all'}")

    async def commit(self, title: str, description: str | None = None):
        """Commit staged changes"""
        if description is None:
            await self._run_git('commit', '-m', title)
            _logger.info(f"Committed with message: {title}")
        else:
            await self._run_git('commit', '-m', title, '-m', description)
            _logger.info(f"Committed with message: {title}\n{description}")

    async def push(self):
        """Push changes to remote"""
        await self._run_git('push', 'origin', self.branch)
        _logger.info(f"Pushed changes to {self.branch}")

    async def get_current_commit(self):
        """Get the current commit hash"""
        return await self._run_git('rev-parse', 'HEAD')

    async def get_short_commit(self):
        """Get the short commit hash"""
        return await self._run_git('rev-parse', '--short', 'HEAD')

    async def setup_auth(self):
        """Setup authentication for the repository"""
        if not self.auth_token:
            _logger.warning("No auth token configured")
            return
        
        auth_url = self.repo_url.replace('https://', f'https://oauth2:{self.auth_token}@')
        await self._run_git('remote', 'set-url', 'origin', auth_url)
        _logger.info("Configured authentication for repository")

    async def setup_environment(self):
        await self._run_git('config', 'user.email', config.git_user_email)
        await self._run_git('config', 'user.name', config.git_user_name)
