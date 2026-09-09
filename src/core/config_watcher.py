import os
import time
import threading
import logging
from typing import Callable, Optional

logger = logging.getLogger("stremio-rpc")


class ConfigWatcher:
    """Watches config.json for external changes and triggers reload."""

    def __init__(self, config_path: str, on_change: Callable, interval: float = 2.0):
        self.config_path = config_path
        self.on_change = on_change
        self.interval = interval
        self._last_mtime: Optional[float] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._last_mtime = self._get_mtime()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info("Config watcher started")

    def stop(self):
        self._running = False

    def _get_mtime(self) -> Optional[float]:
        try:
            return os.path.getmtime(self.config_path)
        except OSError:
            return None

    def _watch_loop(self):
        while self._running:
            try:
                current_mtime = self._get_mtime()
                if current_mtime and current_mtime != self._last_mtime:
                    self._last_mtime = current_mtime
                    logger.info("Config file changed externally, reloading...")
                    try:
                        self.on_change()
                    except Exception as e:
                        logger.error(f"Config reload callback failed: {e}")
            except Exception:
                pass
            time.sleep(self.interval)
