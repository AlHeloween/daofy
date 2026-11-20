"""
Process Manager

Responsible for compiler process creation, monitoring, timeout handling, and output capture
"""

import asyncio
import os
from typing import Callable, Tuple, Optional
from ..constants import TIMEOUT_PROCESS_TERMINATE
from ..utils import get_console_encoding
from ..utils.delphi_env import get_delphi_common_dir
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ProcessManager:
    """Compiler process manager"""

    def __init__(self):
        """Initialize the process manager and detect console encoding"""
        self._encoding = get_console_encoding()
        logger.debug(f"Process manager initialized, console encoding: {self._encoding}")

    def _get_delphi_env(self, compiler_path: str) -> dict:
        """
        Get environment variables required by the Delphi compiler

        Args:
            compiler_path: Compiler path

        Returns:
            Environment variable dictionary
        """
        # Infer the Delphi installation path from the compiler path
        if 'Studio' in compiler_path:
            import re
            match = re.search(r'(.+Studio\\\d+\.\d+)', compiler_path)
            if match:
                bds_path = match.group(1)
                bds_version = bds_path.split('\\')[-1]
                env = {
                    'BDS': bds_path,
                    'BDSINCLUDE': f"{bds_path}\\include",
                    'LANGDIR': 'EN',
                }
                common_dir = get_delphi_common_dir(bds_version)
                if common_dir is not None:
                    env['BDSCOMMONDIR'] = str(common_dir)
                logger.debug(f"Setting Delphi environment variables: {env}")
                return env
        return {}

    async def execute(
        self,
        executable: str,
        args: list,
        timeout: int
    ) -> Tuple[int, str, str]:
        """
        Execute the compiler process

        Args:
            executable: Executable file path
            args: Argument list
            timeout: Timeout (seconds)

        Returns:
            (return_code, stdout, stderr) tuple

        Raises:
            TimeoutError: Compilation timed out
            RuntimeError: Process execution failed
        """
        logger.info(f"Starting compiler process: {executable}")
        logger.debug(f"Arguments: {' '.join(args)}")

        try:
            # Get Delphi environment variables
            delphi_env = self._get_delphi_env(executable)
            
            # Merge environment variables
            env = os.environ.copy()
            env.update(delphi_env)

            # Create process
            process = await asyncio.create_subprocess_exec(
                executable,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            logger.debug(f"Process started, PID: {process.pid}")

            # Wait for completion or timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )

                return_code = process.returncode
                stdout_str = stdout.decode(self._encoding, errors='ignore')
                stderr_str = stderr.decode(self._encoding, errors='ignore')

                logger.info(f"Process completed, return code: {return_code}")
                logger.debug(f"stdout length: {len(stdout_str)}, stderr length: {len(stderr_str)}")

                return (return_code, stdout_str, stderr_str)

            except asyncio.TimeoutError:
                logger.error(f"Compilation timed out ({timeout} seconds), terminating process")
                await self.kill_process(process)
                raise TimeoutError(f"Compilation timed out ({timeout} seconds)")

        except FileNotFoundError:
            error_msg = f"Compiler executable does not exist: {executable}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        except Exception as e:
            error_msg = f"Process execution failed: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    async def kill_process(self, process: asyncio.subprocess.Process):
        """
        Force-terminate the process

        Args:
            process: Process object
        """
        try:
            logger.warning(f"Terminating process PID: {process.pid}")
            # kill() may return a coroutine in AsyncMock; support both cases
            _r = process.kill()
            if asyncio.iscoroutine(_r):
                await _r
            # wait with a short timeout to prevent lingering pipes from blocking wait() after communicate() is cancelled
            await asyncio.wait_for(process.wait(), timeout=TIMEOUT_PROCESS_TERMINATE)
            logger.info(f"Process terminated")
        except asyncio.TimeoutError:
            logger.warning(
                f"Terminating process wait() timed out ({TIMEOUT_PROCESS_TERMINATE} seconds), but the process has been killed, PID: {process.pid}"
            )
        except ProcessLookupError:
            logger.warning(f"Process does not exist; it may have already terminated")
        except Exception as e:
            logger.error(f"Failed to terminate process: {str(e)}")

    async def execute_with_callback(
        self,
        executable: str,
        args: list,
        timeout: int,
        stdout_callback: Optional[Callable] = None,
        stderr_callback: Optional[Callable] = None
    ) -> Tuple[int, str, str]:
        """
        Execute the compiler process with real-time output callbacks

        Args:
            executable: Executable file path
            args: Argument list
            timeout: Timeout (seconds)
            stdout_callback: stdout output callback function
            stderr_callback: stderr output callback function

        Returns:
            (return_code, stdout, stderr) tuple
        """
        logger.info(f"Starting compiler process (with callbacks): {executable}")

        try:
            process = await asyncio.create_subprocess_exec(
                executable,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout_lines = []
            stderr_lines = []

            async def read_stream(stream, callback, lines_list):
                """Read the stream and invoke the callback"""
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    line_str = line.decode(self._encoding, errors='ignore').rstrip()
                    lines_list.append(line_str)
                    if callback:
                        callback(line_str)

            # Read stdout and stderr concurrently
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(process.stdout, stdout_callback, stdout_lines),
                        read_stream(process.stderr, stderr_callback, stderr_lines)
                    ),
                    timeout=timeout
                )

                await process.wait()

                return_code = process.returncode
                stdout_str = '\n'.join(stdout_lines)
                stderr_str = '\n'.join(stderr_lines)

                logger.info(f"Process completed, return code: {return_code}")
                return (return_code, stdout_str, stderr_str)

            except asyncio.TimeoutError:
                logger.error(f"Compilation timed out ({timeout} seconds), terminating process")
                await self.kill_process(process)
                raise TimeoutError(f"Compilation timed out ({timeout} seconds)")

        except Exception as e:
            error_msg = f"Process execution failed: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

