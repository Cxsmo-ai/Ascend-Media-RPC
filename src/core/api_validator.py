import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger("stremio-rpc")


class APIKeyValidator:
    """Validates API keys against their respective services."""

    TIMEOUT = 5

    @staticmethod
    def validate_tmdb(api_key: str) -> Dict:
        if not api_key:
            return {"valid": False, "error": "No API key provided"}
        try:
            r = requests.get(
                f"https://api.themoviedb.org/3/configuration?api_key={api_key}",
                timeout=APIKeyValidator.TIMEOUT,
            )
            if r.status_code == 200:
                return {"valid": True, "service": "tmdb"}
            return {"valid": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    @staticmethod
    def validate_mal(client_id: str) -> Dict:
        if not client_id:
            return {"valid": False, "error": "No client ID provided"}
        try:
            r = requests.get(
                "https://api.myanimelist.net/v2/anime/1",
                headers={"X-MAL-CLIENT-ID": client_id},
                timeout=APIKeyValidator.TIMEOUT,
            )
            if r.status_code == 200:
                return {"valid": True, "service": "mal"}
            return {"valid": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    @staticmethod
    def validate_trakt(client_id: str) -> Dict:
        if not client_id:
            return {"valid": False, "error": "No client ID provided"}
        try:
            r = requests.get(
                "https://api.trakt.tv/calendars/shows/new/2024-01-01/1",
                headers={
                    "Content-Type": "application/json",
                    "trakt-api-version": "2",
                    "trakt-api-key": client_id,
                },
                timeout=APIKeyValidator.TIMEOUT,
            )
            if r.status_code == 200:
                return {"valid": True, "service": "trakt"}
            return {"valid": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    @staticmethod
    def validate_opensubtitles(api_key: str) -> Dict:
        if not api_key:
            return {"valid": False, "error": "No API key provided"}
        try:
            r = requests.get(
                "https://api.opensubtitles.com/api/v1/infos/languages",
                headers={"Api-Key": api_key},
                timeout=APIKeyValidator.TIMEOUT,
            )
            if r.status_code == 200:
                return {"valid": True, "service": "opensubtitles"}
            return {"valid": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    @staticmethod
    def validate_lastfm(api_key: str) -> Dict:
        if not api_key:
            return {"valid": False, "error": "No API key provided"}
        try:
            r = requests.get(
                f"https://ws.audioscrobbler.com/2.0/?method=chart.gettopartists&api_key={api_key}&format=json&limit=1",
                timeout=APIKeyValidator.TIMEOUT,
            )
            if r.status_code == 200:
                return {"valid": True, "service": "lastfm"}
            return {"valid": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    @classmethod
    def validate_all(cls, config: Dict) -> Dict[str, Dict]:
        results = {}
        if config.get("tmdb_api_key"):
            results["tmdb"] = cls.validate_tmdb(config["tmdb_api_key"])
        if config.get("mal_client_id"):
            results["mal"] = cls.validate_mal(config["mal_client_id"])
        if config.get("trakt_client_id"):
            results["trakt"] = cls.validate_trakt(config["trakt_client_id"])
        if config.get("opensubtitles_api_key"):
            results["opensubtitles"] = cls.validate_opensubtitles(config["opensubtitles_api_key"])
        if config.get("lastfm_api_key"):
            results["lastfm"] = cls.validate_lastfm(config["lastfm_api_key"])
        return results
