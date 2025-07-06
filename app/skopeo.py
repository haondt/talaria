import subprocess
import json
import logging
import asyncio
import os
import base64
from .models import SkopeoInspectResponse
from .state import state
from .config import config

_logger = logging.getLogger(__name__)


def _setup_docker_auth():
    """Setup Docker authentication for skopeo if credentials are provided"""
    if not config.docker_username or not config.docker_password:
        return
    
    try:
        # Create auth.json file for skopeo
        auth_data = {
            "auths": {
                "docker.io": {
                    "auth": base64.b64encode(f'{config.docker_username}:{config.docker_password}'.encode()).decode('utf-8')
                }
            }
        }
        
        # Ensure directory exists
        auth_dir = os.path.dirname(config.docker_auth_file)
        if auth_dir:
            os.makedirs(auth_dir, exist_ok=True)
        
        # Write auth file
        with open(config.docker_auth_file, 'w') as f:
            json.dump(auth_data, f)
        
        # Set permissions to 600 (user read/write only)
        os.chmod(config.docker_auth_file, 0o600)
        
        _logger.info("Docker authentication configured for skopeo")
        
    except Exception as e:
        _logger.error(f"Failed to setup Docker authentication: {e}")


_setup_docker_auth()


async def _run_skopeo_async(*args) -> str:
    """Run a skopeo command asynchronously and return the result"""
    # Check cache first
    cached_result = state.skopeo_cache.get('skopeo', list(args))
    if cached_result is not None:
        _logger.debug(f"Using cached result for skopeo command: {' '.join(['skopeo'] + list(args))}")
        return cached_result
    
    # Run the command if not cached
    cmd = ['skopeo'] + list(args)
    
    # Add auth file if Docker credentials are configured
    if config.docker_username and config.docker_password and os.path.exists(config.docker_auth_file):
        cmd.extend(['--authfile', config.docker_auth_file])
    
    _logger.debug(f"Running skopeo command async: {' '.join(cmd)}")
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        _logger.error(f"Skopeo command failed: {stderr}")
        raise subprocess.CalledProcessError(process.returncode or 1, cmd, stdout, stderr)
    
    result = stdout.strip().decode('utf-8')
    
    # Cache the result
    state.skopeo_cache.set('skopeo', list(args), result)
    
    return result

async def inspect(image: str) -> SkopeoInspectResponse:
    """Inspect an image and return detailed information"""
    try:
        output = await _run_skopeo_async('inspect', f'docker://{image}')
        data = json.loads(output)
        
        inspect_response = SkopeoInspectResponse(
            name=data.get('Name', ''),
            digest=data.get('Digest', ''),
            created=data.get('Created', ''),
            architecture=data.get('Architecture', ''),
            os=data.get('Os', ''),
            layers=data.get('Layers', []),
            labels=data.get('Labels', {}),
            env=data.get('Env', []),
            entrypoint=data.get('Entrypoint', []),
            cmd=data.get('Cmd', []),
            working_dir=data.get('WorkingDir', ''),
            user=data.get('User', '')
        )
        
        _logger.debug(f"Inspected image: {image}")
        return inspect_response
        
    except json.JSONDecodeError as e:
        _logger.error(f"Failed to parse skopeo inspect output for {image}: {e}")
        raise
    except Exception as e:
        _logger.error(f"Failed to inspect image {image}: {e}")
        raise

async def list_tags(image: str) -> list[str]:
    """List all available tags for an image asynchronously"""
    try:
        output = await _run_skopeo_async('list-tags', f'docker://{image}')
        data = json.loads(output)
        
        tags = data.get('Tags', [])
        _logger.debug(f"Found {len(tags)} tags for {image}")
        return tags
        
    except json.JSONDecodeError as e:
        _logger.error(f"Failed to parse skopeo list-tags output for {image}: {e}")
        raise
    except Exception as e:
        _logger.error(f"Failed to list tags for {image}: {e}")
        raise

