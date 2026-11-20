"""
pasfmt code formatting tool

Provides Delphi code formatting using the pasfmt tool
Includes download, installation, and configuration features
"""

import os
import sys
import subprocess
import tempfile
import zipfile
import shutil
import requests
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from mcp.types import CallToolResult, TextContent

try:
    from ..constants import (
        CHUNK_SIZE_DOWNLOAD,
        REG_KEY_EMBARCADERO_BDS,
        TIMEOUT_NETWORK_REQUEST,
        TIMEOUT_PASFMT,
        TIMEOUT_PASFMT_BUILD,
        TIMEOUT_PASFMT_GIT_CLONE,
    )
    from ..utils.logger import get_logger
    from ..utils.file_backup import create_backup as _create_backup, detect_encoding as _detect_encoding, list_backups as _list_backups
except ImportError:
    try:
        from src.constants import (
            CHUNK_SIZE_DOWNLOAD,
            REG_KEY_EMBARCADERO_BDS,
            TIMEOUT_NETWORK_REQUEST,
            TIMEOUT_PASFMT,
            TIMEOUT_PASFMT_BUILD,
            TIMEOUT_PASFMT_GIT_CLONE,
        )
        from src.utils.logger import get_logger
        from src.utils.file_backup import create_backup as _create_backup, detect_encoding as _detect_encoding, list_backups as _list_backups
    except ImportError:
        import logging
        CHUNK_SIZE_DOWNLOAD = 8192
        REG_KEY_EMBARCADERO_BDS = r"SOFTWARE\Embarcadero\BDS"
        TIMEOUT_NETWORK_REQUEST = 30
        TIMEOUT_PASFMT = 30
        TIMEOUT_PASFMT_BUILD = 600
        TIMEOUT_PASFMT_GIT_CLONE = 300

        def get_logger(name: str) -> logging.Logger:
            logger = logging.getLogger(name)
            if not logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                logger.addHandler(handler)
                logger.setLevel(logging.INFO)
            return logger

logger = get_logger(__name__)

# pasfmt executable path
_PASFMT_PATH: Optional[str] = None

# uses clause style: "compact"=merge into one line, "pasfmt_default"=keep pasfmt one per line
_USES_STYLE: str = "compact"

# Download source configuration
PASFMT_DOWNLOAD_SOURCES = [
    {
        "name": "GitHub",
        "url": "https://github.com/integrated-application-development/pasfmt/releases/download/v0.7.0/pasfmt-0.7.0-x86_64-pc-windows-msvc.zip",
        "mirror": "https://ghproxy.com/https://github.com/integrated-application-development/pasfmt/releases/download/v0.7.0/pasfmt-0.7.0-x86_64-pc-windows-msvc.zip"
    },
    {
        "name": "GitHub Mirror 1",
        "url": "https://mirror.ghproxy.com/https://github.com/integrated-application-development/pasfmt/releases/download/v0.7.0/pasfmt-0.7.0-x86_64-pc-windows-msvc.zip"
    },
    {
        "name": "GitHub Mirror 2", 
        "url": "https://download.fastgit.org/integrated-application-development/pasfmt/releases/download/v0.7.0/pasfmt-0.7.0-x86_64-pc-windows-msvc.zip"
    }
]

# pasfmt-rad download source configuration
PASFMT_RAD_DOWNLOAD_SOURCES = [
    {
        "name": "GitHub",
        "base_url": "https://github.com/integrated-application-development/pasfmt-rad/releases/download/v0.2.1/",
        "mirror": "https://ghproxy.com/https://github.com/integrated-application-development/pasfmt-rad/releases/download/v0.2.1/"
    },
    {
        "name": "GitHub Mirror 1",
        "base_url": "https://mirror.ghproxy.com/https://github.com/integrated-application-development/pasfmt-rad/releases/download/v0.2.1/"
    },
    {
        "name": "GitHub Mirror 2",
        "base_url": "https://download.fastgit.org/integrated-application-development/pasfmt-rad/releases/download/v0.2.1/"
    }
]

# Source build configuration
PASFMT_SOURCE_REPOSITORIES = [
    {
        "name": "GitHub",
        "url": "https://github.com/integrated-application-development/pasfmt.git",
        "mirror": "https://ghproxy.com/https://github.com/integrated-application-development/pasfmt.git"
    },
    {
        "name": "GitHub Mirror 1",
        "url": "https://mirror.ghproxy.com/https://github.com/integrated-application-development/pasfmt.git"
    },
    {
        "name": "GitHub Mirror 2",
        "url": "https://download.fastgit.org/integrated-application-development/pasfmt.git"
    }
]

PASFMT_RAD_SOURCE_REPOSITORIES = [
    {
        "name": "GitHub",
        "url": "https://github.com/integrated-application-development/pasfmt-rad.git",
        "mirror": "https://ghproxy.com/https://github.com/integrated-application-development/pasfmt-rad.git"
    },
    {
        "name": "GitHub Mirror 1",
        "url": "https://mirror.ghproxy.com/https://github.com/integrated-application-development/pasfmt-rad.git"
    },
    {
        "name": "GitHub Mirror 2",
        "url": "https://download.fastgit.org/integrated-application-development/pasfmt-rad.git"
    }
]

