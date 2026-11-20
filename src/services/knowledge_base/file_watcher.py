"""
File change watcher — monitors Delphi source changes and automatically triggers incremental KB updates

Copyright (C) Jilin Left-Right Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (Dark Night Killer QQ:281309196)

Dependency: watchdog (pip install watchdog)
If watchdog is not installed, the watcher silently degrades and does not affect other functionality.
"""

import os
import threading
import time as _time
from pathlib import Path
from typing import Callable, Iterable, Optional, Set

from src.constants import SOURCE_SCAN_EXCLUDED_DIRS, TIMEOUT_PROCESS_TERMINATE
from src.services.delphi_edit_guard import record_external_edit
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Delphi file extensions to watch
DELPHI_EXTENSIONS: Set[str] = {
    '.pas', '.dpr', '.dpk', '.dfm', '.fmx', '.inc', '.dproj', '.groupproj',
}

# Directory names to skip (no need to watch)
SKIP_DIR_NAMES: Set[str] = set(SOURCE_SCAN_EXCLUDED_DIRS)


# ──────────────────────────────────────────────────────────
# DelphiFileHandler — watchdog event handler (with debounce)
# ──────────────────────────────────────────────────────────


class _DelphiFileHandler:
    """watchdog file event handler that filters Delphi source changes and triggers after debounce.

    Args:
        on_change: Callback triggered after debounce ends (called in the watchdog thread)
        debounce_seconds: Debounce wait seconds, default 3 seconds
    """

    def __init__(
        self,
        on_change: Callable[[Set[str]], None],
        debounce_seconds: float = 3.0,
    ):
        self.on_change = on_change
        self.debounce_seconds = debounce_seconds
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._pending_paths: Set[str] = set()

    def dispatch(self, event) -> None:
        """watchdog event dispatch entry point—compatible with watchdog's FileSystemEventHandler convention."""
        if event.is_directory:
            return
        ext = Path(event.src_path).suffix.lower()
        if ext in DELPHI_EXTENSIONS:
            self._debounce(event.src_path)

    def _debounce(self, file_path: str) -> None:
        """Reset the debounce timer: consecutive changes trigger the callback only once."""
        with self._lock:
            self._pending_paths.add(file_path)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_seconds, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            pending_paths = set(self._pending_paths)
            self._pending_paths.clear()
            self._timer = None
        try:
            self.on_change(pending_paths)
        except Exception as e:
            logger.error("File change callback execution failed: %s", e, exc_info=True)

    def stop(self) -> None:
        """Cancel the pending debounce timer."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending_paths.clear()


# ──────────────────────────────────────────────────────────
# ProjectFileWatcher
# ──────────────────────────────────────────────────────────


class ProjectFileWatcher:
    """Project file watcher: monitors Delphi source changes and automatically triggers incremental KB updates.

    Checks whether watchdog is available at startup, and silently degrades when unavailable.
    Submits background build tasks via AsyncTaskManager, with built-in deduplication to prevent stacking.
    Includes a watchdog timer that checks Observer thread health and automatically restarts it after a crash.

    Args:
        project_path: Project .dproj file path
        project_dir: Project root directory (used for file watch scope)
    """

    # Watchdog check interval (seconds)
    _HEALTH_CHECK_INTERVAL: float = 60.0

    def __init__(self, project_path: str, project_dir: str):
        self._project_path = project_path
        self._project_dir = project_dir
        self._observer: Optional[object] = None
        self._handler: Optional[_DelphiFileHandler] = None
        self._watchdog_available = False
        self._health_timer: Optional[threading.Timer] = None

    def start(self) -> bool:
        """Start file watching. Returns True for successful start, False for degraded mode.

        Degraded reasons: watchdog not installed, project directory does not exist, Observer creation failed.
        """
        # ── Check watchdog availability ──
        try:
            from watchdog.observers import Observer  # noqa: F401
            self._watchdog_available = True
        except ImportError:
            logger.info(
                "watchdog is not installed; file change watching skipped. "
                "For automatic incremental KB updates: pip install watchdog"
            )
            return False

        project_dir = Path(self._project_dir)
        if not project_dir.is_dir():
            logger.warning("Project directory does not exist; cannot start file watching: %s", project_dir)
            return False

        # ── Create debounce handler ──
        self._handler = _DelphiFileHandler(self._on_change, debounce_seconds=3.0)

        # ── Start Observer ──
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEvent

            self._observer = Observer()
            # watchdog requires the handler to implement a specific interface,
            # use a wrapper to call dispatch
            class _WatchdogHandler:
                def __init__(self, handler: _DelphiFileHandler):
                    self._handler = handler

                def dispatch(self, event: FileSystemEvent) -> None:
                    self._handler.dispatch(event)

            watchdog_handler = _WatchdogHandler(self._handler)
            self._observer.schedule(
                watchdog_handler, str(project_dir), recursive=True
            )
            self._observer.daemon = True
            self._observer.start()
            self._start_health_check()
            logger.info("File change watching started: %s", project_dir)
            return True

        except Exception as e:
            logger.warning("File watching failed to start: %s", e)
            return False

    def _start_health_check(self) -> None:
        """Start the watchdog timer to periodically check whether the Observer thread is alive."""
        def _check():
            if self._observer is None:
                return
            try:
                alive = getattr(self._observer, 'is_alive', lambda: True)()
                if not alive:
                    logger.warning("File watching Observer thread has terminated; restarting...")
                    project_dir = self._project_dir
                    self._observer = self._rebuild_observer()
                    if self._observer:
                        self._observer.start()
                        logger.info("File watching Observer restarted: %s", project_dir)
            except Exception as e:
                logger.debug("File watching health check exception: %s", e)

        def _schedule():
            if self._observer is not None:
                self._health_timer = threading.Timer(
                    self._HEALTH_CHECK_INTERVAL, _schedule
                )
                self._health_timer.daemon = True
                self._health_timer.start()
                _check()

        _schedule()

    def _rebuild_observer(self):
        """Rebuild the Observer instance (called when health check detects a crash)."""
        try:
            from watchdog.observers import Observer
            obs = Observer()
            class _WatchdogHandler:
                def __init__(self, handler):
                    self._handler = handler
                def dispatch(self, event):
                    self._handler.dispatch(event)
            if self._handler:
                obs.schedule(
                    _WatchdogHandler(self._handler),
                    str(Path(self._project_dir)),
                    recursive=True,
                )
            obs.daemon = True
            logger.info("Observer instance rebuilt")
            return obs
        except Exception as e:
            logger.warning("Failed to rebuild Observer: %s", e)
            return None

    def stop(self) -> None:
        """Stop file watching and clean up resources."""
        # Stop watchdog
        if self._health_timer is not None:
            self._health_timer.cancel()
            self._health_timer = None

        if self._handler is not None:
            self._handler.stop()
            self._handler = None

        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=TIMEOUT_PROCESS_TERMINATE)
            except Exception as e:
                logger.debug("Non-fatal error while stopping file watching: %s", e)
            self._observer = None
            logger.info("File change watching stopped")

    def _on_change(self, changed_paths: Optional[Iterable[str]] = None) -> None:
        """File change trigger: submit an incremental KB build task via AsyncTaskManager (deduplicated)."""
        for file_path in changed_paths or ():
            record_external_edit(file_path, event_type="modified")

        try:
            from src.services.knowledge_base.async_task_manager import (
                get_task_manager,
            )
            from src.services.knowledge_base.project_knowledge_base import (
                ProjectKnowledgeBase,
            )

            task_mgr = get_task_manager()
            dedup_key = f"file_watcher_rebuild_{self._project_path}"

            def rebuild_task(**kwargs: str) -> bool:
                """Build KB incrementally in the background."""
                pp = kwargs.get("project_path", self._project_path)
                pkb = ProjectKnowledgeBase(pp, progress_callback=kwargs.get("_progress_callback"))
                return pkb.build_project_knowledge_base(rebuild=False)

            task_id = task_mgr.submit_task(
                name=f"Automatic incremental update on file change ({Path(self._project_path).stem})",
                func=rebuild_task,
                project_path=self._project_path,
                dedup_key=dedup_key,
            )
            logger.debug("File change triggered incremental KB update: task_id=%s", task_id)

        except Exception as e:
            logger.error("Failed to trigger incremental KB update: %s", e, exc_info=True)