import logging
import requests
from typing import Dict, Optional, List

logger = logging.getLogger("stremio-rpc")


class LetterboxdClient:
    """Letterboxd API integration for film logging and ratings."""

    BASE_URL = "https://api.letterboxd.com/api/v0"

    def __init__(self, api_key: str = "", api_secret: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret

    def _params(self) -> Dict:
        return {"apikey": self.api_key} if self.api_key else {}

    def search_film(self, title: str, year: Optional[int] = None) -> Optional[Dict]:
        if not self.api_key:
            return None
        try:
            params = self._params()
            params["input"] = title
            params["include"] = "FilmSearchItem"
            if year:
                params["decade"] = (year // 10) * 10
            r = requests.get(
                f"{self.BASE_URL}/search",
                params=params,
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", [])
                if items:
                    return items[0].get("film")
            logger.warning(f"Letterboxd search failed: {r.status_code}")
        except Exception as e:
            logger.error(f"Letterboxd search error: {e}")
        return None

    def get_film(self, film_id: str) -> Optional[Dict]:
        if not self.api_key:
            return None
        try:
            r = requests.get(
                f"{self.BASE_URL}/film/{film_id}",
                params=self._params(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            logger.error(f"Letterboxd film fetch error: {e}")
        return None

    def get_film_statistics(self, film_id: str) -> Optional[Dict]:
        if not self.api_key:
            return None
        try:
            r = requests.get(
                f"{self.BASE_URL}/film/{film_id}/statistics",
                params=self._params(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            logger.error(f"Letterboxd stats error: {e}")
        return None
