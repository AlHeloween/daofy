"""
Asynchronous task manager

Copyright (C) Jilin Left-Right Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (Dark Night Killer QQ:281309196)

Manages long-running background tasks
"""

import asyncio
import threading
import time
from enum import Enum
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime

from ...utils.logger import get_logger

logger = get_logger(__name__)


class CancelledError(Exception):
    """Task cancellation exception—thrown by _cancellation_check and caught by run_task"""
    pass


class TaskStatus(Enum):
    """Task status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    """Task information"""
    task_id: str
    name: str
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: float = 0.0
    message: str = ""
    result: Any = None
    error: Optional[str] = None
    # Added: deduplication key (optional)
    _dedup_key: Optional[str] = None
    # Added: step information
    current_step: str = ""  # Current step name
    total_steps: int = 0    # Total number of steps
    step_index: int = 0     # Current step index (starting from 1)


class AsyncTaskManager:
    """Asynchronous task manager"""

    def __init__(self):
        self._tasks: Dict[str, TaskInfo] = {}
        self._task_threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._progress_condition = threading.Condition(self._lock)
        self._task_counter = 0

    def _generate_task_id(self) -> str:
        """Generate task ID"""
        with self._lock:
            self._task_counter += 1
            return f"task_{int(time.time())}_{self._task_counter}"

    def find_running_task_by_key(self, dedup_key: str) -> Optional[str]:
        """
        Find whether a running or pending dedup task exists

        Args:
            dedup_key: Deduplication key

        Returns:
            task_id of the existing task, or None
        """
        with self._lock:
            for tid, info in self._tasks.items():
                if info.status in (TaskStatus.RUNNING, TaskStatus.PENDING):
                    stored_key = getattr(info, '_dedup_key', None)
                    if stored_key == dedup_key:
                        return tid
        return None

    def submit_task(self, name: str, func: Callable, *args,
                    progress_callback: Optional[Callable] = None,
                    dedup_key: Optional[str] = None,
                    on_complete: Optional[Callable[..., None]] = None,
                    **kwargs) -> str:
        """
        Submit a background task

        Args:
            name: Task name
            func: Task function
            *args: Positional arguments for the task function
            progress_callback: Progress callback function
            dedup_key: Deduplication key. When a task with the same key is already running/pending, return the existing task_id
            **kwargs: Keyword arguments for the task function

        Returns:
            Task ID
        """
        # Re-entry check: if a task with the same dedup_key is already running, reuse task_id
        if dedup_key is not None:
            existing = self.find_running_task_by_key(dedup_key)
            if existing is not None:
                logger.info(f"Reusing existing task task_id={existing} (dedup_key={dedup_key})")
                return existing

        task_id = self._generate_task_id()

        task_info = TaskInfo(
            task_id=task_id,
            name=name,
            status=TaskStatus.PENDING,
            created_at=datetime.now()
        )
        task_info._dedup_key = dedup_key

        with self._lock:
            self._tasks[task_id] = task_info

        def run_task():
            try:
                with self._lock:
                    task_info.status = TaskStatus.RUNNING
                    task_info.started_at = datetime.now()
                    task_info.message = "Task is running..."

                logger.info(f"Task {task_id} ({name}) started")

                # Create a progress update function—embed cancellation check in the callback so downstream code needs no changes
                def update_progress(*args, **kwargs):
                    # Handle different callback signatures:
                    # 1. ProgressInfo object (from ProgressTracker) — has .percentage
                    # 2. (percent, message) or (percent, message, extra_dict) — standard
                    
                    if args and hasattr(args[0], 'percentage'):
                        # Case 1: ProgressInfo object
                        pct = args[0].percentage
                        msg = args[0].message
                    elif args and isinstance(args[0], (int, float)):
                        # Case 2: (percent, message, extra_dict?)
                        pct = float(args[0])
                        msg = str(args[1]) if len(args) > 1 else kwargs.get('message', '')
                    else:
                        pct = 0
                        msg = str(args) if args else ''
                    
                    # Embed cancellation check in every progress callback
                    if self.is_task_cancelled(task_id):
                        raise CancelledError(f"Task {task_id} ({name}) cancelled")
                    
                    logger.debug(f"Progress update: {pct}% - {msg}")
                    self.update_task_progress(task_id, pct, msg)

                # Create cancellation check function—task function calls it at loop boundaries to respond to cancellation
                def _cancellation_check():
                    """Check whether the task is cancelled; throw CancelledError when cancelled"""
                    if self.is_task_cancelled(task_id):
                        raise CancelledError(f"Task {task_id} ({name}) cancelled")

                # Pass progress callback, cancellation check, and task ID to the task function
                kwargs['_progress_callback'] = update_progress
                kwargs['_cancellation_check'] = _cancellation_check
                kwargs['_task_id'] = task_id

                result = func(*args, **kwargs)

                with self._lock:
                    task_info.status = TaskStatus.COMPLETED
                    task_info.completed_at = datetime.now()
                    task_info.progress = 100.0
                    task_info.message = "Task completed"
                    task_info.result = result

                logger.info(f"Task {task_id} ({name}) completed")

                # Trigger completion callback (for MCP push notifications)
                if on_complete:
                    try:
                        on_complete(task_info)
                    except Exception as cb_err:
                        logger.error(f"Task {task_id} completion callback failed: {cb_err}")

            except CancelledError as e:
                logger.info(f"Task {task_id} ({name}) cancelled")
                with self._lock:
                    task_info.status = TaskStatus.CANCELLED
                    task_info.completed_at = datetime.now()
                    task_info.message = str(e)
                if on_complete:
                    try:
                        on_complete(task_info)
                    except Exception as cb_err:
                        logger.error(f"Task {task_id} cancellation callback failed: {cb_err}")

            except Exception as e:
                logger.error(f"Task {task_id} ({name}) failed: {e}", exc_info=True)
                with self._lock:
                    task_info.status = TaskStatus.FAILED
                    task_info.completed_at = datetime.now()
                    task_info.error = str(e)
                    task_info.message = f"Task failed: {str(e)}"
                if on_complete:
                    try:
                        on_complete(task_info)
                    except Exception as cb_err:
                        logger.error(f"Task {task_id} failure callback failed: {cb_err}")

            finally:
                # Clean up thread reference
                with self._lock:
                    if task_id in self._task_threads:
                        del self._task_threads[task_id]

        # Start background thread
        thread = threading.Thread(target=run_task, daemon=True)
        with self._lock:
            self._task_threads[task_id] = thread

        thread.start()
        logger.info(f"Task {task_id} ({name}) submitted to background")

        return task_id

    def get_task_info(self, task_id: str) -> Optional[TaskInfo]:
        """Get task information"""
        with self._lock:
            return self._tasks.get(task_id)

    def wait_for_progress_change(self, task_id: str, timeout_seconds: float = 120) -> Optional[TaskInfo]:
        """Long-poll until task progress changes
        
        Block until progress changes, the task completes/fails/is cancelled, or timeout.
        
        Args:
            task_id: Task ID
            timeout_seconds: Maximum wait seconds (default 120)
        
        Returns:
            Changed TaskInfo, or None (task does not exist)
        """
        deadline = time.time() + timeout_seconds
        with self._progress_condition:
            while time.time() < deadline:
                task = self._tasks.get(task_id)
                if not task:
                    return None
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    return task
                old_progress = task.progress
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._progress_condition.wait(timeout=min(30.0, remaining))
                task = self._tasks.get(task_id)
                if task and task.progress != old_progress:
                    return task  # Progress changed, return immediately
            return self._tasks.get(task_id)  # Timeout: return current status

    def get_all_tasks(self) -> Dict[str, TaskInfo]:
        """Get all tasks"""
        with self._lock:
            return dict(self._tasks)

    def update_task_progress(self, task_id: str, progress: float, message: str = "",
                            current_step: str = "", step_index: int = 0, total_steps: int = 0):
        """Update task progress (notify all waiting long polls)"""
        with self._lock:
            if task_id in self._tasks:
                old_progress = self._tasks[task_id].progress
                # Always update progress
                self._tasks[task_id].progress = min(100.0, max(0.0, progress))
                # Always update message (even if empty to show current status)
                self._tasks[task_id].message = message
                if current_step:
                    self._tasks[task_id].current_step = current_step
                if step_index > 0:
                    self._tasks[task_id].step_index = step_index
                if total_steps > 0:
                    self._tasks[task_id].total_steps = total_steps
                # Notify waiting long polls when progress changes
                if progress != old_progress:
                    self._progress_condition.notify_all()

    def cancel_task(self, task_id: str) -> bool:
        """Cancel task (only effective for tasks that support cancellation)"""
        with self._lock:
            if task_id not in self._tasks:
                return False

            task_info = self._tasks[task_id]
            if task_info.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                return False

            task_info.status = TaskStatus.CANCELLED
            task_info.message = "Task cancelled"
            task_info.completed_at = datetime.now()

            # Notify wait_for_progress_change long polls to return immediately
            self._progress_condition.notify_all()

            # Note: threads cannot be forcibly terminated; _cancellation_check responds within the task function
            return True

    def is_task_cancelled(self, task_id: str) -> bool:
        """Check whether the task has been cancelled"""
        with self._lock:
            if task_id in self._tasks:
                return self._tasks[task_id].status == TaskStatus.CANCELLED
            return False

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Clean up old tasks"""
        cutoff = datetime.now().timestamp() - (max_age_hours * 3600)

        with self._lock:
            to_remove = []
            for task_id, task_info in self._tasks.items():
                if task_info.created_at.timestamp() < cutoff:
                    to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]
                logger.debug(f"Cleaning up old task: {task_id}")


# Global task manager instance
_task_manager: Optional[AsyncTaskManager] = None


def get_task_manager() -> AsyncTaskManager:
    """Get the global task manager instance"""
    global _task_manager
    if _task_manager is None:
        _task_manager = AsyncTaskManager()
    return _task_manager

