import logging
from typing import Dict, Optional
import urllib.parse
import time

import requests

logger = logging.getLogger("stremio-rpc")


class NuvioCoversClient:
    DEFAULT_BASE_URL = "https://nuvioapp.space"
    # Supabase details for auth refresh
    SUPABASE_AUTH_URL = "https://dpyhjjcoabcglfmgecug.supabase.co/auth/v1/token?grant_type=password"
    SUPABASE_KEY = "sb_publishable_zcNkgqGJjBtj8GoRlMvl9A_zkdmXhf5"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: str = "",
        email: str = "",
        password: str = "",
        on_token_refresh=None,
        outage_failure_threshold: int = 2,
        outage_cooldown_seconds: int = 300,
    ):
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.token = (token or "").strip()
        self.email = (email or "").strip()
        self.password = (password or "").strip()
        self.on_token_refresh = on_token_refresh
        self.session = requests.Session()
        self.cache: Dict[str, Optional[Dict]] = {}
        self.outage_failure_threshold = max(1, int(outage_failure_threshold or 2))
        self.outage_cooldown_seconds = max(30, int(outage_cooldown_seconds or 300))
        self._nuvio_failure_count = 0
        self._nuvio_outage_until = 0.0
        self._nuvio_outage_logged = False

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

    def _headers(self):
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def _refresh_token(self) -> bool:
        """Attempt to get a fresh access token using email/password."""
        if self._nuvio_backoff_active():
            return False

        if not self.email or not self.password:
            logger.warning(f"Nuvio covers: Skipping refresh because credentials are missing (email={bool(self.email)}, pass={bool(self.password)})")
            return False
            
        logger.info(f"Nuvio covers: Attempting token refresh for {self.email}...")
        try:
            headers = {
                "apikey": self.SUPABASE_KEY,
                "Content-Type": "application/json"
            }
            payload = {
                "grant_type": "password",
                "email": self.email,
                "password": self.password
            }
            response = requests.post(self.SUPABASE_AUTH_URL, headers=headers, json=payload, timeout=10)
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

    def find_popular_gif(self, query: str, orientation: str = "all", limit: int = 24, _retried=False) -> Optional[Dict]:
        """Find a popular Nuvio GIF cover by title/search text."""
        query = (query or "").strip()
        if not query:
            return None
        if self._nuvio_backoff_active():
            return None
            
        # Proactive Refresh: Check if token is missing or nearly expired (within 5 mins)
        if not _retried and self.email and self.password:
            needs_refresh = not self.token
            if not needs_refresh:
                try:
                    # Quick JWT decode to check exp
                    import base64
                    import json
                    import time
                    parts = self.token.split(".")
                    if len(parts) == 3:
                        payload_b64 = parts[1]
                        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
                        payload = json.loads(base64.b64decode(payload_b64))
                        exp = payload.get("exp", 0)
                        if exp < time.time() + 300: # 5 minute buffer
                            needs_refresh = True
                except:
                    needs_refresh = True
            
            if needs_refresh:
                if self._refresh_token():
                    # If we have a way to save it back to the main app, we should, 
                    # but for now we just use it in-memory.
                    return self.find_popular_gif(query, orientation, limit, _retried=True)

        if not self.token:
            logger.info("Nuvio covers DEBUG: skipped because token is missing")
            return None

        key = self._cache_key(query, orientation, limit)
        if key in self.cache:
            return self.cache[key]

        params = {
            "format": "gif",
            "sort": "popular",
            "orientation": orientation or "all",
            "page": "1",
            "limit": str(limit or 24),
            "search": query,
        }

        request_failed = False
        try:
            url = f"{self.base_url}/api/covers?{urllib.parse.urlencode(params)}"
            response = self.session.get(url, headers=self._headers(), timeout=8)
            
            # Handle expired token
            if response.status_code in (401, 403) and not _retried:
                logger.info("Nuvio covers DEBUG: token expired, attempting refresh...")
                if self._refresh_token():
                    return self.find_popular_gif(query, orientation, limit, _retried=True)
            
            logger.info(f"Nuvio covers DEBUG: GET {url} status={response.status_code}")
            if response.status_code in (401, 403):
                logger.info("Nuvio covers DEBUG: auth missing/expired; falling back to network logo.")
                self._record_nuvio_failure(f"lookup HTTP {response.status_code}")
                self.cache[key] = None
                return None
                
            response.raise_for_status()
            self._record_nuvio_success()
            data = response.json()
            items = data.get("items") if isinstance(data, dict) else None
            if not isinstance(items, list):
                logger.info("Nuvio covers DEBUG: response did not include items list")
                self.cache[key] = None
                return None
            
            logger.info(f"Nuvio covers DEBUG: items={len(items)} query={query!r}")

            for item in items:
                if not isinstance(item, dict):
                    continue
                image_url = (item.get("image_url") or "").strip()
                mime_type = (item.get("mime_type") or "").lower()
                if image_url and (mime_type == "image/gif" or image_url.lower().split("?")[0].endswith(".gif")):
                    if image_url.startswith("/"):
                        image_url = f"{self.base_url}{image_url}"
                    result = {
                        "image_url": image_url,
                        "title": item.get("title") or query,
                        "id": item.get("id"),
                        "likes_count": item.get("likes_count"),
                    }
                    self.cache[key] = result
                    return result
        except Exception as exc:
            logger.info(f"Nuvio covers DEBUG: lookup failed for {query!r}: {exc}")
            self._record_nuvio_failure(exc.__class__.__name__)
            request_failed = True

        logger.info(f"Nuvio covers DEBUG: no gif image_url found for {query!r}")
        if not request_failed:
            self.cache[key] = None
        return None
