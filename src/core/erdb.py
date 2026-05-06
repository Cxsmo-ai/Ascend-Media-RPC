import logging
import re
from typing import Dict, Optional

import requests

logger = logging.getLogger("stremio-rpc")


class ERDBClient:
    DEFAULT_BASE_URL = "https://easyratingsdb.com"
    TYPE_TOGGLES = {
        "poster": "erdb_posters_enabled",
        "backdrop": "erdb_backdrops_enabled",
        "logo": "erdb_logos_enabled",
        "thumbnail": "erdb_thumbnails_enabled",
    }

    def __init__(self, config: Dict):
        self.config = config
        self.session = requests.Session()
        self._validation_cache = {}
        self.last_validation_error = None

    def update_config(self, config: Dict):
        self.config = config

    def is_selected(self) -> bool:
        return self.config.get("artwork_provider", "legacy") == "erdb"

    def normalized_base_url(self) -> str:
        return (self.config.get("erdbBaseUrl") or self.config.get("erdb_base_url") or self.DEFAULT_BASE_URL).strip().rstrip("/")

    def token(self) -> str:
        value = (self.config.get("erdbToken") or self.config.get("erdb_token") or "").strip()
        # Handle full configurator URL (e.g. https://easyratingsdb.com/Tk-ABC123XYZ)
        if "Tk-" in value:
            match = re.search(r"Tk-[A-Za-z0-9_-]+", value)
            if match:
                return match.group(0)
        return value

    def build_url(self, artwork_type: str, media_id: str) -> Optional[str]:
        token = self.token()
        if not self.is_selected() or not token or not artwork_type or not media_id:
            return None

        toggle_key = self.TYPE_TOGGLES.get(artwork_type)
        if toggle_key and not self.config.get(toggle_key, True):
            return None

        return f"{self.normalized_base_url()}/{token}/{artwork_type}/{media_id}.jpg"

    def build_episode_thumbnail_url(self, series_imdb_id: str, season: int, episode: int) -> Optional[str]:
        if not series_imdb_id or season is None or episode is None:
            return None
        episode_id = f"{series_imdb_id}:{int(season)}:{int(episode)}"
        if self.config.get("erdb_episode_id_mode", "realimdb") == "realimdb":
            episode_id = f"realimdb:{episode_id}"
        return self.build_url("thumbnail", episode_id)

    def validate_artwork_url(self, url: str) -> bool:
        if not url or self.config.get("erdb_validate_remote", False) is False:
            return bool(url)
        if url in self._validation_cache:
            self.last_validation_error = self._validation_cache[url][1]
            return self._validation_cache[url][0]

        response = None
        try:
            logger.debug(f"ERDB: Validating remote artwork: {url}")
            response = self.session.get(url, timeout=6, stream=True, allow_redirects=True)
            content_type = response.headers.get("Content-Type", "")
            status_code = int(response.status_code)
            
            ok = 200 <= status_code < 300 and content_type.lower().startswith("image/")
            reason = None if ok else f"HTTP {status_code} ({content_type})"
            
            if ok:
                logger.debug(f"ERDB: Validation SUCCESS for {url}")
            else:
                logger.debug(f"ERDB: Validation FAILED: {reason}")
                
            self._validation_cache[url] = (ok, reason)
            self.last_validation_error = reason
            return ok
        except Exception as exc:
            reason = exc.__class__.__name__
            logger.debug(f"ERDB: Validation ERROR: {reason}")
            self._validation_cache[url] = (False, reason)
            self.last_validation_error = reason
            return False
        finally:
            if response is not None:
                response.close()
