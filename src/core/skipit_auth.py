"""SkipIt / Clerk session auto-refresh helper.

SkipIt (getskipit.com) uses Clerk for auth. The ``Authorization: Bearer``
token the API expects is a short-lived (~5 min) session JWT issued by
Clerk's Frontend API (FAPI) at ``clerk.<domain>``. Clerk's JS SDK silently
refreshes it in the browser using the long-lived ``__client`` cookie.

We reproduce that refresh server-side so the user only has to paste the
``__client`` cookie once (plus one initial JWT so we can extract the
session id / FAPI host without hard-coding them).

Clerk refresh endpoint used:
    POST {FRONTEND_API}/v1/client/sessions/{sid}/tokens
         ?_clerk_js_version=5.0.0
         Cookie: __client=<long JWT>

Response: ``{"jwt": "...", "object": "token"}``
"""
from __future__ import annotations

import base64
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger("stremio-rpc")

CLERK_JS_VERSION = "5.0.0"
REFRESH_MARGIN_SECONDS = 60  # refresh when token has <= this many seconds left
DEFAULT_TIMEOUT = 10


# ----------------------------------------------------------------------
# JWT helpers (no signature verification -- we only read payload claims).
# ----------------------------------------------------------------------
def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def decode_jwt_payload(token: str) -> Dict[str, Any]:
    """Return the decoded JWT payload dict, or {} on failure."""
    if not isinstance(token, str):
        return {}
    if not token or token.count(".") < 2:
        return {}
    try:
        payload_b64 = token.split(".")[1]
        return json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        logger.debug(f"skipit_auth: failed to decode JWT payload: {exc}")
        return {}


def extract_session_meta(token: str) -> Dict[str, Any]:
    """Pull ``sid``, ``iss``, ``exp``, ``frontend_api`` from a SkipIt JWT."""
    payload = decode_jwt_payload(token) or {}
    iss = payload.get("iss") or ""
    frontend_api = ""
    if iss:
        try:
            host = urlparse(iss).netloc or iss
            frontend_api = host.strip().strip("/")
        except Exception:
            frontend_api = ""
    return {
        "sid": payload.get("sid") or "",
        "iss": iss,
        "exp": int(payload.get("exp") or 0),
        "iat": int(payload.get("iat") or 0),
        "sub": payload.get("sub") or "",
        "frontend_api": frontend_api,
    }


def seconds_until_expiry(token: str, *, now: Optional[float] = None) -> int:
    """Positive = seconds remaining; zero/negative = already expired."""
    meta = extract_session_meta(token)
    exp = meta.get("exp") or 0
    if not exp:
        return 0
    return int(exp - (now if now is not None else time.time()))