# Delphi version mapping
DELPHI_VERSIONS = {
    "11": {"name": "Alexandria", "bpl_32": "Pasfmt_11_Alexandria.bpl", "bpl_64": None},
    "12": {"name": "Athens", "bpl_32": "Pasfmt_12_Athens.bpl", "bpl_64": "Pasfmt_12_Athens_64.bpl"},
    "13": {"name": "Florence", "bpl_32": "Pasfmt_13_Florence.bpl", "bpl_64": "Pasfmt_13_Florence_64.bpl"}
}

_DELPHI_TO_BDS_REGISTRY_VERSION = {
    "11": "22.0",
    "12": "23.0",
    "13": "37.0",
}


def _project_root() -> Path:
    return Path(__file__).parent.parent.parent


def _pasfmt_default_paths() -> list[str]:
    return [str(_project_root() / "tools" / "pasfmt" / "cli" / "pasfmt.exe")]


def _bds_registry_version(delphi_version: str) -> str:
    return _DELPHI_TO_BDS_REGISTRY_VERSION.get(delphi_version, delphi_version)


def _pasfmt_rad_candidate_dirs(delphi_version: str) -> list[str]:
    project_rad_dir = str(_project_root() / "tools" / "pasfmt" / "rad")
    possible_dirs = [project_rad_dir]
    if sys.platform == "win32":
        try:
            from ..utils.delphi_env import get_delphi_root_dir
        except ImportError:
            from src.utils.delphi_env import get_delphi_root_dir

        root_dir = get_delphi_root_dir(_bds_registry_version(delphi_version))
        if root_dir:
            possible_dirs.append(str(Path(root_dir) / "bin"))
    return possible_dirs


def set_pasfmt_path(path: str):
    """Set pasfmt executable path"""
    global _PASFMT_PATH
    _PASFMT_PATH = path
    logger.info(f"Set pasfmt path: {path}")


def get_pasfmt_path() -> Optional[str]:
    """Get pasfmt executable path"""
    global _PASFMT_PATH
    
    if _PASFMT_PATH:
        return _PASFMT_PATH
    
    # Try to get from environment variable
    env_path = os.environ.get('PASFMT_PATH')
    if env_path and os.path.exists(env_path):
        _PASFMT_PATH = env_path
        return _PASFMT_PATH
    
    # Try to search from PATH environment variable
    path_in_path = shutil.which('pasfmt') or shutil.which('pasfmt.exe')
    if path_in_path:
        _PASFMT_PATH = path_in_path
        logger.info(f"Found pasfmt in PATH: {path_in_path}")
        return path_in_path
    
    # Try to get from default installation location
    default_paths = _pasfmt_default_paths()
    
    for path in default_paths:
        if os.path.exists(path):
            _PASFMT_PATH = path
            logger.info(f"Found pasfmt in default location: {path}")
            return path
    
    logger.warning("pasfmt executable not found")
    return None


def set_uses_style(style: str) -> None:
    """Set uses clause style: "compact"=merge into one line, "pasfmt_default"=keep pasfmt as-is"""
    global _USES_STYLE
    if style not in ("compact", "pasfmt_default"):
        logger.warning(f"Unknown uses_style: {style}, using default compact")
        _USES_STYLE = "compact"
    else:
        _USES_STYLE = style
        logger.info(f"Set uses style: {style}")


def get_uses_style() -> str:
    """Get current uses clause style setting"""
    return _USES_STYLE


def _compact_uses_clause(content: str) -> str:
    """
    Compress pasfmt-expanded multi-line uses clauses back into a single line.

    pasfmt default:
      uses
        System.SysUtils,
        System.Classes;

    After compression:
      uses System.SysUtils, System.Classes;
    """
    lines = content.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        trimmed = line.strip()

        # Detect "uses" on its own line (pasfmt style)
        if trimmed.lower() == 'uses' and not trimmed.endswith(';'):
            items = []
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                next_trimmed = next_line.strip()

                # Blank line or non-indented line = end of uses block
                if not next_trimmed or not (next_line.startswith(' ') or next_line.startswith('\t')):
                    break

                item = next_trimmed.rstrip(',').rstrip(';').strip()
                if item:
                    items.append(item)

                if next_trimmed.endswith(';'):
                    j += 1
                    break  # End with semicolon
                j += 1

            if items:
                indent = line[:len(line) - len(trimmed)]
                result.append(f"{indent}uses {', '.join(items)};")
                i = j
                continue

        result.append(line)
        i += 1

    return '\n'.join(result)


