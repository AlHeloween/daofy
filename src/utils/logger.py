"""
Logging utility module.

Provides unified log configuration and logger accessors.
Features:
- One log file per date (delphi_mcp_YYYY-MM-DD.log)
- Automatic 7z compression archive of historical logs
- API call argument/return-value logging (controlled by a config switch)
"""

import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from ..constants import TIMEOUT_ARCHIVE_7Z


# ---------------------------------------------------------------------------
# Log configuration
# ---------------------------------------------------------------------------

@dataclass
class LogConfig:
    """Log configuration."""
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_api_calls: bool = False
    archive_old_logs: bool = True
    keep_days: int = 7
    console_logging: bool = False


_CONFIG_FILE_NAME = "config/logging_config.json"
_LOG_FORMAT = "%(asctime)s - PID:%(process)d - %(name)s - %(levelname)s - %(message)s"
_LOG_FILE_PREFIX = "delphi_mcp"

# Cached configuration
_log_config: Optional[LogConfig] = None


def _log_nonfatal(message: str, exc: Exception) -> None:
    """Log best-effort cleanup errors without requiring module logger setup."""
    logging.getLogger("delphi_mcp").debug(message, str(exc))


def _get_project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent.parent


def _load_log_config() -> LogConfig:
    """Load the log configuration from config/logging_config.json."""
    global _log_config
    if _log_config is not None:
        return _log_config

    cfg_path = _get_project_root() / _CONFIG_FILE_NAME
    config = LogConfig()
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            config.log_level = data.get("log_level", config.log_level).upper()
            config.log_dir = data.get("log_dir", config.log_dir)
            config.log_api_calls = data.get("log_api_calls", config.log_api_calls)
            config.archive_old_logs = data.get("archive_old_logs", config.archive_old_logs)
            config.keep_days = int(data.get("keep_days", config.keep_days))
            config.console_logging = data.get("console_logging", config.console_logging)
        except Exception as e:
            _log_nonfatal("Ignoring non-fatal exception: %s", e)
    _log_config = config
    return config


def reload_log_config() -> LogConfig:
    """Reload the log configuration (for runtime updates)."""
    global _log_config
    _log_config = None
    return _load_log_config()


def should_log_api_calls() -> bool:
    """Check whether API call logging is enabled."""
    return _load_log_config().log_api_calls


# ---------------------------------------------------------------------------
# Historical log 7z archive
# ---------------------------------------------------------------------------