# ----------------------------------------------------------------------
# Refresher
# ----------------------------------------------------------------------
class SkipItAuth:
    """Thread-safe holder for the active Bearer token with lazy refresh.

    Persists new tokens to disk via ``on_token_refresh`` (typically the
    GUI app's config save callback) so restarts don't force a re-paste.
    """

    def __init__(self, *,
                 token: str = "",
                 session_cookie: str = "",
                 session_id: str = "",
                 frontend_api: str = "",
                 on_token_refresh: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                 timeout: int = DEFAULT_TIMEOUT):
        self._lock = threading.Lock()
        self._token = token.strip() if isinstance(token, str) else ""
        self._session_cookie = session_cookie.strip() if isinstance(session_cookie, str) else ""
        self._session_id = session_id.strip() if isinstance(session_id, str) else ""
        self._frontend_api = frontend_api.strip().strip("/") if isinstance(frontend_api, str) else ""
        self._on_refresh = on_token_refresh
        self._timeout = timeout
        self._last_error: str = ""
        self._last_refreshed_at: float = 0.0
        # Auto-fill missing sid/frontend_api from the provided token.
        self._backfill_from_token()

    # -- mutators --------------------------------------------------
    def update(self, *, token: Optional[str] = None,
               session_cookie: Optional[str] = None,
               session_id: Optional[str] = None,
               frontend_api: Optional[str] = None) -> None:
        with self._lock:
            if token is not None:
                self._token = (token or "").strip()
            if session_cookie is not None:
                self._session_cookie = (session_cookie or "").strip()
            if session_id is not None:
                self._session_id = (session_id or "").strip()
            if frontend_api is not None:
                self._frontend_api = (frontend_api or "").strip().strip("/")
            self._backfill_from_token()

    def _backfill_from_token(self) -> None:
        if not self._token:
            return
        meta = extract_session_meta(self._token)
        if meta.get("sid") and not self._session_id:
            self._session_id = meta["sid"]
        if meta.get("frontend_api") and not self._frontend_api:
            self._frontend_api = meta["frontend_api"]

    # -- read helpers ----------------------------------------------
    @property
    def token(self) -> str:
        with self._lock:
            return self._token

    @property
    def can_refresh(self) -> bool:
        with self._lock:
            return bool(self._session_cookie and self._session_id and self._frontend_api)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            meta = extract_session_meta(self._token) if self._token else {}
            now = time.time()
            exp = meta.get("exp") or 0
            remaining = int(exp - now) if exp else 0
            return {
                "has_token": bool(self._token),
                "has_cookie": bool(self._session_cookie),
                "session_id": self._session_id,
                "frontend_api": self._frontend_api,
                "user_id": meta.get("sub") or "",
                "expires_in": max(remaining, 0),
                "expired": remaining <= 0 and bool(self._token),
                "can_auto_refresh": bool(self._session_cookie and self._session_id and self._frontend_api),
                "last_refreshed_at": int(self._last_refreshed_at) if self._last_refreshed_at else 0,
                "last_error": self._last_error,
            }

    # -- primary accessor: fresh token on demand --------------------
    def get_active_token(self) -> str:
        """Return a token that's guaranteed fresh (refreshing if needed).

        Falls back to the existing token if refresh fails or is impossible.
        Thread-safe; concurrent callers coalesce on the lock.
        """
        with self._lock:
            if not self._token:
                return ""
            remaining = seconds_until_expiry(self._token)
            if remaining > REFRESH_MARGIN_SECONDS:
                return self._token
            if not (self._session_cookie and self._session_id and self._frontend_api):
                # Can't refresh; return what we have (caller handles 401).
                return self._token
            new_token = self._do_refresh_locked()
            return new_token or self._token

    def force_refresh(self) -> Dict[str, Any]:
        """Manually refresh the token now and return a status dict."""
        with self._lock:
            missing = []
            if not self._session_cookie:
                missing.append("__client cookie")
            if not self._session_id:
                missing.append("session_id (paste a valid JWT first)")
            if not self._frontend_api:
                missing.append("frontend_api (paste a valid JWT first)")
            if missing:
                self._last_error = "missing: " + ", ".join(missing)
                return {"ok": False, "error": self._last_error}
            new_token = self._do_refresh_locked()
            ok = bool(new_token)
            result = {"ok": ok}
            if not ok:
                result["error"] = self._last_error or "refresh_failed"
            return result

    # -- internal refresh -------------------------------------------
    def _do_refresh_locked(self) -> str:
        """Perform the Clerk FAPI refresh. Caller must hold the lock."""
        url = f"https://{self._frontend_api}/v1/client/sessions/{self._session_id}/tokens"
        params = {"_clerk_js_version": CLERK_JS_VERSION}
        cookies = {"__client": self._session_cookie}
        headers = {
            "Accept": "application/json",
            "Origin": self._origin_for_frontend_api(),
            "Referer": self._origin_for_frontend_api() + "/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Ascend-Media-RPC/SkipIt",
        }
        try:
            resp = requests.post(url, params=params, cookies=cookies,
                                 headers=headers, timeout=self._timeout)
        except requests.RequestException as exc:
            logger.warning(f"skipit_auth: refresh network error: {exc}")
            self._last_error = f"network: {exc}"
            return ""

        if resp.status_code == 401 or resp.status_code == 403:
            self._last_error = f"clerk_unauthorized_{resp.status_code}"
            logger.warning("skipit_auth: Clerk rejected __client cookie "
                           f"({resp.status_code}); user must re-paste cookie.")
            return ""
        if not resp.ok:
            self._last_error = f"http_{resp.status_code}"
            logger.warning(f"skipit_auth: Clerk refresh HTTP {resp.status_code}: "
                           f"{resp.text[:300]}")
            return ""

        try:
            data = resp.json()
        except ValueError:
            self._last_error = "bad_json"
            return ""
        new_token = data.get("jwt") or ""
        if not new_token:
            # Some Clerk responses wrap in {response: {jwt: ...}}
            nested = data.get("response") or {}
            if isinstance(nested, dict):
                new_token = nested.get("jwt") or ""
        if not new_token:
            self._last_error = "no_jwt_in_response"
            return ""

        # Success.
        self._token = new_token
        self._last_refreshed_at = time.time()
        self._last_error = ""
        self._backfill_from_token()
        exp = seconds_until_expiry(self._token)
        logger.info(f"skipit_auth: refreshed SkipIt token (valid {exp}s).")

        # Persist new token via callback, outside the critical section is
        # safer but callbacks are typically cheap writes.
        cb = self._on_refresh
        if cb:
            try:
                cb(new_token, self.status())
            except Exception as exc:
                logger.warning(f"skipit_auth: on_token_refresh callback failed: {exc}")
        return new_token

    def _origin_for_frontend_api(self) -> str:
        fapi = self._frontend_api or ""
        # Strip leading 'clerk.' subdomain to get the app origin.
        host = fapi
        if host.startswith("clerk."):
            host = host[len("clerk."):]
        return f"https://{host}" if host else "https://getskipit.com"