async def format_file(
    file_path: str,
    config_path: Optional[str] = None,
    backup: bool = True,
    in_place: bool = True,
    dry_run: bool = False,
    uses_style: Optional[str] = None
) -> Dict[str, Any]:
    """
    Format a Delphi source code file

    Args:
        file_path: Path to the Delphi file to format
        config_path: pasfmt configuration file path (optional)
        backup: Whether to create a backup file (under the __history directory)
        in_place: Whether to format in place (modify the original file)
        dry_run: Only check formatting, do not actually modify the file
        uses_style: uses clause style, None=use global setting, "compact"=merge into one line, "pasfmt_default"=keep pasfmt as-is

    Returns:
        Formatting result dictionary
    """
    logger.info(f"Received formatting request: {file_path}")
    
    # Check whether file exists
    if not os.path.exists(file_path):
        error_msg = f"File does not exist: {file_path}"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "FILE_NOT_FOUND",
            "error_message": error_msg,
            "formatted": False
        }
    
    # Get pasfmt path
    pasfmt_path = get_pasfmt_path()
    if not pasfmt_path:
        error_msg = (
            "pasfmt is not installed. Download URL: https://github.com/integrated-application-development/pasfmt/releases\n"
            "The AI Agent should download and install the latest version for the operating system"
        )
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "PASFMT_NOT_FOUND",
            "error_message": error_msg,
            "formatted": False
        }
    
    # Detect file encoding (using common function)
    encoding = _detect_encoding(file_path)
    
    # Create backup (using common function)
    backup_path = None
    if backup:
        backup_path = _create_backup(file_path)
    
    # Build pasfmt command
    cmd = [pasfmt_path]
    
    # Add config file argument
    if config_path and os.path.exists(config_path):
        cmd.extend(["--config-file", config_path])
    
    # Add mode argument
    if dry_run:
        cmd.extend(["--mode", "check"])
    elif in_place:
        cmd.extend(["--mode", "files"])
    else:
        cmd.extend(["--mode", "stdout"])
    
    # Add input file
    cmd.append(file_path)
    
    try:
        # Execute pasfmt
        logger.info(f"Executing command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=TIMEOUT_PASFMT,  # 30 second timeout
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        
        # Process output
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        
        if dry_run:
            # check mode: returncode != 0 means incorrect formatting, this is normal behavior
            if result.returncode != 0:
                # Format issues found - parse stderr to get file names
                all_output = stderr.strip()
                lines = all_output.split('\n')
                # Extract file name lines (lines containing "ERROR CHECK:" or "has incorrect formatting")
                issues = []
                for line in lines:
                    if line and ('incorrect formatting' in line or 'CHECK:' in line):
                        # Extract file name
                        if "has incorrect formatting" in line:
                            # Format: "ERROR CHECK: 'filepath' has incorrect formatting"
                            import re
                            match = re.search(r"'([^']+)'", line)
                            if match:
                                issues.append(match.group(1))
                        elif "CHECK:" in line:
                            issues.append(line)
                
                return {
                    "status": "success",
                    "formatted": False,
                    "dry_run": True,
                    "issues": issues if issues else [all_output],
                    "message": "Code formatting check completed, formatting issues found",
                    "backup_file": backup_path
                }
            else:
                # Formatting is correct
                return {
                    "status": "success",
                    "formatted": True,
                    "dry_run": True,
                    "issues": [],
                    "message": "Code formatting is correct",
                    "backup_file": backup_path
                }
        
        # Non-check mode
        if result.returncode == 0:
            # Formatting succeeded
            if not in_place:
                # Read formatted content from stdout
                # pasfmt stdout mode outputs "filepath:\nformatted_code", need to remove file name prefix
                _lines = stdout.split('\n', 1)
                if len(_lines) > 1 and ':' in _lines[0]:
                    formatted_content = _lines[1]
                else:
                    formatted_content = stdout
                return {
                    "status": "success",
                    "formatted": True,
                    "content": formatted_content,
                    "message": "Code formatted successfully",
                    "backup_file": backup_path
                }
            else:
                # in_place succeeded, apply uses compaction post-processing
                effective_uses_style = uses_style if uses_style is not None else _USES_STYLE
                if effective_uses_style == "compact":
                    try:
                        with open(file_path, 'r', encoding=encoding) as f:
                            file_content = f.read()
                        compacted = _compact_uses_clause(file_content)
                        if compacted != file_content:
                            with open(file_path, 'w', encoding=encoding) as f:
                                f.write(compacted)
                            logger.info(f"uses clause compacted: {file_path}")
                    except Exception as e:
                        logger.warning(f"uses compaction failed: {str(e)}")

                return {
                    "status": "success",
                    "formatted": True,
                    "message": "Code formatted successfully",
                    "backup_file": backup_path
                }
        else:
            # Failed
            error_msg = f"pasfmt execution failed (exit code: {result.returncode})"
            if stderr:
                error_msg += f": {stderr}"
            elif stdout:
                error_msg += f": {stdout}"
            
            logger.error(error_msg)
            return {
                "status": "failed",
                "error_code": "PASFMT_EXECUTION_FAILED",
                "error_message": error_msg,
                "formatted": False,
                "backup_file": backup_path
            }
            
    except subprocess.TimeoutExpired:
        error_msg = "pasfmt execution timed out"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "TIMEOUT",
            "error_message": error_msg,
            "formatted": False,
            "backup_file": backup_path
        }
    except Exception as e:
        error_msg = f"An exception occurred while executing pasfmt: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "status": "failed",
            "error_code": "EXECUTION_ERROR",
            "error_message": error_msg,
            "formatted": False,
            "backup_file": backup_path
        }



