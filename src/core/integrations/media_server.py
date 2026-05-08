import logging
import requests
from typing import Dict, Optional, List

logger = logging.getLogger("stremio-rpc")


class PlexClient:
    """Plex Media Server companion integration."""

    def __init__(self, url: str = "", token: str = ""):
        self.url = url.rstrip("/")
        self.token = token

    def _headers(self) -> Dict:
        return {
            "X-Plex-Token": self.token,
            "Accept": "application/json",
        }

    def get_sessions(self) -> List[Dict]:
        if not self.url or not self.token:
            return []
        try:
            r = requests.get(
                f"{self.url}/status/sessions",
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("MediaContainer", {}).get("Metadata", [])
        except Exception as e:
            logger.error(f"Plex sessions error: {e}")
        return []

    def get_now_playing(self) -> Optional[Dict]:
        sessions = self.get_sessions()
        return sessions[0] if sessions else None

    def get_libraries(self) -> List[Dict]:
        if not self.url or not self.token:
            return []
        try:
            r = requests.get(
                f"{self.url}/library/sections",
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json().get("MediaContainer", {}).get("Directory", [])
        except Exception as e:
            logger.error(f"Plex libraries error: {e}")
        return []


class JellyfinClient:
    """Jellyfin/Emby media server companion integration."""

    def __init__(self, url: str = "", api_key: str = "", server_type: str = "jellyfin"):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.server_type = server_type

    def _headers(self) -> Dict:
        if self.server_type == "emby":
            return {"X-Emby-Token": self.api_key}
        return {"Authorization": f'MediaBrowser Token="{self.api_key}"'}

    def get_sessions(self) -> List[Dict]:
        if not self.url or not self.api_key:
            return []
        try:
            r = requests.get(
                f"{self.url}/Sessions",
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                sessions = r.json()
                return [s for s in sessions if s.get("NowPlayingItem")]
        except Exception as e:
            logger.error(f"{self.server_type.title()} sessions error: {e}")
        return []

    def get_now_playing(self) -> Optional[Dict]:
        sessions = self.get_sessions()
        if sessions:
            return sessions[0].get("NowPlayingItem")
        return None

    def get_libraries(self) -> List[Dict]:
        if not self.url or not self.api_key:
            return []
        try:
            r = requests.get(
                f"{self.url}/Library/VirtualFolders",
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            logger.error(f"{self.server_type.title()} libraries error: {e}")
        return []
