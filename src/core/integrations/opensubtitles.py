import logging
import requests
from typing import Dict, Optional, List

logger = logging.getLogger("stremio-rpc")


class OpenSubtitlesClient:
    """OpenSubtitles.com API v1 integration for subtitle availability."""

    BASE_URL = "https://api.opensubtitles.com/api/v1"

    def __init__(self, api_key: str = "", username: str = "", password: str = ""):
        self.api_key = api_key
        self.username = username
        self.password = password
        self._token: Optional[str] = None

    def _headers(self) -> Dict:
        headers = {"Api-Key": self.api_key, "Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def login(self) -> bool:
        if not self.api_key or not self.username or not self.password:
            return False
        try:
            r = requests.post(
                f"{self.BASE_URL}/login",
                json={"username": self.username, "password": self.password},
                headers={"Api-Key": self.api_key, "Content-Type": "application/json"},
                timeout=10,
            )
            if r.status_code == 200:
                self._token = r.json().get("token")
                logger.info("OpenSubtitles login successful")
                return True
            logger.warning(f"OpenSubtitles login failed: {r.status_code}")
        except Exception as e:
            logger.error(f"OpenSubtitles login error: {e}")
        return False

    def search(self, imdb_id: str = "", query: str = "",
               season: int = 0, episode: int = 0,
               languages: str = "en") -> List[Dict]:
        if not self.api_key:
            return []
        try:
            params = {"languages": languages}
            if imdb_id:
                params["imdb_id"] = imdb_id.lstrip("t")
            elif query:
                params["query"] = query
            if season:
                params["season_number"] = season
            if episode:
                params["episode_number"] = episode

            r = requests.get(
                f"{self.BASE_URL}/subtitles",
                params=params,
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("data", [])
            logger.warning(f"OpenSubtitles search failed: {r.status_code}")
        except Exception as e:
            logger.error(f"OpenSubtitles search error: {e}")
        return []

    def get_subtitle_languages(self, imdb_id: str, season: int = 0,
                               episode: int = 0) -> List[str]:
        results = self.search(imdb_id=imdb_id, season=season, episode=episode, languages="")
        languages = set()
        for sub in results:
            attrs = sub.get("attributes", {})
            lang = attrs.get("language", "")
            if lang:
                languages.add(lang)
        return sorted(languages)

    def get_download_link(self, file_id: int) -> Optional[str]:
        if not self.api_key:
            return None
        try:
            r = requests.post(
                f"{self.BASE_URL}/download",
                json={"file_id": file_id},
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json().get("link")
        except Exception as e:
            logger.error(f"OpenSubtitles download error: {e}")
        return None