async def format_code(
    code: str,
    config_path: Optional[str] = None,
    uses_style: Optional[str] = None
) -> CallToolResult:
    """
    Format a Delphi code string

    Args:
        code: Delphi code to format
        config_path: pasfmt configuration file path (optional)
        uses_style: uses clause style, None=use global setting, "compact"=merge into one line, "pasfmt_default"=keep pasfmt as-is

    Returns:
        Formatting result dictionary
    """
    logger.info("Received code string formatting request")
    
    # Get pasfmt path
    pasfmt_path = get_pasfmt_path()
    if not pasfmt_path:
        error_msg = (
            "pasfmt is not installed. Download URL: https://github.com/integrated-application-development/pasfmt/releases\n"
            "The AI Agent should download and install the latest version for the operating system"
        )
        logger.error(error_msg)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )
    
    # Create temporary file (save path before writing content to avoid temp_input being undefined if write raises)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pas', delete=False, encoding='utf-8') as tmp:
        temp_input = tmp.name
        tmp.write(code)
    
    try:
        # Build pasfmt command
        cmd = [pasfmt_path]
        
        # Add config file argument
        if config_path and os.path.exists(config_path):
            cmd.extend(["--config-file", config_path])
        
        # Use stdout mode
        cmd.extend(["--mode", "stdout"])
        
        # Add input file
        cmd.append(temp_input)
        
        # Execute pasfmt
        logger.info(f"Executing command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=TIMEOUT_PASFMT,  # 30 second timeout
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        
        # Clean up input temp file
        os.unlink(temp_input)
        
        stdout = result.stdout.strip()
        
        if result.returncode == 0:
            # Remove file name prefix (pasfmt stdout mode outputs "filepath:\nformatted_code")
            lines = stdout.split('\n', 1)
            if len(lines) > 1 and ':' in lines[0]:
                formatted_content = lines[1]
            else:
                formatted_content = stdout

            # Apply uses compaction post-processing
            effective_uses_style = uses_style if uses_style is not None else _USES_STYLE
            if effective_uses_style == "compact":
                formatted_content = _compact_uses_clause(formatted_content)

            return CallToolResult(
                content=[{"type": "text", "text": formatted_content}],
                isError=False
            )
        else:
            # Failed
            error_msg = f"pasfmt execution failed (exit code: {result.returncode})"
            stderr = result.stderr.strip()
            if stderr:
                error_msg += f": {stderr}"
            
            logger.error(error_msg)
            return CallToolResult(
                content=[{"type": "text", "text": error_msg}],
                isError=True
            )
            
    except subprocess.TimeoutExpired:
        # Clean up temp file
        if os.path.exists(temp_input):
            os.unlink(temp_input)
        
        error_msg = "pasfmt execution timed out"
        logger.error(error_msg)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )
    except Exception as e:
        # Clean up temp file
        if os.path.exists(temp_input):
            os.unlink(temp_input)
        
        error_msg = f"An exception occurred while executing pasfmt: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )


def _download_file(url: str, destination: str, source_name: str = "source") -> Tuple[bool, str]:
    """
    Download a file, supporting retries and mirrors
    
    Args:
        url: Download URL
        destination: Destination file path
        source_name: Source name (used for logging)
    
    Returns:
        (success flag, error message)
    """
    try:
        logger.info(f"Downloading from {source_name}: {url}")
        
        # Set timeout and retry
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(
            url,
            headers=headers,
            stream=True,
            timeout=TIMEOUT_NETWORK_REQUEST,
        )
        response.raise_for_status()
        
        # Get file size
        total_size = int(response.headers.get('content-length', 0))
        
        # Download file
        with open(destination, 'wb') as f:
            if total_size == 0:
                f.write(response.content)
            else:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE_DOWNLOAD):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        # Progress display can be added, but omitted here for brevity
        
        logger.info(f"Download complete: {destination} ({os.path.getsize(destination)} bytes)")
        return True, ""
        
    except requests.exceptions.Timeout:
        error_msg = f"Download timed out: {url}"
        logger.error(error_msg)
        return False, error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"Download failed: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"An error occurred during download: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg


