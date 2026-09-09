import logging
import urllib.parse
from typing import Dict, Optional
import requests

logger = logging.getLogger("stremio-rpc")

# These are the filenames used by UltraMax's public Asset Library and its
# collection media map.  Keep this table deliberately explicit: guessing from
# a partial title is how a Showtime request previously ended up with an HBO
# animation.  If UltraMax has no matching asset, the caller must use its static
# logo fallback instead of returning an unrelated GIF.
ULTRAMAX_IMAGE_BASE_URL = "https://ultramax.vip/images/"


def _ultramax_asset(filename: str) -> str:
    return urllib.parse.urljoin(ULTRAMAX_IMAGE_BASE_URL, filename)


DEFAULT_NETWORK_GIFS = {
    # Streaming services present in UltraMax's media map.
    "netflix": {
        "title": "Netflix",
        "image_url": _ultramax_asset("netflix.gif"),
    },
    "hbo": {
        "title": "HBO",
        "image_url": _ultramax_asset("HBO.gif"),
    },
    "hbo max": {
        "title": "HBO / Max",
        "image_url": _ultramax_asset("HBO.gif"),
    },
    "max": {
        "title": "HBO / Max",
        "image_url": _ultramax_asset("HBO.gif"),
    },
    "hbo / max": {
        "title": "HBO / Max",
        "image_url": _ultramax_asset("HBO.gif"),
    },
    "disney+": {
        "title": "Disney+",
        "image_url": _ultramax_asset("Disney.gif"),
    },
    "disney plus": {
        "title": "Disney+",
        "image_url": _ultramax_asset("Disney.gif"),
    },
    "hulu": {
        "title": "Hulu",
        "image_url": _ultramax_asset("Hulu.gif"),
    },
    "amazon prime video": {
        "title": "Prime Video",
        "image_url": _ultramax_asset("Prime.gif"),
    },
    "prime video": {
        "title": "Prime Video",
        "image_url": _ultramax_asset("Prime.gif"),
    },
    "amazon": {
        "title": "Prime Video",
        "image_url": _ultramax_asset("Prime.gif"),
    },
    "apple tv+": {
        "title": "Apple TV+",
        "image_url": _ultramax_asset("Apple.gif"),
    },
    "apple tv": {
        "title": "Apple TV+",
        "image_url": _ultramax_asset("Apple.gif"),
    },
    "paramount+": {
        "title": "Paramount+",
        "image_url": _ultramax_asset("Paramount.gif"),
    },
    "paramount plus": {
        "title": "Paramount+",
        "image_url": _ultramax_asset("Paramount.gif"),
    },
    "paramount": {
        "title": "Paramount+",
        "image_url": _ultramax_asset("Paramount.gif"),
    },
    "peacock": {
        "title": "Peacock",
        "image_url": _ultramax_asset("Peacock.gif"),
    },
    "crunchyroll": {
        "title": "Crunchyroll",
        "image_url": _ultramax_asset("streaming_services.crunchyroll.focus.gif"),
    },
    "starz": {
        "title": "Starz",
        "image_url": _ultramax_asset("quick/starz.gif"),
    },
    "shudder": {
        "title": "Shudder",
        "image_url": _ultramax_asset("Shudder.gif"),
    },
    "mubi": {
        "title": "Mubi",
        "image_url": _ultramax_asset("quick/mubi.gif"),
    },
    "britbox": {
        "title": "BritBox",
        "image_url": _ultramax_asset("Brit.gif"),
    },
    "mgm+": {
        "title": "MGM+",
        "image_url": _ultramax_asset("MGM.gif"),
    },
    "mgm plus": {
        "title": "MGM+",
        "image_url": _ultramax_asset("MGM.gif"),
    },
    "discovery+": {
        "title": "Discovery+",
        "image_url": _ultramax_asset("Discovery.gif"),
    },
    "discovery plus": {
        "title": "Discovery+",
        "image_url": _ultramax_asset("Discovery.gif"),
    },
    "national geographic": {
        "title": "National Geographic",
        "image_url": _ultramax_asset("NatGeo.gif"),
    },
    "nat geo": {
        "title": "National Geographic",
        "image_url": _ultramax_asset("NatGeo.gif"),
    },
    "natgeo": {
        "title": "National Geographic",
        "image_url": _ultramax_asset("NatGeo.gif"),
    },
    "animal planet": {
        "title": "Animal Planet",
        "image_url": _ultramax_asset("animal_planet.gif?v=20260820b"),
    },
    "a and e": {
        "title": "A&E",
        "image_url": _ultramax_asset("A%26E.gif"),
    },

    # British streaming assets explicitly published by UltraMax.
    "itvx": {
        "title": "ITVX",
        "image_url": _ultramax_asset("uk.itvx.focus.gif"),
    },
    "itv": {
        "title": "ITVX",
        "image_url": _ultramax_asset("uk.itvx.focus.gif"),
    },
    "channel 4": {
        "title": "Channel 4",
        "image_url": _ultramax_asset("uk.channel_4.focus.gif"),
    },
    "channel4": {
        "title": "Channel 4",
        "image_url": _ultramax_asset("uk.channel_4.focus.gif"),
    },
    "acorn tv": {
        "title": "Acorn TV",
        "image_url": _ultramax_asset("uk.acorn_tv.focus.gif"),
    },
    "acorn": {
        "title": "Acorn TV",
        "image_url": _ultramax_asset("uk.acorn_tv.focus.gif"),
    },

    # Studios and franchises published by UltraMax.
    "marvel": {
        "title": "Marvel Studios",
        "image_url": _ultramax_asset("studios.marvel.focus.gif"),
    },
    "dc": {
        "title": "DC Studios",
        "image_url": _ultramax_asset("studios.dc.focus.gif"),
    },
    "warner bros": {
        "title": "Warner Bros",
        "image_url": _ultramax_asset("studios.warner_bros.focus.gif"),
    },
    "universal": {
        "title": "Universal Studios",
        "image_url": _ultramax_asset("studios.universal.focus.gif"),
    },
    "ghibli": {
        "title": "Studio Ghibli",
        "image_url": _ultramax_asset("studios.ghibli.focus.gif"),
    },
    "studio ghibli": {
        "title": "Studio Ghibli",
        "image_url": _ultramax_asset("studios.ghibli.focus.gif"),
    },
    "pixar": {
        "title": "Pixar",
        "image_url": _ultramax_asset("Pixar.gif"),
    },
    "a24": {
        "title": "A24",
        "image_url": _ultramax_asset("A24.gif"),
    },
    "blumhouse": {
        "title": "Blumhouse",
        "image_url": _ultramax_asset("Blumhouse.gif"),
    },
    "dreamworks": {
        "title": "DreamWorks",
        "image_url": _ultramax_asset("Dreamworks.gif"),
    },
    "sony": {
        "title": "Sony Pictures",
        "image_url": _ultramax_asset("Sony.gif"),
    },
    "paramount pictures": {
        "title": "Paramount Pictures",
        "image_url": _ultramax_asset("Paramount.gif"),
    },

    # Genre GIFs used by UltraMax collection folders.
    "anime": {
        "title": "Anime",
        "image_url": _ultramax_asset("quick/genres__anime__gif.gif"),
    },
    "action": {
        "title": "Action",
        "image_url": _ultramax_asset("quick/genres__action__gif.gif"),
    },
    "adventure": {
        "title": "Adventure",
        "image_url": _ultramax_asset("quick/genres__adventure__gif.gif"),
    },
    "comedy": {
        "title": "Comedy",
        "image_url": _ultramax_asset("quick/genres__comedy__gif.gif"),
    },
    "drama": {
        "title": "Drama",
        "image_url": _ultramax_asset("quick/genres__drama__gif.gif"),
    },
    "horror": {
        "title": "Horror",
        "image_url": _ultramax_asset("quick/genres__horror__gif.gif"),
    },
    "thriller": {
        "title": "Thriller",
        "image_url": _ultramax_asset("quick/genres__thriller__gif.gif"),
    },
    "war": {
        "title": "War",
        "image_url": _ultramax_asset("quick/genres__war__gif.gif"),
    },
    "western": {
        "title": "Western",
        "image_url": _ultramax_asset("quick/genres__western__gif.gif"),
    },
    "reality tv": {
        "title": "Reality TV",
        "image_url": _ultramax_asset("quick/genres__reality_tv__gif.gif"),
    },
    "romantic comedy": {
        "title": "Romantic Comedy",
        "image_url": _ultramax_asset("quick/genres__romantic_comedy__gif.gif"),
    },
    "stand up comedy": {
        "title": "Stand-up Comedy",
        "image_url": _ultramax_asset("quick/genres__stand_up_comedy__gif.gif"),
    },
    "history": {
        "title": "History",
        "image_url": _ultramax_asset("quick/genres__history__gif.gif"),
    },
}


