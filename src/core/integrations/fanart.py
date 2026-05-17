import logging
import requests
from typing import Dict, Optional, List

logger = logging.getLogger("stremio-rpc")


class FanArtClient:
    """FanArt.tv API integration for high-quality artwork."""

    BASE_URL = "https://webservice.fanart.tv/v3"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def get_movie_images(self, tmdb_id: str) -> Optional[Dict]:
        if not self.api_key:
            return None
        try:
            r = requests.get(
                f"{self.BASE_URL}/movies/{tmdb_id}",
                params={"api_key": self.api_key},
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
            logger.warning(f"FanArt movie images failed: {r.status_code}")
        except Exception as e:
            logger.error(f"FanArt movie images error: {e}")
        return None

    def get_show_images(self, tvdb_id: str) -> Optional[Dict]:
        if not self.api_key:
            return None
        try:
            r = requests.get(
                f"{self.BASE_URL}/tv/{tvdb_id}",
                params={"api_key": self.api_key},
                timeout=10,
            )
            if r.status_code == 200:
                return r.json()
            logger.warning(f"FanArt show images failed: {r.status_code}")
        except Exception as e:
            logger.error(f"FanArt show images error: {e}")
        return None

    def get_best_poster(self, tmdb_id: str, media_type: str = "movie") -> Optional[str]:
        if media_type == "movie":
            data = self.get_movie_images(tmdb_id)
            if data:
                posters = data.get("movieposter", [])
                if posters:
                    best = sorted(posters, key=lambda x: int(x.get("likes", 0)), reverse=True)
                    return best[0].get("url")
        else:
            data = self.get_show_images(tmdb_id)
            if data:
                posters = data.get("tvposter", [])
                if posters:
                    best = sorted(posters, key=lambda x: int(x.get("likes", 0)), reverse=True)
                    return best[0].get("url")
        return None

    def get_best_background(self, tmdb_id: str, media_type: str = "movie") -> Optional[str]:
        if media_type == "movie":
            data = self.get_movie_images(tmdb_id)
            key = "moviebackground"
        else:
            data = self.get_show_images(tmdb_id)
            key = "showbackground"
        if data:
            bgs = data.get(key, [])
            if bgs:
                best = sorted(bgs, key=lambda x: int(x.get("likes", 0)), reverse=True)
                return best[0].get("url")
        return None

    def get_clearlogo(self, tmdb_id: str, media_type: str = "movie") -> Optional[str]:
        if media_type == "movie":
            data = self.get_movie_images(tmdb_id)
            key = "hdmovielogo"
        else:
            data = self.get_show_images(tmdb_id)
            key = "hdtvlogo"
        if data:
            logos = data.get(key, [])
            if logos:
                best = sorted(logos, key=lambda x: int(x.get("likes", 0)), reverse=True)
                return best[0].get("url")
        return None
