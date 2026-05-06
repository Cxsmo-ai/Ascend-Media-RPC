import hashlib
import logging
import os
from io import BytesIO
from typing import Callable, Dict, Optional
from urllib.parse import urlencode

import requests
from PIL import Image, ImageChops, ImageFilter, ImageOps

from src.core.config import get_config_path

logger = logging.getLogger("stremio-rpc")


class TopPostersClient:
    ALLOWED_POSITIONS = {
        "top-right",
        "top-left",
        "top-center",
        "bottom-right",
        "bottom-left",
        "bottom-center",
    }
    ALLOWED_SIZES = {"small", "medium", "large"}
    CANVAS_SIZE = (512, 768)

    def __init__(
        self,
        config: Dict,
        cache_dir: Optional[str] = None,
        image_fetcher: Optional[Callable[[str], Optional[Image.Image]]] = None,
    ):
        self.config = config
        self.cache_dir = cache_dir or os.path.join(get_config_path(), "top_posters_cache")
        self.image_fetcher = image_fetcher
        self.session = requests.Session()
        self._validation_cache = {}
        self.last_validation_error = None

    def update_config(self, config: Dict):
        self.config = config

    def is_enabled(self) -> bool:
        return (
            self.config.get("artwork_provider") == "top_posters"
            and bool(str(self.config.get("top_posters_api_key", "")).strip())
        )

    def is_selected(self) -> bool:
        return self.is_enabled()

    def _base_url(self) -> str:
        base_url = (
            self.config.get("top_posters_base_url")
            or "https://api.top-posters.com"
        ).strip().rstrip("/")

        # Old host compatibility.
        if "top-streaming.stream" in base_url:
            base_url = "https://api.top-posters.com"

        return base_url

    def _badge_size(self) -> str:
        value = str(self.config.get("top_posters_badge_size") or "medium").strip()
        return value if value in {"small", "medium", "large"} else "medium"

    def _badge_position(self) -> str:
        value = str(self.config.get("top_posters_badge_position") or "bottom-left").strip()
        allowed = {
            "top-left",
            "top-right",
            "top-center",
            "bottom-left",
            "bottom-right",
            "bottom-center",
        }
        return value if value in allowed else "bottom-left"

    def build_poster_url(self, imdb_id: str, fallback_url: Optional[str] = None) -> Optional[str]:
        if not self.is_enabled() or not imdb_id:
            return None

        # Do NOT include fallback_url here.
        # That makes URLs huge after wsrv wrapping.
        params = {
            "style": self.config.get("top_posters_style") or "modern",
        }

        return self._build_url("imdb", "poster", imdb_id, params=params)

    def build_thumbnail_url(
        self,
        imdb_id: str,
        season: int,
        episode: int,
        fallback_url: Optional[str] = None,
    ) -> Optional[str]:
        if not self.is_enabled() or not imdb_id or season is None or episode is None:
            return None

        # Thumbnail endpoint is Premium-only, so validation may fail.
        # That is okay; app will fallback to Top Posters poster, then TMDB.
        params = {
            "badge_size": self._badge_size(),
            "badge_position": self._badge_position(),
            "blur": "true" if self.config.get("top_posters_blur") else "false",
        }

        suffix = f"S{int(season)}E{int(episode)}.jpg"
        return self._build_url("imdb", "thumbnail", imdb_id, suffix=suffix, params=params)

    def validate_artwork_url(self, url: str) -> bool:
        if not url or self.config.get("top_posters_validate_remote", True) is False:
            return bool(url)
        if url in self._validation_cache:
            self.last_validation_error = self._validation_cache[url][1]
            return self._validation_cache[url][0]

        response = None
        try:
            response = self.session.get(url, timeout=15, stream=True, allow_redirects=False)
            content_type = response.headers.get("Content-Type", "")
            ok = 200 <= int(response.status_code) < 300 and content_type.lower().startswith("image/")
            if ok:
                reason = None
            elif 300 <= int(response.status_code) < 400:
                reason = f"redirect HTTP {response.status_code}"
            else:
                reason = f"HTTP {response.status_code}"
            self._validation_cache[url] = (ok, reason)
            self.last_validation_error = reason
            return ok
        except Exception as exc:
            reason = exc.__class__.__name__
            self._validation_cache[url] = (False, reason)
            self.last_validation_error = reason
            return False
        finally:
            if response is not None:
                response.close()

    def generate_masked_season_poster(
        self,
        imdb_id: str,
        tmdb_id: int,
        season: int,
        top_poster_url: str,
        show_poster_url: str,
        season_poster_url: str,
    ) -> Optional[Dict[str, str]]:
        if not self.is_enabled() or not all([imdb_id, tmdb_id, season, top_poster_url, show_poster_url, season_poster_url]):
            return None

        cache_key = self._season_cache_key(imdb_id, tmdb_id, season)
        path = self.get_cached_artwork_path(cache_key)
        if os.path.exists(path):
            return {"cache_key": cache_key, "path": path}

        try:
            top_poster = self._fetch_image(top_poster_url)
            show_poster = self._fetch_image(show_poster_url)
            season_poster = self._fetch_image(season_poster_url)
            if not top_poster or not show_poster or not season_poster:
                return None

            top_poster = self._normalize(top_poster)
            show_poster = self._normalize(show_poster)
            season_poster = self._normalize(season_poster)

            diff = ImageChops.difference(top_poster, show_poster).convert("L")
            threshold = int(self.config.get("top_posters_season_mask_threshold", 32) or 32)
            mask = diff.point(lambda p: 255 if p > threshold else 0)
            mask = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(0.8))

            output = Image.composite(top_poster, season_poster, mask)
            os.makedirs(self.cache_dir, exist_ok=True)
            output.save(path, format="JPEG", quality=96, subsampling=0)
            return {"cache_key": cache_key, "path": path}
        except Exception as exc:
            logger.warning(f"Top Posters season composite failed: {exc}")
            return None

    def get_cached_artwork_path(self, cache_key: str) -> str:
        safe_key = "".join(ch for ch in cache_key if ch.isalnum() or ch in ("-", "_"))
        return os.path.join(self.cache_dir, f"{safe_key}.jpg")

    def _build_url(
        self,
        id_type: str,
        image_type: str,
        media_id: str,
        suffix: Optional[str] = None,
        params: Optional[Dict] = None,
    ) -> str:
        base_url = self._base_url()
        api_key = str(self.config.get("top_posters_api_key", "")).strip()

        if suffix:
            path = f"{base_url}/{api_key}/{id_type}/{image_type}/{media_id}/{suffix}"
        else:
            path = f"{base_url}/{api_key}/{id_type}/{image_type}/{media_id}.jpg"

        query = urlencode(params or {})
        return f"{path}?{query}" if query else path

    def _fetch_image(self, url: str) -> Optional[Image.Image]:
        if self.image_fetcher:
            return self.image_fetcher(url)
        response = self.session.get(url, timeout=25)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))

    def _normalize(self, image: Image.Image) -> Image.Image:
        return ImageOps.fit(image.convert("RGB"), self.CANVAS_SIZE, method=Image.Resampling.LANCZOS)

    def _season_cache_key(self, imdb_id: str, tmdb_id: int, season: int) -> str:
        raw = "|".join(
            str(part)
            for part in (
                imdb_id,
                tmdb_id,
                season,
                self.config.get("top_posters_style", "modern"),
                self._badge_size(),
                self._badge_position(),
                self.config.get("top_posters_season_mask_threshold", 32),
            )
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
