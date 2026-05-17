import logging
import requests
from typing import Dict, Optional, List

logger = logging.getLogger("stremio-rpc")

ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"


class AniListClient:
    """AniList GraphQL API integration for anime metadata and tracking."""

    def __init__(self, access_token: str = ""):
        self.access_token = access_token

    def _headers(self) -> Dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def search_anime(self, title: str, year: Optional[int] = None) -> Optional[Dict]:
        query = """
        query ($search: String, $seasonYear: Int) {
            Media(search: $search, type: ANIME, seasonYear: $seasonYear) {
                id
                idMal
                title { romaji english native userPreferred }
                episodes
                status
                averageScore
                meanScore
                genres
                studios(isMain: true) { nodes { name } }
                coverImage { large medium }
                bannerImage
                description(asHtml: false)
                format
                season
                seasonYear
            }
        }
        """
        variables = {"search": title}
        if year:
            variables["seasonYear"] = year
        try:
            r = requests.post(
                ANILIST_GRAPHQL_URL,
                json={"query": query, "variables": variables},
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("data", {}).get("Media")
            logger.warning(f"AniList search failed: {r.status_code}")
        except Exception as e:
            logger.error(f"AniList search error: {e}")
        return None

    def get_by_mal_id(self, mal_id: int) -> Optional[Dict]:
        query = """
        query ($malId: Int) {
            Media(idMal: $malId, type: ANIME) {
                id
                idMal
                title { romaji english native userPreferred }
                episodes
                status
                averageScore
                meanScore
                genres
                studios(isMain: true) { nodes { name } }
                coverImage { large medium }
                bannerImage
                description(asHtml: false)
            }
        }
        """
        try:
            r = requests.post(
                ANILIST_GRAPHQL_URL,
                json={"query": query, "variables": {"malId": mal_id}},
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                return r.json().get("data", {}).get("Media")
        except Exception as e:
            logger.error(f"AniList MAL lookup error: {e}")
        return None

    def update_progress(self, media_id: int, progress: int) -> bool:
        if not self.access_token:
            return False
        mutation = """
        mutation ($mediaId: Int, $progress: Int) {
            SaveMediaListEntry(mediaId: $mediaId, progress: $progress) {
                id
                progress
                status
            }
        }
        """
        try:
            r = requests.post(
                ANILIST_GRAPHQL_URL,
                json={"query": mutation, "variables": {"mediaId": media_id, "progress": progress}},
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                logger.info(f"AniList progress updated: media={media_id} ep={progress}")
                return True
            logger.warning(f"AniList progress update failed: {r.status_code}")
        except Exception as e:
            logger.error(f"AniList progress update error: {e}")
        return False

    def get_user_score(self, media_id: int) -> Optional[float]:
        if not self.access_token:
            return None
        query = """
        query ($mediaId: Int) {
            MediaList(mediaId: $mediaId) {
                score
                status
                progress
            }
        }
        """
        try:
            r = requests.post(
                ANILIST_GRAPHQL_URL,
                json={"query": query, "variables": {"mediaId": media_id}},
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code == 200:
                entry = r.json().get("data", {}).get("MediaList")
                if entry:
                    return entry.get("score")
        except Exception as e:
            logger.error(f"AniList score fetch error: {e}")
        return None