async def download_and_install_pasfmt(install_dir: str = None) -> Dict[str, Any]:
    """
    Download and install the pasfmt tool
    
    Args:
        install_dir: Installation directory, defaults to tools/pasfmt/cli under the project root
    
    Returns:
        Installation result dictionary
    """
    logger.info("Starting download and installation of pasfmt tool")
    
    # Determine installation directory
    if not install_dir:
        # Use the tools/pasfmt/cli directory under the project root
        project_root = Path(__file__).parent.parent.parent
        install_dir = str(project_root / "tools" / "pasfmt" / "cli")
    
    # Create installation directory
    try:
        os.makedirs(install_dir, exist_ok=True)
        logger.info(f"Creating installation directory: {install_dir}")
    except Exception as e:
        error_msg = f"Failed to create installation directory: {str(e)}"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "CREATE_DIR_FAILED",
            "error_message": error_msg,
            "install_dir": install_dir
        }
    
    # Temporary file path
    temp_zip = os.path.join(tempfile.gettempdir(), "pasfmt_%d.zip" % os.getpid())
    
    # Try downloading from multiple sources
    download_success = False
    last_error = ""
    
    for source in PASFMT_DOWNLOAD_SOURCES:
        url = source["url"]
        source_name = source["name"]
        
        logger.info(f"Trying to download from {source_name}: {url}")
        success, error = _download_file(url, temp_zip, source_name)
        
        if success:
            download_success = True
            break
        else:
            last_error = error
            logger.warning(f"Download from {source_name} failed: {error}")
            
            # Try mirror
            if "mirror" in source:
                mirror_url = source["mirror"]
                logger.info(f"Trying to download from {source_name} mirror: {mirror_url}")
                success, error = _download_file(mirror_url, temp_zip, f"{source_name} mirror")
                if success:
                    download_success = True
                    break
                else:
                    last_error = error
                    logger.warning(f"Download from {source_name} mirror failed: {error}")
    
    if not download_success:
        logger.warning(f"All download sources failed, trying to compile and install from source. Last error: {last_error}")
        
        # Try compiling from source
        compile_result = await compile_from_source("pasfmt", install_dir, "release")
        
        if compile_result.get("status") == "success":
            logger.info("Source compilation and installation succeeded")
            return compile_result
        else:
            # Compilation also failed, return error
            return {
                "status": "failed",
                "error_code": "DOWNLOAD_AND_COMPILE_FAILED",
                "error_message": f"Both download and compilation failed. Download error: {last_error}, compilation error: {compile_result.get('error_message', 'unknown error')}",
                "install_dir": install_dir,
                "download_error": last_error,
                "compile_error": compile_result.get("error_message")
            }
    
    # Extract file
    try:
        logger.info(f"Extracting file: {temp_zip}")
        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
            # Find pasfmt.exe
            exe_files = [f for f in zip_ref.namelist() if f.endswith('.exe') and 'pasfmt' in f.lower()]
            
            if not exe_files:
                # Try to find any executable file
                exe_files = [f for f in zip_ref.namelist() if f.endswith('.exe')]
            
            if not exe_files:
                error_msg = "No executable file found in ZIP file"
                logger.error(error_msg)
                return {
                    "status": "failed",
                    "error_code": "NO_EXECUTABLE_FOUND",
                    "error_message": error_msg,
                    "install_dir": install_dir
                }
            
            # Extract all files
            zip_ref.extractall(install_dir)
            logger.info(f"Extraction complete to: {install_dir}")
            
            # Find extracted pasfmt.exe
            exe_path = None
            for root, dirs, files in os.walk(install_dir):
                for file in files:
                    if file.lower() == 'pasfmt.exe':
                        exe_path = os.path.join(root, file)
                        break
                if exe_path:
                    break
            
            if not exe_path:
                # Find any exe file
                for root, dirs, files in os.walk(install_dir):
                    for file in files:
                        if file.endswith('.exe'):
                            exe_path = os.path.join(root, file)
                            # Rename to pasfmt.exe
                            new_path = os.path.join(install_dir, 'pasfmt.exe')
                            os.rename(exe_path, new_path)
                            exe_path = new_path
                            break
                    if exe_path:
                        break
            
            if not exe_path:
                error_msg = "No executable file found after extraction"
                logger.error(error_msg)
                return {
                    "status": "failed",
                    "error_code": "EXE_NOT_FOUND_AFTER_EXTRACT",
                    "error_message": error_msg,
                    "install_dir": install_dir
                }
            
            # Set path
            global _PASFMT_PATH
            _PASFMT_PATH = exe_path
            
            # Clean up temp file
            try:
                os.unlink(temp_zip)
                logger.info(f"Cleaning up temp file: {temp_zip}")
            except OSError:
                pass
            
            return {
                "status": "success",
                "message": f"pasfmt installed successfully to: {install_dir}",
                "install_dir": install_dir,
                "exe_path": exe_path,
                "pasfmt_path": exe_path
            }
            
    except zipfile.BadZipFile:
        error_msg = "The downloaded file is not a valid ZIP file"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "INVALID_ZIP",
            "error_message": error_msg,
            "install_dir": install_dir
        }
    except Exception as e:
        error_msg = f"Failed to extract file: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "status": "failed",
            "error_code": "EXTRACT_FAILED",
            "error_message": error_msg,
            "install_dir": install_dir
        }