def _find_7z_path() -> Optional[str]:
    """Locate the 7z executable path."""
    # Prefer the project's bundled tools/7z/7z.exe
    builtin = _get_project_root() / "tools" / "7z" / "7z.exe"
    if builtin.exists():
        return str(builtin)
    for name in ("7z", "7z.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def archive_old_logs(log_dir: Optional[str] = None) -> None:
    """
    Compress historical log files into 7z and delete the originals.
    At most one 7z archive is kept per day. Archives older than keep_days
    days are deleted automatically.

    Multiprocess-safe: a pid file provides mutual exclusion so archives never
    run concurrently.

    Args:
        log_dir: log directory; read from the configuration when omitted
    """
    config = _load_log_config()
    if not config.archive_old_logs:
        return

    log_path = Path(log_dir) if log_dir else _get_project_root() / config.log_dir
    if not log_path.exists():
        return

    seven_z = _find_7z_path()
    if not seven_z:
        return  # No 7z tool available; skip archiving

    # Multiprocess mutex: a .archive_lock file prevents concurrent archiving
    lock_file = log_path / ".archive_lock"
    if lock_file.exists():
        return  # Another process is archiving; skip
    try:
        lock_file.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        return

    try:
        today_str = date.today().isoformat()  # YYYY-MM-DD
        keep_days = max(config.keep_days, 1)

        # ---------------------------------------------------------------
        # 1) Delete .7z archives beyond the retention period
        # ---------------------------------------------------------------
        for archive_file in sorted(log_path.glob(f"{_LOG_FILE_PREFIX}_*.7z")):
            stem = archive_file.stem
            date_part = stem.replace(f"{_LOG_FILE_PREFIX}_", "")
            try:
                file_date = date.fromisoformat(date_part)
                if (date.today() - file_date).days > keep_days:
                    archive_file.unlink()
            except (ValueError, OverflowError):
                pass  # Filename format does not match; skip

        # ---------------------------------------------------------------
        # 2) Compress old .log files into .7z
        # ---------------------------------------------------------------
        for log_file in sorted(log_path.glob(f"{_LOG_FILE_PREFIX}_*.log")):
            # Extract the date from the filename: delphi_mcp_YYYY-MM-DD.log
            stem = log_file.stem  # delphi_mcp_YYYY-MM-DD
            date_part = stem.replace(f"{_LOG_FILE_PREFIX}_", "")
            if date_part == today_str:
                continue  # Today's log is not archived

            archive_name = log_path / f"{stem}.7z"
            if archive_name.exists():
                # The archive already exists; delete the source file (a previous compression
                # may have succeeded without deleting it)
                try:
                    log_file.unlink()
                except Exception as e:
                    _log_nonfatal("Ignoring non-fatal exception: %s", e)
                continue

            # Compress with 7z
            try:
                result = subprocess.run(
                    [seven_z, "a", "-t7z", "-mx=5", str(archive_name), str(log_file)],
                    capture_output=True, text=True, timeout=TIMEOUT_ARCHIVE_7Z,
                )
                if result.returncode == 0 and archive_name.exists():
                    log_file.unlink()
            except Exception as e:
                _log_nonfatal("Ignoring non-fatal exception: %s", e)
    finally:
        # Release the lock
        try:
            lock_file.unlink()
        except Exception as e:
            _log_nonfatal("Ignoring non-fatal exception: %s", e)


# ---------------------------------------------------------------------------
# Logger core
# ---------------------------------------------------------------------------

def _resolve_log_level(level_str: str = "INFO") -> int:
    mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return mapping.get(level_str.upper(), logging.INFO)


def _get_today_log_path(log_dir: Path) -> Path:
    """Build today's log file path: logs/delphi_mcp_YYYY-MM-DD.log"""
    today_str = date.today().isoformat()
    return log_dir / f"{_LOG_FILE_PREFIX}_{today_str}.log"


_initialized = False


_root_handlers_initialized = False
_file_logging_warning_emitted = False


def _warn_file_logging_unavailable(log_path: Path, exc: OSError) -> None:
    """Report a file logging failure without depending on logger setup."""
    global _file_logging_warning_emitted
    if _file_logging_warning_emitted:
        return

    _file_logging_warning_emitted = True
    try:
        print(
            "[Daofy] Log directory is not writable: "
            f"{log_path.parent}; grant the host write access or configure a writable directory, "
            f"otherwise file logging will be ignored. Reason: {exc}",
            file=sys.stderr,
            flush=True,
        )
    except Exception:
        # stderr is closed or its encoding is unsupported: the warning itself must not fail startup
        pass


# ---------------------------------------------------------------------------
# stderr handler: the safety net for the MCP stdio scenario
# ---------------------------------------------------------------------------
# Background (a real failure):
#   An MCP stdio server treats stderr as a side-band diagnostic channel, but the
#   client does not guarantee that it keeps draining it. Once the pipe is full,
#   logging's synchronous emit blocks forever; because logging is called
#   synchronously from the asyncio event-loop thread, the whole server freezes —
#   it cannot even answer initialize, the client only sees request timeouts and
#   keeps restarting the server, forming a loop. Handlers are also called
#   synchronously in sequence: if the console handler is queued before the file
#   handler, a stalled stderr stops file logging as well.
#
#   The constraints of this module are therefore:
#     1) the file handler must be attached first;
#     2) stderr is written only when it is "confirmed writable" or "cancellable",
#        so the caller never blocks;
#     3) the background drain thread never stays stuck in write (a write that
#        takes too long is cancelled), otherwise the interpreter would wait for
#        this thread at exit and the process could not terminate (Python 3.12+
#        finalization behaviour).
# ---------------------------------------------------------------------------
# Bytes that can be safely written to a POSIX pipe in one call (the guaranteed
# minimum of PIPE_BUF). A write never blocks while the remaining space is at
# least this large. Fragmenting or dropping logs is preferable to risking a
# hang. The Windows side does not use this value; it uses the writable quota
# from NtQueryInformationFile.
_PIPE_BUF_HINT = 512
# A single write that has not returned after this long means the pipe is blocked (the client stopped reading)
_WRITE_STUCK_SECONDS = 2.0
# How long stderr writes are paused after a block is detected, before probing again
_STDERR_BLOCKED_COOLDOWN = 30.0

# Cache of the lazily built "pipe writable quota" probe: None=not initialized, False=unavailable
_pipe_quota_probe = None


def _probe_stderr(stream) -> "tuple[str, int]":
    """Probe whether stderr can be written safely.

    Returns:
        ("pipe", free)  free > 0: bytes that can be written safely (a conservative estimate)
                        free == 0: the pipe is full, nothing can be written now
                        free == -1: confirmed pipe, but the free space is unknown (the quota probe failed)
        ("other", 0)    a regular file/console/in-memory stream: writes never block for lack of a reader
        ("unknown", 0)  cannot be determined (handled worst-case: do not write)
    """
    try:
        fd = stream.fileno()
    except Exception:
        # In-memory streams (StringIO etc.) have no fd, but writing to them never blocks
        return "other", 0

    if os.name != "nt":
        try:
            import select as _select
            import stat as _stat

            if not _stat.S_ISFIFO(os.fstat(fd).st_mode):
                return "other", 0
            _, writable, _ = _select.select([], [fd], [], 0)
            return "pipe", (_PIPE_BUF_HINT if writable else 0)
        except Exception:
            return "unknown", 0

    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        handle = wintypes.HANDLE(msvcrt.get_osfhandle(fd))
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        if kernel32.GetFileType(handle) != 3:  # FILE_TYPE_PIPE
            return "other", 0
        # PeekNamedPipe expects a read-end handle and always fails on the write
        # end (measured: ERROR_ACCESS_DENIED=5); NtQueryInformationFile is used
        # instead to read the writable quota. When that is unavailable we report
        # -1 (space unknown) and a cancellable background write is the fallback.
        quota_probe = _get_pipe_quota_probe()
        free = quota_probe(handle) if quota_probe else None
        return "pipe", (free if free is not None else -1)
    except Exception:
        return "unknown", 0


def _get_pipe_quota_probe():
    """Lazily build the "pipe writable quota" probe; returns None when the platform does not support it.

    PeekNamedPipe cannot be used on a write-end handle (it is a read-end interface), but
    NtQueryInformationFile with FilePipeLocalInformation reports WriteQuotaAvailable —
    how many bytes can still be written right now.
    Measured: empty pipe=4096, full=0, 2048 after 2 KB was read.
    """
    global _pipe_quota_probe
    if _pipe_quota_probe is not None:
        return _pipe_quota_probe or None
    try:
        import ctypes
        from ctypes import wintypes

        class IO_STATUS_BLOCK(ctypes.Structure):
            _fields_ = [("Status", ctypes.c_void_p), ("Information", ctypes.c_size_t)]

        class FILE_PIPE_LOCAL_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("NamedPipeType", wintypes.ULONG),
                ("NamedPipeConfiguration", wintypes.ULONG),
                ("MaximumInstances", wintypes.ULONG),
                ("CurrentInstances", wintypes.ULONG),
                ("InboundQuota", wintypes.ULONG),
                ("ReadDataAvailable", wintypes.ULONG),
                ("OutboundQuota", wintypes.ULONG),
                ("WriteQuotaAvailable", wintypes.ULONG),
                ("NamedPipeState", wintypes.ULONG),
                ("NamedPipeEnd", wintypes.ULONG),
            ]

        ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
        ntdll.NtQueryInformationFile.restype = ctypes.c_long
        ntdll.NtQueryInformationFile.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(IO_STATUS_BLOCK),
            ctypes.c_void_p,
            wintypes.ULONG,
            ctypes.c_int,
        ]

        def probe(handle) -> "Optional[int]":
            iosb = IO_STATUS_BLOCK()
            info = FILE_PIPE_LOCAL_INFORMATION()
            status = ntdll.NtQueryInformationFile(
                handle,
                ctypes.byref(iosb),
                ctypes.byref(info),
                ctypes.sizeof(info),
                0x18,  # FilePipeLocalInformation
            )
            if status != 0:
                return None
            return int(info.WriteQuotaAvailable)

        _pipe_quota_probe = probe
    except Exception:
        _pipe_quota_probe = False  # Explicitly marked unavailable
    return _pipe_quota_probe or None