class NetworkGifsClient:
    """
    Client for fetching streaming and TV network animated logo GIFs via direct links.
    No login or authentication is required.
    """

    def __init__(
        self,
        index_url: str = "",
        custom_mappings: Optional[Dict[str, str]] = None,
        session: Optional[requests.Session] = None,
        verify_urls: bool = False,
        **_kwargs,
    ):
        self.index_url = (index_url or "").strip()
        self.custom_mappings = {
            self.normalize_key(key): value.strip()
            for key, value in (custom_mappings or {}).items()
            if isinstance(key, str) and isinstance(value, str) and value.strip()
        }
        self.session = session or requests.Session()
        self.verify_urls = bool(verify_urls)
        self.cache: Dict[str, Optional[Dict]] = {}
        self._remote_catalog: Optional[Dict[str, Dict]] = None

    @staticmethod
    def _is_ultramax_url(url: str) -> bool:
        try:
            parsed = urllib.parse.urlsplit(url)
            return (
                parsed.scheme in {"http", "https"}
                and parsed.netloc.lower().split(":", 1)[0] in {"ultramax.vip", "www.ultramax.vip"}
                and parsed.path.lower().startswith("/images/")
            )
        except Exception:
            return False

    def _verify_image_url(self, url: str) -> bool:
        """Verify that a configured UltraMax asset is a live image.

        UltraMax currently serves a few animated WebP files with a ``.gif``
        filename, so accept both real GIF and RIFF/WebP signatures.  HTML
        challenge pages, redirects to unrelated sites, and 404 responses are
        rejected before Discord sees them.
        """
        if not self.verify_urls:
            return True
        if not self._is_ultramax_url(url):
            return False
        response = None
        try:
            response = self.session.get(url, timeout=8.0, stream=True)
            if getattr(response, "status_code", 0) != 200:
                return False
            content_type = (getattr(response, "headers", {}) or {}).get("Content-Type", "").lower()
            if "text/html" in content_type:
                return False
            raw = getattr(response, "raw", None)
            header = raw.read(12) if raw is not None and hasattr(raw, "read") else b""
            if not header:
                content = getattr(response, "content", b"")
                header = content[:12] if isinstance(content, (bytes, bytearray)) else b""
            # A .gif path is not sufficient: UltraMax has a few mislabeled
            # static JPEG assets. Do not present those as animated icons.
            return header.startswith((b"GIF87a", b"GIF89a", b"RIFF"))
        except Exception as exc:
            logger.debug("UltraMax GIF validation failed: %s", exc.__class__.__name__)
            return False
        finally:
            if response is not None and hasattr(response, "close"):
                response.close()

    def _load_remote_catalog(self) -> Dict[str, Dict]:
        if self._remote_catalog is not None:
            return self._remote_catalog
        if not self.index_url:
            self._remote_catalog = {}
            return self._remote_catalog
        try:
            resp = self.session.get(self.index_url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    normalized = {}
                    for key, val in data.items():
                        if isinstance(val, dict) and val.get("image_url"):
                            image_url = str(val.get("image_url")).strip()
                            if self._is_ultramax_url(image_url):
                                normalized[self.normalize_key(key)] = {**val, "image_url": image_url}
                        elif isinstance(val, str) and val.strip():
                            image_url = val.strip()
                            if self._is_ultramax_url(image_url):
                                normalized[self.normalize_key(key)] = {"title": key.title(), "image_url": image_url}
                    self._remote_catalog = normalized
                    return self._remote_catalog
        except Exception as e:
            logger.debug(f"Failed to fetch remote network GIF index: {e}")
        self._remote_catalog = {}
        return self._remote_catalog

    @staticmethod
    def normalize_key(query: str) -> str:
        key = (query or "").strip().lower()
        key = key.replace("&", "and")
        key = " ".join(key.replace("+", " plus ").split())
        return key

    def find_popular_gif(self, query: str, orientation: str = "all", limit: int = 24, _retried=False) -> Optional[Dict]:
        """
        Resolves a network search query to a direct animated GIF image URL.
        """
        query = (query or "").strip()
        if not query:
            return None

        cache_key = query.lower()
        if cache_key in self.cache:
            return self.cache[cache_key]

        norm_key = self.normalize_key(query)

        # 1. Custom mappings check
        if norm_key in self.custom_mappings:
            url = self.custom_mappings[norm_key]
            res = {"image_url": url, "title": query}
            self.cache[cache_key] = res
            return res

        # 2. Remote UltraMax catalog check (if index_url provided)
        remote = self._load_remote_catalog()
        if norm_key in remote:
            result = remote[norm_key]
            if self._verify_image_url(result.get("image_url", "")):
                self.cache[cache_key] = result
                return result

        # 3. Built-in exact UltraMax asset mapping.  Do not fuzzy-match: a
        # missing network must never silently inherit another network's GIF.
        if norm_key in DEFAULT_NETWORK_GIFS:
            res = DEFAULT_NETWORK_GIFS[norm_key].copy()
            res["source"] = "ultramax"
            if self._verify_image_url(res["image_url"]):
                self.cache[cache_key] = res
                return res

        self.cache[cache_key] = None
        return None
