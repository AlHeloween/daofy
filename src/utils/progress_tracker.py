#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Progress tracker

Progress tracking and feedback for long-running tasks.
"""

import time
from typing import Callable, Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class ProgressInfo:
    """Progress information"""
    current: int  # Current progress
    total: int  # Total count
    message: str  # Current status message
    percentage: float  # Percentage (0-100)
    elapsed_time: float  # Elapsed time (seconds)
    estimated_remaining: float  # Estimated remaining time (seconds)
    speed: float  # Processing speed (items/second)


class ProgressTracker:
    """Progress tracker"""

    def __init__(
        self,
        total: int,
        callback: Optional[Callable[[ProgressInfo], None]] = None,
        update_interval: float = 1.0
    ):
        """
        Initialize the progress tracker.

        Args:
            total: Total number of items
            callback: Progress callback function
            update_interval: Update interval (seconds)
        """
        self.total = total
        self.current = 0
        self.callback = callback
        self.update_interval = update_interval

        self.start_time = time.time()
        self.last_update_time = 0
        self.last_update_count = 0

    def update(self, increment: int = 1, message: str = ""):
        """
        Update progress.

        Args:
            increment: Increment
            message: Status message
        """
        self.current += increment
        current_time = time.time()

        # Check whether an update is due (based on the time interval)
        if current_time - self.last_update_time >= self.update_interval:
            self._notify_progress(message)
            self.last_update_time = current_time
            self.last_update_count = self.current

    def _notify_progress(self, message: str = ""):
        """Notify a progress update"""
        if not self.callback:
            return

        elapsed_time = time.time() - self.start_time
        percentage = (self.current / self.total * 100) if self.total > 0 else 0

        # Compute the processing speed
        if elapsed_time > 0:
            speed = self.current / elapsed_time
        else:
            speed = 0

        # Estimate the remaining time
        if speed > 0 and self.current < self.total:
            remaining_items = self.total - self.current
            estimated_remaining = remaining_items / speed
        else:
            estimated_remaining = 0

        progress_info = ProgressInfo(
            current=self.current,
            total=self.total,
            message=message or f"Processing... ({self.current}/{self.total})",
            percentage=percentage,
            elapsed_time=elapsed_time,
            estimated_remaining=estimated_remaining,
            speed=speed
        )

        self.callback(progress_info)

    def finish(self, message: str = "Done"):
        """
        Finish progress tracking.

        Args:
            message: Completion message
        """
        self.current = self.total
        self._notify_progress(message)

    def get_progress_text(self, progress: ProgressInfo) -> str:
        """
        Get the formatted progress text.

        Args:
            progress: Progress information

        Returns:
            Formatted progress text
        """
        elapsed = self._format_time(progress.elapsed_time)
        remaining = self._format_time(progress.estimated_remaining)

        text = (
            f"Progress: {progress.current}/{progress.total} "
            f"({progress.percentage:.1f}%) | "
            f"Speed: {progress.speed:.1f} items/s | "
            f"Elapsed: {elapsed} | "
            f"Remaining: {remaining} | "
            f"{progress.message}"
        )

        return text

    def _format_time(self, seconds: float) -> str:
        """Format a duration"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f} min"
        else:
            hours = seconds / 3600
            return f"{hours:.1f} h"
