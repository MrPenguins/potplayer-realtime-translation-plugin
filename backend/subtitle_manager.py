"""
Subtitle lifecycle manager.

Handles timestamped subtitle storage, automatic expiry of stale subtitles,
and playback-state-aware reset.
"""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class SubtitleEntry:
    """A single subtitle with timing metadata."""

    def __init__(self, text: str, timestamp: Optional[float] = None):
        self.text = text
        self.timestamp = timestamp or time.time()
        self.expires_at = self.timestamp  # will be set by SubtitleManager


class SubtitleManager:
    """
    Thread-safe subtitle storage with automatic expiry.

    Usage:
        mgr = SubtitleManager(max_idle_seconds=3.0)
        mgr.update("Hello world")          # store a new subtitle
        current = mgr.get_current()        # get current or None if expired
        mgr.reset()                        # clear everything (playback stop/skip)
    """

    def __init__(self, max_idle_seconds: float = 3.0):
        """
        Args:
            max_idle_seconds: seconds without update before subtitle is considered stale.
        """
        self._max_idle = max_idle_seconds
        self._current: Optional[SubtitleEntry] = None
        self._lock = threading.Lock()
        logger.info(f"SubtitleManager initialized (max_idle={max_idle_seconds}s)")

    def update(self, text: str) -> None:
        """
        Store a new subtitle text. Resets the expiry timer.

        Args:
            text: the subtitle text. Empty string or whitespace-only is treated
                  as a clear signal (current subtitle is removed).
        """
        if not text or not text.strip():
            with self._lock:
                self._current = None
            return

        entry = SubtitleEntry(text.strip())
        entry.expires_at = entry.timestamp + self._max_idle

        with self._lock:
            self._current = entry

        logger.debug(f"Subtitle updated: '{text[:60]}{'...' if len(text) > 60 else ''}'")

    def get_current(self) -> Optional[str]:
        """
        Get the current subtitle text, or None if expired/empty.

        Once the subtitle expires (no update for max_idle_seconds),
        it is cleared and None is returned.
        """
        with self._lock:
            entry = self._current
            if entry is None:
                return None

            # Check expiry
            if time.time() > entry.expires_at:
                self._current = None
                logger.debug("Subtitle expired and cleared.")
                return None

            return entry.text

    def reset(self) -> None:
        """
        Reset all state. Called on playback stop, skip, or pause.

        Clears current subtitle and any internal state.
        """
        with self._lock:
            self._current = None
        logger.debug("SubtitleManager reset (playback state change).")

    @property
    def max_idle_seconds(self) -> float:
        return self._max_idle

    @max_idle_seconds.setter
    def max_idle_seconds(self, value: float) -> None:
        self._max_idle = max(0.5, value)
        logger.info(f"Subtitle max_idle_seconds updated to {self._max_idle}s")