async def download_and_install_pasfmt_rad(
    delphi_version: str = "11",
    install_64bit: bool = False,
    install_dir: str = None
) -> Dict[str, Any]:
    """
    Download and install the pasfmt-rad IDE plugin
    
    Args:
        delphi_version: Delphi version (11, 12, 13)
        install_64bit: Whether to install the 64-bit version
        install_dir: Installation directory, defaults to tools/pasfmt/rad under the project root
    
    Returns:
        Installation result dictionary
    """
    logger.info(f"Starting download and installation of pasfmt-rad IDE plugin (Delphi {delphi_version})")
    
    # Check Delphi version
    if delphi_version not in DELPHI_VERSIONS:
        error_msg = f"Unsupported Delphi version: {delphi_version}. Supported: {', '.join(DELPHI_VERSIONS.keys())}"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "UNSUPPORTED_DELPHI_VERSION",
            "error_message": error_msg
        }
    
    version_info = DELPHI_VERSIONS[delphi_version]
    
    # Determine the filename to download
    if install_64bit and version_info["bpl_64"]:
        bpl_filename = version_info["bpl_64"]
    else:
        bpl_filename = version_info["bpl_32"]
    
    if not bpl_filename:
        error_msg = f"Delphi {delphi_version} does not support the {'64-bit' if install_64bit else '32-bit'} version"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "UNSUPPORTED_ARCHITECTURE",
            "error_message": error_msg
        }
    
    # Determine installation directory
    if not install_dir:
        # Use the tools/pasfmt/rad directory under the project root
        project_root = Path(__file__).parent.parent.parent
        install_dir = str(project_root / "tools" / "pasfmt" / "rad")
    
    # Create directory (if it does not exist)
    try:
        os.makedirs(install_dir, exist_ok=True)
        logger.info(f"Installation directory: {install_dir}")
    except Exception as e:
        error_msg = f"Failed to create installation directory: {str(e)}"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "CREATE_INSTALL_DIR_FAILED",
            "error_message": error_msg,
            "install_dir": install_dir
        }
    
    # Target file path
    target_path = os.path.join(install_dir, bpl_filename)
    
    # Temporary file path
    temp_bpl = os.path.join(tempfile.gettempdir(), bpl_filename)
    
    # Try downloading from multiple sources
    download_success = False
    last_error = ""
    
    for source in PASFMT_RAD_DOWNLOAD_SOURCES:
        url = source["base_url"] + bpl_filename
        source_name = source["name"]
        
        logger.info(f"Trying to download from {source_name}: {url}")
        success, error = _download_file(url, temp_bpl, source_name)
        
        if success:
            download_success = True
            break
        else:
            last_error = error
            logger.warning(f"Failed to download from {source_name}: {error}")
            
            # Try mirror
            if "mirror" in source:
                mirror_url = source["mirror"] + bpl_filename
                logger.info(f"Trying to download from {source_name} mirror: {mirror_url}")
                success, error = _download_file(mirror_url, temp_bpl, f"{source_name} mirror")
                if success:
                    download_success = True
                    break
                else:
                    last_error = error
                    logger.warning(f"Failed to download from {source_name} mirror: {error}")
    
    if not download_success:
        logger.warning(f"All download sources failed, trying to compile and install from source. Last error: {last_error}")
        
        # Try compiling from source
        compile_result = await compile_from_source("pasfmt-rad", install_dir, "release")
        
        if compile_result.get("status") == "success":
            logger.info("Compiled and installed from source successfully")
            # Update target path to the executable path in the build result
            if "executable" in compile_result:
                target_path = compile_result["executable"]
                bpl_filename = os.path.basename(target_path)
            
            return {
                "status": "success",
                "message": f"pasfmt-rad IDE plugin compiled and installed from source successfully",
                "delphi_version": delphi_version,
                "delphi_name": version_info["name"],
                "bpl_filename": bpl_filename,
                "install_path": target_path,
                "registry_success": False,  # Compiled installation does not auto-register
                "source": "compiled"
            }
        else:
            # Compilation also failed, returning error
            return {
                "status": "failed",
                "error_code": "DOWNLOAD_AND_COMPILE_FAILED",
                "error_message": f"Both download and compilation failed. Download error: {last_error}, compilation error: {compile_result.get('error_message', 'Unknown error')}",
                "install_dir": install_dir,
                "bpl_filename": bpl_filename,
                "download_error": last_error,
                "compile_error": compile_result.get("error_message")
            }
    
    # Copy file to target location
    try:
        shutil.copy2(temp_bpl, target_path)
        logger.info(f"Copying file to: {target_path}")
        
        # Clean up temporary file
        try:
            os.unlink(temp_bpl)
            logger.info(f"Cleaning up temporary file: {temp_bpl}")
        except OSError:
            pass
        
        # Register with IDE (Windows registry)
        if sys.platform == "win32":
            try:
                import winreg
                
                # Delphi registry path
                registry_version = _bds_registry_version(delphi_version)
                reg_path = f"{REG_KEY_EMBARCADERO_BDS}\\{registry_version}\\Known Packages"
                
                # Open or create registry key
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_WRITE)
                except FileNotFoundError:
                    # Create key
                    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path)
                
                # Set value
                package_name = bpl_filename.replace('.bpl', '')
                winreg.SetValueEx(key, target_path, 0, winreg.REG_SZ, package_name)
                winreg.CloseKey(key)
                
                logger.info(f"Registered in registry: {reg_path}")
                registry_success = True
                
            except Exception as e:
                logger.warning(f"Registry operation failed: {str(e)}, manual registration required")
                registry_success = False
        else:
            registry_success = True  # Non-Windows platforms do not need registry
        
        return {
            "status": "success",
            "message": f"pasfmt-rad IDE plugin installed successfully",
            "delphi_version": delphi_version,
            "delphi_name": version_info["name"],
            "bpl_filename": bpl_filename,
            "install_path": target_path,
            "registry_success": registry_success if sys.platform == "win32" else None,
            "registry_path": (
                f"HKEY_CURRENT_USER\\{REG_KEY_EMBARCADERO_BDS}\\"
                f"{_bds_registry_version(delphi_version)}\\Known Packages"
                if sys.platform == "win32"
                else None
            ),
            "registry_value": target_path if sys.platform == "win32" else None
        }
        
    except Exception as e:
        error_msg = f"Failed to copy file: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "status": "failed",
            "error_code": "COPY_FAILED",
            "error_message": error_msg,
            "install_dir": install_dir,
            "bpl_filename": bpl_filename
        }


async def check_pasfmt_installation() -> CallToolResult:
    """
    Check pasfmt installation status
    
    Returns:
        Check result dictionary
    """
    logger.info("Checking pasfmt installation status")
    
    # Check whether pasfmt is installed
    pasfmt_path = get_pasfmt_path()
    
    if pasfmt_path and os.path.exists(pasfmt_path):
        return CallToolResult(
            content=[{"type": "text", "text": f"pasfmt is installed: {pasfmt_path}"}]
        )
    else:
        # Check possible installation locations
        default_paths = _pasfmt_default_paths()
        
        found_paths = []
        for path in default_paths:
            if os.path.exists(path):
                found_paths.append(path)
        
        if found_paths:
            # Set the found path
            set_pasfmt_path(found_paths[0])
            return CallToolResult(
                content=[{"type": "text", "text": f"Found pasfmt: {found_paths[0]}"}]
            )
        else:
            # Suggest installing to tools/pasfmt/cli under the project directory
            suggested_dir = str(_project_root() / "tools" / "pasfmt" / "cli")
            
            return CallToolResult(
                content=[{"type": "text", "text": f"pasfmt not found, suggested installation location: {suggested_dir}"}],
                isError=True
            )


