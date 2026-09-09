import hashlib
import logging
import time
import requests
from typing import Dict, Optional

logger = logging.getLogger("stremio-rpc")


class LastFMClient:
    """Last.fm API integration for music scrobbling."""

    BASE_URL = "https://ws.audioscrobbler.com/2.0/"

    def __init__(self, api_key: str = "", api_secret: str = "", session_key: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session_key = session_key

    def _sign(self, params: Dict) -> str:
        sorted_params = sorted(params.items())
        param_str = "".join(f"{k}{v}" for k, v in sorted_params)
        param_str += self.api_secret
        return hashlib.md5(param_str.encode("utf-8")).hexdigest()

    def _call(self, method: str, params: Dict, post: bool = False) -> Optional[Dict]:
        params["method"] = method
        params["api_key"] = self.api_key
        params["format"] = "json"

        if post and self.session_key:
            params["sk"] = self.session_key
            params.pop("format", None)
            params["api_sig"] = self._sign(params)
            params["format"] = "json"

        try:
            if post:
                r = requests.post(self.BASE_URL, data=params, timeout=10)
            else:
                r = requests.get(self.BASE_URL, params=params, timeout=10)
            if r.status_code == 200:
                return r.json()
            logger.warning(f"Last.fm {method} failed: {r.status_code}")
        except Exception as e:
            logger.error(f"Last.fm {method} error: {e}")
        return None

    def get_auth_token(self) -> Optional[str]:
        result = self._call("auth.getToken", {})
        return result.get("token") if result else None

    def get_session(self, token: str) -> Optional[str]:
        params = {"token": token}
        params["api_sig"] = self._sign({"method": "auth.getSession", "api_key": self.api_key, "token": token})
        result = self._call("auth.getSession", params)
        if result and "session" in result:
            self.session_key = result["session"]["key"]
            return self.session_key
        return None

    def scrobble(self, artist: str, track: str, album: str = "",
                 timestamp: Optional[int] = None) -> bool:
        if not self.session_key:
            return False
        params = {
            "artist": artist,
            "track": track,
            "timestamp": str(timestamp or int(time.time())),
        }
        if album:
            params["album"] = album
        result = self._call("track.scrobble", params, post=True)
        if result and "scrobbles" in result:
            logger.info(f"Last.fm scrobble: {artist} - {track}")
            return True
        return False

    def update_now_playing(self, artist: str, track: str, album: str = "") -> bool:
        if not self.session_key:
            return False
        params = {"artist": artist, "track": track}
        if album:
            params["album"] = album
        result = self._call("track.updateNowPlaying", params, post=True)
        return result is not None

    def search_track(self, query: str, limit: int = 5) -> list:
        result = self._call("track.search", {"track": query, "limit": str(limit)})
        if result:
            return result.get("results", {}).get("trackmatches", {}).get("track", [])
        return []
