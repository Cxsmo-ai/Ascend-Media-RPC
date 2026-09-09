import json
import os
import time
import threading
from typing import Dict, List
from src.core.config import get_config_path

HISTORY_FILE = os.path.join(get_config_path(), "data", "rpc_history.json")


class RPCHistory:
    """Tracks RPC activity history for local activity log."""

    def __init__(self, limit: int = 100):
        self.limit = limit
        self._lock = threading.Lock()
        self.entries: List[Dict] = []
        self._load()

    def _load(self):
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r") as f:
                    self.entries = json.load(f)
            except Exception:
                self.entries = []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            with open(HISTORY_FILE, "w") as f:
                json.dump(self.entries[-self.limit:], f, indent=2)
        except Exception:
            pass

    def add(self, details: str, state: str, image_url: str = "",
            activity_type: str = "watching"):
        entry = {
            "timestamp": int(time.time()),
            "details": details,
            "state": state,
            "image_url": image_url,
            "activity_type": activity_type,
        }
        with self._lock:
            if self.entries and self.entries[-1].get("details") == details:
                return
            self.entries.append(entry)
            if len(self.entries) > self.limit:
                self.entries = self.entries[-self.limit:]
            self._save()

    def get_all(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            return list(reversed(self.entries[-limit:]))

    def clear(self):
        with self._lock:
            self.entries = []
            self._save()
