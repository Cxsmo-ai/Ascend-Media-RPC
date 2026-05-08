import time
import threading
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("stremio-rpc")


class SkipSegmentCache:
    """TTL-based cache for skip segments to reduce API calls."""

    def __init__(self, ttl: int = 3600, max_size: int = 500):
        self.ttl = ttl
        self.max_size = max_size
        self._cache: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def _make_key(self, imdb_id: str, season: int, episode: int,
                  tmdb_id: Optional[int] = None, title: Optional[str] = None,
                  is_movie: bool = False, year: Optional[str] = None) -> str:
        return f"{imdb_id}-{tmdb_id}-{title}-{season}-{episode}-{is_movie}-{year}"

    def get(self, imdb_id: str, season: int, episode: int,
            tmdb_id: Optional[int] = None, title: Optional[str] = None,
            is_movie: bool = False, year: Optional[str] = None) -> Optional[List[Dict]]:
        key = self._make_key(imdb_id, season, episode, tmdb_id, title, is_movie, year)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.time() - entry["ts"] > self.ttl:
                del self._cache[key]
                return None
            return entry["data"]

    def put(self, imdb_id: str, season: int, episode: int,
            segments: Optional[List[Dict]],
            tmdb_id: Optional[int] = None, title: Optional[str] = None,
            is_movie: bool = False, year: Optional[str] = None):
        key = self._make_key(imdb_id, season, episode, tmdb_id, title, is_movie, year)
        with self._lock:
            if len(self._cache) >= self.max_size:
                oldest_key = min(self._cache, key=lambda k: self._cache[k]["ts"])
                del self._cache[oldest_key]
            self._cache[key] = {"data": segments, "ts": time.time()}

    def invalidate(self, imdb_id: str = None, season: int = None,
                   episode: int = None):
        with self._lock:
            if imdb_id is None:
                self._cache.clear()
                return
            to_remove = [
                k for k in self._cache
                if k.startswith(f"{imdb_id}-")
            ]
            for k in to_remove:
                del self._cache[k]

    def stats(self) -> Dict:
        with self._lock:
            now = time.time()
            valid = sum(1 for e in self._cache.values() if now - e["ts"] <= self.ttl)
            return {
                "total_entries": len(self._cache),
                "valid_entries": valid,
                "expired_entries": len(self._cache) - valid,
                "max_size": self.max_size,
                "ttl_seconds": self.ttl,
            }