async def check_pasfmt_rad_installation(delphi_version: str = "11") -> Dict[str, Any]:
    """
    Check pasfmt-rad IDE plugin installation status
    
    Args:
        delphi_version: Delphi version (11, 12, 13)
    
    Returns:
        Check result dictionary
    """
    logger.info(f"Checking pasfmt-rad IDE plugin installation status (Delphi {delphi_version})")
    
    if delphi_version not in DELPHI_VERSIONS:
        return {
            "status": "failed",
            "error_code": "UNSUPPORTED_DELPHI_VERSION",
            "error_message": f"Unsupported Delphi version: {delphi_version}"
        }
    
    version_info = DELPHI_VERSIONS[delphi_version]
    
    # Check 32-bit and 64-bit versions
    bpl_files = []
    if version_info["bpl_32"]:
        bpl_files.append(version_info["bpl_32"])
    if version_info["bpl_64"]:
        bpl_files.append(version_info["bpl_64"])
    
    # Check common installation locations
    possible_dirs = _pasfmt_rad_candidate_dirs(delphi_version)
    
    installed_files = []
    for bpl_file in bpl_files:
        for dir_path in possible_dirs:
            file_path = os.path.join(dir_path, bpl_file)
            if os.path.exists(file_path):
                installed_files.append({
                    "filename": bpl_file,
                    "path": file_path,
                    "directory": dir_path
                })
    
    # Check registry (Windows only)
    registry_installed = False
    registry_path = None
    if sys.platform == "win32" and installed_files:
        try:
            import winreg
            registry_version = _bds_registry_version(delphi_version)
            reg_path = f"{REG_KEY_EMBARCADERO_BDS}\\{registry_version}\\Known Packages"
            
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ)
                
                # Check whether registered
                for bpl_file in bpl_files:
                    for dir_path in possible_dirs:
                        file_path = os.path.join(dir_path, bpl_file)
                        try:
                            value, reg_type = winreg.QueryValueEx(key, file_path)
                            if value:
                                registry_installed = True
                                registry_path = reg_path
                                break
                        except FileNotFoundError:
                            continue
                
                winreg.CloseKey(key)
            except FileNotFoundError:
                pass  # Registry key does not exist
                
        except ImportError:
            pass  # Non-Windows platform or no winreg module
    
    if installed_files:
        return {
            "status": "success",
            "installed": True,
            "delphi_version": delphi_version,
            "delphi_name": version_info["name"],
            "installed_files": installed_files,
            "registry_installed": registry_installed,
            "registry_path": registry_path,
            "message": f"Found {len(installed_files)} installed plugin file(s)"
        }
    else:
        return {
            "status": "success",
            "installed": False,
            "delphi_version": delphi_version,
            "delphi_name": version_info["name"],
            "message": f"pasfmt-rad IDE plugin not found (Delphi {delphi_version})",
            "suggested_paths": possible_dirs
        }


