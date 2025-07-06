from pathlib import Path
from .models import DockerComposeTarget, BumpSize
from .config import config
import logging
import re

_logger = logging.getLogger(__name__)

def get_docker_compose_files():
    repo_path = Path(config.git_repo_path)
    
    docker_compose_files = []
    for file_path in repo_path.rglob(config.docker_compose_file_pattern):
        if '.git' in file_path.parts:
            continue
        
        docker_compose_files.append(str(file_path.absolute()))
        _logger.debug(f"Found docker-compose file: {file_path}")
    
    _logger.info(f"Found {len(docker_compose_files)} docker-compose files")
    return docker_compose_files

def _remove_quotes(item: str):
    if (item.startswith("'") and item.endswith("'")) or \
        (item.startswith('"') and item.endswith('"')):
        return item[1:-1]
    return item

def _get_indentation(line: str) -> int:
    """Get the indentation level of a line"""
    return len(line) - len(line.lstrip())

def _find_service_key(lines: list[str], current_line_num: int) -> str:
    """Find the service key by looking up for the first line with less indentation"""
    current_indent = _get_indentation(lines[current_line_num])
    
    # Search upwards for the service key
    for i in range(current_line_num - 1, -1, -1):
        line = lines[i]
        indent = _get_indentation(line)
        if indent < current_indent and ':' in line and not line.strip().startswith('#'):
            # Found the service key
            return line.split(':')[0].strip()
    
    raise ValueError(f"Unable to find service key") 


def _parse_bump_value(value: str) -> BumpSize:
    """Parse bump value from string"""
    value = _remove_quotes(value)
    value_lower = value.lower().strip()
    if value_lower == "major":
        return BumpSize.MAJOR
    elif value_lower == "minor":
        return BumpSize.MINOR
    elif value_lower == "patch":
        return BumpSize.PATCH
    elif value_lower == "digest":
        return BumpSize.DIGEST
    else:
        raise ValueError(f"Invalid bump value: {value}")

def _parse_skip_value(value: str) -> bool:
    """Parse skip value from string"""
    value = _remove_quotes(value)
    value_lower = value.lower().strip()
    if value_lower in ["true", "yes", "1"]:
        return True
    elif value_lower in ["false", "no", "0"]:
        return False
    else:
        # Try to parse as number
        try:
            num = int(value)
            return num > 0
        except ValueError:
            return False

def _find_x_config(lines: list[str], current_line_num: int, current_indent: int) -> tuple[BumpSize, bool]:
    # Search downwards for x-talos or x-tl at the same indentation level
    for i in range(current_line_num + 1, len(lines)):
        line = lines[i]
        indent = _get_indentation(line)
        
        # If we've gone to a higher level, stop searching
        if indent < current_indent:
            break
            
        if indent == current_indent:
            line_stripped = line.strip()
            
            if line_stripped.startswith('x-talaria:'):
                # Parse x-talos configuration
                return _parse_x_talaria_config(lines, i, current_indent)
            elif line_stripped.startswith('x-tl:'):
                # Parse x-tl configuration
                return _parse_x_tl_config(line_stripped)
            elif config.enable_talos_compatibility and line_stripped.startswith('x-talos:'):
                # Parse x-talos configuration
                return _parse_x_talaria_config(lines, i, current_indent)
    
    raise ValueError(f"Unable to find talaria configuration")

def _parse_x_talaria_config(lines: list[str], start_line: int, base_indent: int) -> tuple[BumpSize, bool]:
    """Parse x-talos configuration block"""
    bump = BumpSize.DIGEST
    skip = False
    
    for i in range(start_line + 1, len(lines)):
        line = lines[i]
        indent = _get_indentation(line)
        
        if indent <= base_indent:
            break
            
        if indent > base_indent:
            line_stripped = line.strip()
            if line_stripped.startswith('bump:'):
                value = line.split(':', 1)[1].strip()
                bump = _parse_bump_value(value)
            elif line_stripped.startswith('skip:'):
                value = line.split(':', 1)[1].strip()
                skip = _parse_skip_value(value)
    
    return bump, skip

def _parse_x_tl_config(line: str) -> tuple[BumpSize, bool]:
    """Parse x-tl configuration (single line format)"""
    value = line.split(':', 1)[1].strip()
    value = _remove_quotes(value)
    if config.enable_talos_compatibility:
        if len(value) > 0:
            value = value[0]
    if value == 'x':
        return BumpSize.DIGEST, True
    elif value == '+':
        return BumpSize.MAJOR, False
    elif value == '^':
        return BumpSize.MINOR, False
    elif value == '~':
        return BumpSize.PATCH, False
    elif value == '@':
        return BumpSize.DIGEST, False
    else:
        raise ValueError(f"Invalid x-tl value: {value}")

def get_images(file_path: str) -> tuple[list[DockerComposeTarget], list[str]]:
    targets: list[DockerComposeTarget] = []
    errors: list[str] = []
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
        
    for line_num, line in enumerate(lines):
        line = line.strip()
        if line.startswith('image:'):
            # Extract the image name after 'image:'
            image = line[6:].strip()
            # Remove quotes if present
            if image.startswith('"') and image.endswith('"'):
                image = image[1:-1]
            elif image.startswith("'") and image.endswith("'"):
                image = image[1:-1]
            
            if not image:  # Only add if image is not empty
                continue

            try:
                # Find the service key
                service_key = _find_service_key(lines, line_num)
                
                # Find x-talos or x-tl configuration
                current_indent = _get_indentation(lines[line_num])
                bump, skip = _find_x_config(lines, line_num, current_indent)
                
                target = DockerComposeTarget(
                    file_path=file_path,
                    service_key=service_key,
                    line=line_num,
                    current_image_string=image,
                    bump=bump,
                    skip=skip
                )
                
                targets.append(target)
                _logger.debug(f"Found image '{image}' at line {line_num + 1} in service '{service_key}'")
                
            except Exception as e:
                error_msg = f"Failed to parse image at line {line_num + 1}: {e}"
                errors.append(error_msg)

    
    return targets, errors

def apply_update(target: DockerComposeTarget, new_image: str):
    """Apply the update to the docker-compose file by replacing the image line"""
    with open(target.file_path, 'r') as f:
        lines = f.readlines()
    
    line_index = target.line
    if line_index >= len(lines):
        raise ValueError(f"Line {target.line} is out of bounds for file {target.file_path}")
    
    original_line = lines[line_index]
    indent = _get_indentation(original_line)
    indent_str = ' ' * indent
    
    new_line = f"{indent_str}image: {new_image}\n"
    lines[line_index] = new_line
    
    with open(target.file_path, 'w') as f:
        f.writelines(lines)
