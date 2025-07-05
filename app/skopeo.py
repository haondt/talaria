import subprocess
import json
import logging
import asyncio
from .models import SkopeoInspectResponse

_logger = logging.getLogger(__name__)


async def _run_skopeo_async(*args) -> str:
    """Run a skopeo command asynchronously and return the result"""
    cmd = ['skopeo'] + list(args)
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
    
    return stdout.strip().decode('utf-8')

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