def _cancel_thread_io(thread) -> bool:
    """Cancel a thread's in-progress synchronous I/O (Windows CancelSynchronousIo).

    Frees a background thread stuck on a pipe write so the process can exit normally.
    Returns False on non-Windows platforms or when the cancellation fails.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenThread.restype = wintypes.HANDLE
        kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.CancelSynchronousIo.restype = wintypes.BOOL
        kernel32.CancelSynchronousIo.argtypes = [wintypes.HANDLE]
        thread_terminate = 0x0001
        handle = kernel32.OpenThread(
            thread_terminate, False, ctypes.c_ulong(thread.ident or 0)
        )
        if not handle:
            return False
        try:
            return bool(kernel32.CancelSynchronousIo(handle))
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


class _SafeStderrHandler(logging.StreamHandler):
    """Console handler that writes to stderr: writes directly only when space is
    confirmed, and hands the rest to a cancellable background write.

    - inherits StreamHandler, keeping isinstance semantics consistent with the stdlib;
    - file/console/in-memory streams: written directly, so logs are visible immediately;
    - POSIX pipes: probe the writable space first; write when it fits, drop when it does not
      (a write request never blocks);
    - Windows pipes: take the writable quota from NtQueryInformationFile (see _probe_stderr);
      when the quota cannot be probed, fall back to a background thread write and cancel a
      stuck write with a CancelSynchronousIo watchdog.
      emit (the business thread) therefore never blocks and never leaves a thread permanently
      stuck in write — otherwise the interpreter would wait for it at exit and the process
      could not terminate.
    """

    _MAX_QUEUE = 128

    def __init__(self, stream, level: int = logging.NOTSET) -> None:
        super().__init__(stream)
        self.setLevel(level)
        self._queue: "queue.Queue[str]" = queue.Queue(maxsize=self._MAX_QUEUE)
        self._writing = False
        self._write_started = 0.0
        self._closing = False
        self._blocked_until = 0.0
        self._thread = threading.Thread(
            target=self._pump, name="daofy-stderr-writer", daemon=True
        )
        self._thread.start()

    # -- Internal helpers --------------------------------------------------
    def _write_now(self, text: str) -> None:
        """Best-effort write of one chunk; every exception (full pipe/EAGAIN/cancelled/closed) is swallowed."""
        try:
            self.stream.write(text)
            self.stream.flush()
        except Exception:
            pass

    def _write_best_effort(self, text: str) -> None:
        """Write the whole record in chunks; abandon the remainder as soon as space runs out, never blocking."""
        while text:
            kind, free = _probe_stderr(self.stream)
            if kind == "unknown":
                return
            if kind == "pipe":
                if free < 0:
                    # Space unknown (Windows pipe write end): hand the whole record to one cancellable write
                    self._write_now(text)
                    return
                if free == 0:
                    return  # The client stopped reading: drop the rest; losing logs beats hanging
                chunk, text = text[:free], text[free:]
            else:
                chunk, text = text, ""
            self._write_now(chunk)

    def _pump(self) -> None:
        while True:
            if self._closing:
                return
            text = self._queue.get()
            if text is None:
                return
            if time.monotonic() < self._blocked_until:
                continue  # The pipe was just declared blocked: drop logs directly during this window
            self._writing = True
            self._write_started = time.monotonic()
            try:
                self._write_best_effort(text)
            finally:
                self._writing = False

    def _cancel_stuck_write(self, force: bool = False) -> None:
        """Cancel a write stuck too long so the thread never blocks forever (and the process cannot hang at exit)."""
        if not self._writing:
            return
        if not force and time.monotonic() - self._write_started <= _WRITE_STUCK_SECONDS:
            return
        if _cancel_thread_io(self._thread):
            self._blocked_until = time.monotonic() + _STDERR_BLOCKED_COOLDOWN

    # -- logging.Handler interface -----------------------------------------
    def emit(self, record: logging.LogRecord) -> None:
        self._cancel_stuck_write()
        try:
            text = self.format(record) + "\n"
        except Exception:
            return

        kind, free = _probe_stderr(self.stream)
        if kind == "other":
            self._write_now(text)
            return
        if kind == "pipe" and 0 < free and len(text) <= free:
            self._write_now(text)
            return
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            # The client cannot keep up, so drop logs; losing logs beats hanging the service
            pass

    def flush(self) -> None:
        # The direct-write path flushes on its own; keep this a no-op so shutdown never flushes a stuck stream
        pass

    def handleError(self, record: logging.LogRecord) -> None:
        # The default implementation would write the exception back to stderr (possibly blocking
        # or recursing again); swallow it
        pass

    def close(self) -> None:
        # Signal exit first (when the queue is full, _closing is the fallback), then
        # cancel any in-flight blocking write: Python 3.12+ waits for daemon threads
        # at exit, and a thread stuck in write would keep the process from terminating.
        self._closing = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        for _ in range(2):
            self._cancel_stuck_write(force=True)
            try:
                self._thread.join(timeout=0.5)
            except Exception:
                pass
            if not self._thread.is_alive():
                break
        # Do not call StreamHandler.close(): it would close self.stream (i.e. sys.stderr)
        # as well, breaking every later stderr write in the process.
        logging.Handler.close(self)


def setup_logger(
    name: str = "delphi_mcp",
    level: Optional[int] = None,
    log_file: Optional[str] = None,
    format_string: Optional[str] = None,
) -> logging.Logger:
    """
    Configure and return a logger.

    The handlers are also attached to the root logger so that the logs of all
    submodules (independent loggers obtained through get_logger(__name__)) are
    emitted as well.

    Args:
        name: logger name
        level: log level; read from the configuration when omitted
        log_file: log file path; the date-based file is used when omitted
        format_string: log format string

    Returns:
        the configured logger
    """
    global _root_handlers_initialized

    logger = logging.getLogger(name)
    if logger.handlers and _root_handlers_initialized:
        return logger

    if level is None:
        level = _resolve_log_level(_load_log_config().log_level)
    logger.setLevel(level)

    if format_string is None:
        format_string = _LOG_FORMAT
    formatter = logging.Formatter(format_string)

    # File handler
    file_handler: Optional[logging.FileHandler] = None
    file_logging_failed = False
    if log_file or _load_log_config().log_dir:
        if log_file:
            log_path = Path(log_file)
        else:
            log_dir = _get_project_root() / _load_log_config().log_dir
            log_path = _get_today_log_path(log_dir)

        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
        except OSError as exc:
            file_logging_failed = True
            _warn_file_logging_unavailable(log_path, exc)

    # Order matters: the file handler must be attached first. Handlers are called
    # synchronously in sequence, so once the console handler misbehaves, the file
    # log queued behind it stalls as well.
    if file_handler is not None:
        logger.addHandler(file_handler)

    if file_logging_failed:
        # File logging is best-effort.  A NullHandler prevents later log calls
        # from raising or falling back to repeated stderr output.
        logger.addHandler(logging.NullHandler())

    # Console handler (stderr, so MCP stdio is not disturbed) — off by default.
    # Output goes to the console only when the configuration sets console_logging=true;
    # otherwise every log (runtime logs included) is written to files only.
    # Decoupled from file logging: when the log directory is not writable, console
    # output explicitly requested by the user is still kept.
    # Writes go through _SafeStderrHandler: logs are dropped when the client does not
    # drain stderr, instead of hanging the service.
    if _load_log_config().console_logging:
        console_handler = _SafeStderrHandler(sys.stderr, level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # Attach the handlers to the root logger as well; otherwise records from the
    # child loggers created by get_logger(__name__) are lost when they propagate
    # to a root logger that has no handler.
    if not _root_handlers_initialized:
        root = logging.getLogger()
        # Avoid adding duplicates
        existing = {str(h) for h in root.handlers}
        for h in logger.handlers:
            if str(h) not in existing:
                root.addHandler(h)
        _root_handlers_initialized = True

    # Stop delphi_mcp from propagating up to root, or the handlers would run twice and duplicate output
    if name != "":
        logger.propagate = False

    return logger


def get_logger(name: str = "delphi_mcp") -> logging.Logger:
    """Return a logger."""
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Default logger
# ---------------------------------------------------------------------------

_default_logger: Optional[logging.Logger] = None


def init_default_logger(log_file: Optional[str] = None) -> logging.Logger:
    """
    Initialize the default logger.
    The first call automatically loads the configuration, archives old logs and
    sets up the logger.

    Note: modules obtain independent child loggers through get_logger(__name__),
    and their level is inherited from the root logger, so the root level must be
    set as well. Otherwise only the "delphi_mcp" level would be set and DEBUG logs
    from other modules would never be emitted.

    Args:
        log_file: log file path; the date-based file is used when omitted

    Returns:
        the default logger
    """
    global _default_logger, _initialized

    if _default_logger is not None and _initialized:
        return _default_logger

    # 1) Load the configuration
    config = _load_log_config()
    level = _resolve_log_level(config.log_level)

    # 2) Set the root logger level (so every module's child logger inherits the right level)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 3) Archive old logs (first call only)
    if not _initialized:
        archive_old_logs()

    # 4) Set up the logger
    if log_file is None:
        log_dir = _get_project_root() / config.log_dir
        log_file = str(_get_today_log_path(log_dir))

    _default_logger = setup_logger(log_file=log_file, level=level)
    _default_logger.info(f"Logging system initialized - level: {config.log_level}, file: {log_file}")
    _initialized = True
    return _default_logger


def get_default_logger() -> logging.Logger:
    """Return the default logger."""
    global _default_logger
    if _default_logger is None:
        _default_logger = init_default_logger()
    return _default_logger


# ---------------------------------------------------------------------------
# API call logging (controlled by a switch)
# ---------------------------------------------------------------------------

def log_api_call(logger: logging.Logger, tool_name: str, arguments: dict, result) -> None:
    """
    Record the arguments and return value of an API call.
    Only effective when log_api_calls=True.

    Args:
        logger: the logger
        tool_name: tool name
        arguments: call arguments
        result: return value
    """
    if not should_log_api_calls():
        return
    # Filter sensitive arguments (e.g. a password embedded in a path)
    # 过滤敏感参数 (如路径中的密码)
    safe_args = {}
    for k, v in arguments.items():
        if any(sensitive in k.lower() for sensitive in ("password", "secret", "token", "key")):
            safe_args[k] = "****"
        else:
            safe_args[k] = v

    try:
        args_text = json.dumps(safe_args, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        args_text = str(safe_args)
    logger.debug(">>> API call: %s | arguments: %s", tool_name, args_text)

    # Record the return value (truncated so the log stays small)
    result_str = str(result)
    if len(result_str) > 2000:
        result_str = result_str[:2000] + "... (truncated)"

    logger.debug("<<< API return: %s | result: %s", tool_name, result_str)
