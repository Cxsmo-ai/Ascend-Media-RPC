import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger("stremio-rpc")


class SimklClient:
    """Simkl API integration for scrobbling and tracking."""

    BASE_URL = "https://api.simkl.com"

    def __init__(self, client_id: str = "", access_token: str = ""):
        self.client_id = client_id
        self.access_token = access_token

    def _headers(self) -> Dict:
        headers = {
            "Content-Type": "application/json",
            "simkl-api-key": self.client_id,
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def search(self, title: str, media_type: str = "movie") -> Optional[Dict]:
        try:
            r = requests.get(
                f"{self.BASE_URL}/search/{media_type}",
                params={"q": title},
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                results = r.json()
                return results[0] if results else None
        except Exception as e:
            logger.error(f"Simkl search error: {e}")
        return None

    def scrobble(self, media_data: Dict, progress: float) -> bool:
        if not self.access_token:
            return False
        try:
            payload = {"progress": progress}
            if "movie" in media_data:
                payload["movie"] = media_data["movie"]
            elif "show" in media_data:
                payload["show"] = media_data["show"]
                if "episode" in media_data:
                    payload["episode"] = media_data["episode"]

            r = requests.post(
                f"{self.BASE_URL}/sync/history",
                json=payload,
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code in (200, 201):
                logger.info("Simkl scrobble successful")
                return True
            logger.warning(f"Simkl scrobble failed: {r.status_code}")
        except Exception as e:
            logger.error(f"Simkl scrobble error: {e}")
        return False

    def get_watching(self) -> Optional[Dict]:
        if not self.access_token:
            return None
        try:
            r = requests.get(
                f"{self.BASE_URL}/sync/activities",
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            logger.error(f"Simkl activities error: {e}")
        return None