async def compile_from_source(
    source_type: str = "pasfmt",
    install_dir: str = None,
    build_type: str = "release"
) -> Dict[str, Any]:
    """
    Compile and install pasfmt or pasfmt-rad from source
    
    Args:
        source_type: Source type, 'pasfmt' or 'pasfmt-rad'
        install_dir: Installation directory
        build_type: Build type, 'release' or 'debug'
    
    Returns:
        Compilation result dictionary
    """
    logger.info(f"Starting compilation from source for {source_type} (build type: {build_type})")
    
    # Determine installation directory
    if not install_dir:
        project_root = Path(__file__).parent.parent.parent
        if source_type == "pasfmt":
            install_dir = str(project_root / "tools" / "pasfmt" / "cli")
        else:  # pasfmt-rad
            install_dir = str(project_root / "tools" / "pasfmt" / "rad")
    
    # Create installation directory
    try:
        os.makedirs(install_dir, exist_ok=True)
        logger.info(f"Installation directory: {install_dir}")
    except Exception as e:
        error_msg = f"Failed to create installation directory: {str(e)}"
        logger.error(error_msg)
        return {
            "status": "failed",
            "error_code": "DIRECTORY_CREATION_FAILED",
            "error_message": error_msg
        }
    
    # Select source repository
    if source_type == "pasfmt":
        repositories = PASFMT_SOURCE_REPOSITORIES
        repo_name = "pasfmt"
    else:  # pasfmt-rad
        repositories = PASFMT_RAD_SOURCE_REPOSITORIES
        repo_name = "pasfmt-rad"
    
    # Create temporary directory for cloning source code
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"{repo_name}_build_")
        logger.info(f"Temporary build directory: {temp_dir}")
        
        # Try cloning code from different sources
        clone_success = False
        last_error = None
        
        for repo in repositories:
            repo_url = repo.get("url")
            repo_mirror = repo.get("mirror", repo_url)
            repo_name_display = repo["name"]
            
            logger.info(f"Trying to clone from {repo_name_display}: {repo_url}")
            
            try:
                # First try the primary source
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", repo_url, temp_dir],
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_PASFMT_GIT_CLONE,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
                
                if result.returncode == 0:
                    clone_success = True
                    logger.info(f"Cloned successfully from {repo_name_display}")
                    break
                else:
                    logger.warning(f"Failed to clone from {repo_name_display}: {result.stderr}")
                    
                    # Try mirror
                    logger.info(f"Trying to clone from mirror: {repo_mirror}")
                    result = subprocess.run(
                        ["git", "clone", "--depth", "1", repo_mirror, temp_dir],
                        capture_output=True,
                        text=True,
                        timeout=TIMEOUT_PASFMT_GIT_CLONE,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                    )
                    
                    if result.returncode == 0:
                        clone_success = True
                        logger.info(f"Cloned successfully from mirror")
                        break
                    else:
                        last_error = result.stderr
                        logger.warning(f"Failed to clone from mirror: {result.stderr}")
                        
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Clone failed: {last_error}")
        
        if not clone_success:
            return {
                "status": "failed",
                "error_code": "GIT_CLONE_FAILED",
                "error_message": f"All source repositories failed to clone. Last error: {last_error}",
                "install_dir": install_dir
            }
        
        # Build project
        logger.info(f"Starting build for {source_type}...")
        
        # Check build script
        build_script = None
        if source_type == "pasfmt":
            # pasfmt uses cargo build (Rust project)
            build_script = os.path.join(temp_dir, "Cargo.toml")
            if os.path.exists(build_script):
                logger.info("Detected Rust project, using cargo build")
                
                # Install Rust toolchain (if not installed)
                try:
                    rustc_check = subprocess.run(["rustc", "--version"], capture_output=True, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    if rustc_check.returncode != 0:
                        logger.warning("Rust toolchain is not installed, attempting to install...")
                        # Rust installation logic can be added here
                        return {
                            "status": "failed",
                            "error_code": "RUST_NOT_INSTALLED",
                            "error_message": "Rust toolchain is not installed, please install Rust first",
                            "install_dir": install_dir
                        }
                    
                    # Build with cargo
                    build_cmd = ["cargo", "build", "--release"] if build_type == "release" else ["cargo", "build"]
                    result = subprocess.run(
                        build_cmd,
                        cwd=temp_dir,
                        capture_output=True,
                        text=True,
                        timeout=TIMEOUT_PASFMT_BUILD,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                    )
                    
                    if result.returncode != 0:
                        return {
                            "status": "failed",
                            "error_code": "CARGO_BUILD_FAILED",
                            "error_message": f"cargo build failed: {result.stderr}",
                            "install_dir": install_dir
                        }
                    
                    # Find build artifacts
                    target_dir = os.path.join(temp_dir, "target", "release" if build_type == "release" else "debug")
                    if not os.path.exists(target_dir):
                        return {
                            "status": "failed",
                            "error_code": "BUILD_OUTPUT_NOT_FOUND",
                            "error_message": f"Build output directory does not exist: {target_dir}",
                            "install_dir": install_dir
                        }
                    
                    # Copy executable
                    if source_type == "pasfmt":
                        exe_name = "pasfmt.exe" if sys.platform == "win32" else "pasfmt"
                        source_exe = os.path.join(target_dir, exe_name)
                        
                        if not os.path.exists(source_exe):
                            # Try searching in subdirectories
                            for root, dirs, files in os.walk(target_dir):
                                if exe_name in files:
                                    source_exe = os.path.join(root, exe_name)
                                    break
                        
                        if os.path.exists(source_exe):
                            dest_exe = os.path.join(install_dir, exe_name)
                            shutil.copy2(source_exe, dest_exe)
                            logger.info(f"Copying executable to: {dest_exe}")
                            
                            # Set executable permissions (non-Windows)
                            if sys.platform != "win32":
                                os.chmod(dest_exe, 0o755)
                            
                            return {
                                "status": "success",
                                "message": f"{source_type} compiled and installed successfully",
                                "install_dir": install_dir,
                                "executable": dest_exe,
                                "build_type": build_type,
                                "source": "git"
                            }
                        else:
                            return {
                                "status": "failed",
                                "error_code": "EXECUTABLE_NOT_FOUND",
                                "error_message": f"Executable not found: {exe_name}",
                                "install_dir": install_dir
                            }
                except Exception as e:
                    return {
                        "status": "failed",
                        "error_code": "BUILD_PROCESS_FAILED",
                        "error_message": f"Build process failed: {str(e)}",
                        "install_dir": install_dir
                    }
            else:
                return {
                    "status": "failed",
                    "error_code": "NO_BUILD_SYSTEM",
                    "error_message": "Build system not found (Cargo.toml)",
                    "install_dir": install_dir
                }
        else:  # pasfmt-rad
            # pasfmt-rad is a Delphi project and requires the Delphi compiler
            logger.warning("pasfmt-rad is a Delphi project and requires the Delphi compiler for building")
            logger.info("It is recommended to install from precompiled binaries or compile manually using the Delphi IDE")
            
            return {
                "status": "failed",
                "error_code": "DELPHI_COMPILER_REQUIRED",
                "error_message": "pasfmt-rad requires the Delphi compiler for building. Please install from precompiled binaries or compile manually using the Delphi IDE.",
                "install_dir": install_dir,
                "source_dir": temp_dir
            }
    
    except Exception as e:
        error_msg = f"Compilation process failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "status": "failed",
            "error_code": "COMPILATION_FAILED",
            "error_message": error_msg,
            "install_dir": install_dir
        }
    
    finally:
        # Clean up temporary directory
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaning up temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory: {str(e)}")