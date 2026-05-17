import json
import os
import time
import threading
from typing import Dict, List, Optional
from src.core.config import get_config_path

AUDIT_FILE = os.path.join(get_config_path(), "data", "audit_log.json")


class AuditLog:
    """Tracks configuration changes, API key updates, and auth events."""

    def __init__(self, max_entries: int = 1000):
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self.entries: List[Dict] = []
        self._load()

    def _load(self):
        os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
        if os.path.exists(AUDIT_FILE):
            try:
                with open(AUDIT_FILE, "r") as f:
                    self.entries = json.load(f)
            except Exception:
                self.entries = []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
            with open(AUDIT_FILE, "w") as f:
                json.dump(self.entries[-self.max_entries:], f, indent=2)
        except Exception:
            pass

    def log(self, event_type: str, details: Optional[Dict] = None, source: str = "system"):
        entry = {
            "timestamp": int(time.time()),
            "type": event_type,
            "source": source,
            "details": details or {},
        }
        with self._lock:
            self.entries.append(entry)
            if len(self.entries) > self.max_entries:
                self.entries = self.entries[-self.max_entries:]
            self._save()

    def log_config_change(self, key: str, old_value, new_value, source: str = "dashboard"):
        sensitive_keys = {
            "trakt_access_token", "trakt_refresh_token", "trakt_client_secret",
            "nuvio_covers_password", "nuvio_covers_token", "dashboard_auth_pin",
            "opensubtitles_password", "lastfm_session_key", "anilist_access_token",
            "simkl_access_token", "kitsu_access_token", "plex_token",
            "notion_api_key", "jellyfin_api_key", "emby_api_key",
        }
        if key in sensitive_keys:
            old_value = "****" if old_value else "(empty)"
            new_value = "****" if new_value else "(empty)"
        self.log("config_change", {
            "key": key,
            "old_value": old_value,
            "new_value": new_value,
        }, source=source)

    def log_auth_event(self, service: str, action: str, success: bool = True):
        self.log("auth_event", {
            "service": service,
            "action": action,
            "success": success,
        })

    def log_api_key_update(self, service: str, valid: bool):
        self.log("api_key_update", {
            "service": service,
            "valid": valid,
        })

    def get_entries(self, limit: int = 100, event_type: Optional[str] = None) -> List[Dict]:
        with self._lock:
            filtered = self.entries
            if event_type:
                filtered = [e for e in filtered if e.get("type") == event_type]
            return list(reversed(filtered[-limit:]))
