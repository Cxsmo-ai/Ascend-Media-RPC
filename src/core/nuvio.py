import base64
import json
import logging
import os
import time
import urllib.parse
from typing import Dict, Optional

import requests

from src.core.network_gifs import NetworkGifsClient, DEFAULT_NETWORK_GIFS

logger = logging.getLogger("stremio-rpc")


class NuvioCoversClient(NetworkGifsClient):
    """
    NuvioCoversClient handles animated network GIF lookups via Nuvio (nuvio.tv / api.nuvio.tv).
    Supports token authentication via Supabase password grant and UltraMax anon key.
    """
    DEFAULT_BASE_URL = "https://nuvio.tv"
    NUVIO_API_BASE = "https://api.nuvio.tv"
    NUVIO_ANON_KEY = ""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: str = "",
        email: str = "",
        password: str = "",
        anon_key: str = "",
        on_token_refresh=None,
        outage_failure_threshold: int = 2,
        outage_cooldown_seconds: int = 300,
        **kwargs,
    ):
        base = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        if "nuvioapp.space" in base:
            base = "https://nuvio.tv"
        super().__init__(index_url="", **kwargs)
        self.base_url = base
        self.token = (token or "").strip()
        self.email = (email or "").strip()
        self.password = (password or "").strip()
        self.anon_key = (anon_key or os.environ.get("NUVIO_ANON_KEY", "")).strip()
        self.on_token_refresh = on_token_refresh
        self.session = requests.Session()
        self.cache: Dict[str, Optional[Dict]] = {}
        self.outage_failure_threshold = max(1, int(outage_failure_threshold or 2))
        self.outage_cooldown_seconds = max(30, int(outage_cooldown_seconds or 300))
        self._nuvio_failure_count = 0
        self._nuvio_outage_until = 0.0
        self._nuvio_outage_logged = False

    def _headers(self):
        headers = {
            "Content-Type": "application/json",
            "X-Client-Info": "UltraMAX/1.0",
        }
        if self.anon_key:
            headers["apikey"] = self.anon_key
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _nuvio_backoff_active(self) -> bool:
        if time.time() < self._nuvio_outage_until:
            return True
        if self._nuvio_outage_until:
            self._nuvio_outage_until = 0.0
            self._nuvio_outage_logged = False
        return False

    def _record_nuvio_failure(self, reason: str) -> None:
        self._nuvio_failure_count += 1
        if self._nuvio_failure_count < self.outage_failure_threshold:
            return

        self._nuvio_outage_until = time.time() + self.outage_cooldown_seconds
        if not self._nuvio_outage_logged:
            logger.warning(
                "Nuvio covers: temporarily backing off for "
                f"{self.outage_cooldown_seconds // 60} minutes after "
                f"{self._nuvio_failure_count} consecutive failures ({reason})."
            )
            self._nuvio_outage_logged = True

    def _record_nuvio_success(self) -> None:
        self._nuvio_failure_count = 0
        self._nuvio_outage_until = 0.0
        self._nuvio_outage_logged = False

    def _refresh_token(self) -> bool:
        """Attempt to get a fresh access token using email/password via NUVIO_API_BASE."""
        if self._nuvio_backoff_active():
            return False

        if not self.email or not self.password:
            logger.warning(
                f"Nuvio covers: Skipping refresh because credentials are missing (email={bool(self.email)}, pass={bool(self.password)})"
            )
            return False

        logger.info(f"Nuvio covers: Attempting token refresh for {self.email}...")
        try:
            auth_url = f"{self.NUVIO_API_BASE}/auth/v1/token?grant_type=password"
            payload = {
                "grant_type": "password",
                "email": self.email,
                "password": self.password,
            }
            response = requests.post(auth_url, headers=self._headers(), json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                new_token = data.get("access_token")
                if new_token:
                    self.token = new_token
                    logger.info("Nuvio covers: Token refreshed successfully.")
                    if self.on_token_refresh:
                        try:
                            self.on_token_refresh(new_token)
                        except Exception as e:
                            logger.error(f"Nuvio covers: Failed to call on_token_refresh callback: {e}")
                    self._record_nuvio_success()
                    return True
            logger.warning(f"Nuvio covers: Refresh failed status={response.status_code} body={response.text[:200]}")
            self._record_nuvio_failure(f"refresh HTTP {response.status_code}")
        except Exception as e:
            logger.error(f"Nuvio covers: Refresh error: {e}")
            self._record_nuvio_failure(e.__class__.__name__)
        return False

    @staticmethod
    def _cache_key(query: str, orientation: str, limit: int) -> str:
        return f"{query.strip().lower()}|{orientation}|{limit}"

    def _valid_gif_url(self, image_url: str) -> bool:
        """Reject deleted Nuvio uploads before they reach Discord.

        The covers API can retain metadata for an upload after the underlying
        file is gone. A short streamed probe is only made for API results;
        built-in fallback assets do not incur a network request.
        """
        try:
            parsed = urllib.parse.urlsplit(image_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return False
            request_headers = {}
            if parsed.netloc.lower() in {
                urllib.parse.urlsplit(self.base_url).netloc.lower(),
                urllib.parse.urlsplit(self.NUVIO_API_BASE).netloc.lower(),
            }:
                request_headers = self._headers()
            response = self.session.get(
                image_url,
                headers=request_headers,
                stream=True,
                timeout=5,
            )
            try:
                if response.status_code != 200:
                    return False
                content_type = (response.headers.get("Content-Type") or "").lower()
                return "gif" in content_type or image_url.lower().split("?", 1)[0].endswith(".gif")
            finally:
                response.close()
        except Exception as exc:
            logger.debug(f"Nuvio covers: GIF validation failed: {exc.__class__.__name__}")
            return False

    def find_popular_gif(self, query: str, orientation: str = "all", limit: int = 24, _retried=False) -> Optional[Dict]:
        """Find a popular Nuvio GIF cover by title/search text."""
        query = (query or "").strip()
        if not query:
            return None

        key = self._cache_key(query, orientation, limit)
        if key in self.cache:
            return self.cache[key]

        # Check token freshness
        if not _retried and self.email and self.password:
            needs_refresh = not self.token
            if not needs_refresh:
                try:
                    parts = self.token.split(".")
                    if len(parts) == 3:
                        payload_b64 = parts[1]
                        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
                        payload = json.loads(base64.b64decode(payload_b64))
                        exp = payload.get("exp", 0)
                        if exp < time.time() + 300:
                            needs_refresh = True
                except Exception:
                    needs_refresh = True

            if needs_refresh:
                if self._refresh_token():
                    return self.find_popular_gif(query, orientation, limit, _retried=True)

        if not self._nuvio_backoff_active() and self.token:
            params = {
                "format": "gif",
                "sort": "popular",
                "orientation": orientation or "all",
                "page": "1",
                "limit": str(limit or 24),
                "search": query,
            }

            try:
                url = f"{self.base_url}/api/covers?{urllib.parse.urlencode(params)}"
                response = self.session.get(url, headers=self._headers(), timeout=8)

                if response.status_code in (401, 403) and not _retried:
                    logger.info("Nuvio covers DEBUG: token expired, attempting refresh...")
                    if self._refresh_token():
                        return self.find_popular_gif(query, orientation, limit, _retried=True)

                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items") if isinstance(data, dict) else None
                    if not isinstance(items, list) or len(items) == 0:
                        # Try popular covers without search filter if specific search returned no items
                        gen_params = {
                            "format": "gif",
                            "sort": "popular",
                            "orientation": orientation or "all",
                            "page": "1",
                            "limit": str(limit or 24),
                        }
                        gen_url = f"{self.base_url}/api/covers?{urllib.parse.urlencode(gen_params)}"
                        gen_resp = self.session.get(gen_url, headers=self._headers(), timeout=8)
                        if gen_resp.status_code == 200:
                            gen_data = gen_resp.json()
                            items = gen_data.get("items") if isinstance(gen_data, dict) else None

                    if isinstance(items, list):
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            image_url = (item.get("image_url") or "").strip()
                            mime_type = (item.get("mime_type") or "").lower()
                            if image_url and (mime_type == "image/gif" or image_url.lower().split("?")[0].endswith(".gif")):
                                if image_url.startswith("/"):
                                    image_url = f"{self.base_url}{image_url}"
                                if not self._valid_gif_url(image_url):
                                    logger.debug(
                                        f"Nuvio covers: skipping unavailable GIF result for {query!r}"
                                    )
                                    continue
                                result = {
                                    "image_url": image_url,
                                    "title": item.get("title") or query,
                                    "id": item.get("id"),
                                    "likes_count": item.get("likes_count"),
                                }
                                self.cache[key] = result
                                self._record_nuvio_success()
                                return result
            except Exception as exc:
                logger.info(f"Nuvio covers DEBUG: lookup failed for {query!r}: {exc}")
                self._record_nuvio_failure(exc.__class__.__name__)

        # Fallback to local / direct network GIF
        fallback_res = super().find_popular_gif(query, orientation=orientation, limit=limit, _retried=_retried)
        if fallback_res:
            self.cache[key] = fallback_res
            return fallback_res

        self.cache[key] = None
        return None
