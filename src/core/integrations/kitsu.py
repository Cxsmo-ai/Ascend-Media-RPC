import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger("stremio-rpc")


class KitsuClient:
    """Kitsu API integration for anime tracking."""

    BASE_URL = "https://kitsu.io/api/edge"

    def __init__(self, access_token: str = ""):
        self.access_token = access_token

    def _headers(self) -> Dict:
        headers = {
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def search_anime(self, title: str) -> Optional[Dict]:
        try:
            r = requests.get(
                f"{self.BASE_URL}/anime",
                params={"filter[text]": title, "page[limit]": 1},
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json().get("data", [])
                return data[0] if data else None
        except Exception as e:
            logger.error(f"Kitsu search error: {e}")
        return None

    def get_by_mal_id(self, mal_id: int) -> Optional[Dict]:
        try:
            r = requests.get(
                f"{self.BASE_URL}/mappings",
                params={
                    "filter[externalSite]": "myanimelist/anime",
                    "filter[externalId]": str(mal_id),
                    "include": "item",
                },
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                included = r.json().get("included", [])
                return included[0] if included else None
        except Exception as e:
            logger.error(f"Kitsu MAL lookup error: {e}")
        return None

    def update_progress(self, library_entry_id: str, progress: int) -> bool:
        if not self.access_token:
            return False
        try:
            payload = {
                "data": {
                    "type": "libraryEntries",
                    "id": library_entry_id,
                    "attributes": {"progress": progress},
                }
            }
            r = requests.patch(
                f"{self.BASE_URL}/library-entries/{library_entry_id}",
                json=payload,
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                logger.info(f"Kitsu progress updated: entry={library_entry_id} ep={progress}")
                return True
            logger.warning(f"Kitsu progress update failed: {r.status_code}")
        except Exception as e:
            logger.error(f"Kitsu progress update error: {e}")
        return False
