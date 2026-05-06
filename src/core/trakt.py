import requests
import time
import logging

logger = logging.getLogger("stremio-rpc")

class TraktClient:
    BASE_URL = "https://api.trakt.tv"
    # Using a dedicated Client ID for Stremio RPC (or placeholder)
    # Ideally should be passed in config, but we need a default for ease of use.
    # This is a public simplified ID if available, otherwise user must supply.
    # For now, we will require the user to input one or use a placeholder they can swap.
    DEFAULT_CLIENT_ID = "" 
    
    def __init__(self, client_id=None, client_secret=None, access_token=None, refresh_token=None):
        self.client_id = client_id or self.DEFAULT_CLIENT_ID
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.headers = {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": self.client_id
        }
        if self.access_token:
            self.headers["Authorization"] = f"Bearer {self.access_token}"

    def set_auth(self, access_token, refresh_token):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.headers["Authorization"] = f"Bearer {self.access_token}"

    def get_device_code(self):
        """Initiate Device Auth Flow"""
        url = f"{self.BASE_URL}/oauth/device/code"
        payload = {"client_id": self.client_id}
        try:
            r = requests.post(url, json=payload, timeout=10)
            r.raise_for_status()
            return r.json() # Returns {user_code, verification_url, device_code, interval, expires_in}
        except Exception as e:
            logger.error(f"Trakt Auth Init Failed: {e}")
            return None

    def poll_for_token(self, device_code, interval=5):
        """Poll for the user to authorize"""
        url = f"{self.BASE_URL}/oauth/device/token"
        payload = {
            "code": device_code,
            "client_id": self.client_id,
            "client_secret": self.client_secret 
        }
        
        # Trakt requires client_secret for `device/token` exchange? 
        # Actually for device flow it often does.
        # If the user doesn't have a secret (public app), check docs.
        # Docs say: client_secret is required.
        
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                return r.json() # {access_token, refresh_token, ...}
            elif r.status_code == 400:
                return "pending"
            elif r.status_code == 404:
                return "invalid_code"
            elif r.status_code == 409:
                return "already_used"
            elif r.status_code == 410:
                return "expired"
            elif r.status_code == 418:
                return "denied"
            elif r.status_code == 429:
                return "slow_down"
            
            return None
        except Exception as e:
            logger.error(f"Trakt Poll Error: {e}")
            return None

    def lookup_id(self, imdb_id=None, tmdb_id=None, media_type="movie"):
        """Convert external ID to Trakt ID object (summary)"""
        if not imdb_id and not tmdb_id: return None
        
        # Search endpoint
        # media_type: movie, show, episode
        
        search_type = "movie" if media_type == "movie" else "episode" 
        # If it's an episode, we usually scrobble the episode, but the lookup might be by Show IMDB?
        # If we have Show IMDB + Season + Episode, we need to find the specific episode.
        
        # Better approach: 
        # /search/imdb/{id}?type={type}
        
        lookup_type = "movie" if media_type == "movie" else "show"
        id_val = imdb_id or tmdb_id
        id_provider = "imdb" if imdb_id else "tmdb"
        
        url = f"{self.BASE_URL}/search/{id_provider}/{id_val}"
        params = {"type": lookup_type}
        
        try:
            r = requests.get(url, params=params, headers=self.headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data:
                    return data[0].get(lookup_type) # The movie/show object
            return None
        except Exception as e:
            logger.error(f"Trakt Lookup Failed: {e}")
            return None
            
    def get_episode(self, show_trakt_id, season, episode):
        """Get specific episode info including IDs"""
        url = f"{self.BASE_URL}/shows/{show_trakt_id}/seasons/{season}/episodes/{episode}"
        try:
            r = requests.get(url, headers=self.headers, timeout=5)
            if r.status_code == 200:
                return r.json()
            return None
        except:
            return None

    def scrobble(self, action, media_data, progress, app_version="1.0.0"):
        """
        action: start, pause, stop
        media_data: dict containing keys for 'movie' or 'episode' with 'ids'
        progress: float 0-100
        """
        if not self.access_token: return
        
        # Circuit breaker: stop attempting after repeated auth failures
        if getattr(self, "_auth_failures", 0) >= 3:
            return
        
        url = f"{self.BASE_URL}/scrobble/{action}"
        payload = {
            "progress": progress,
            "app_version": app_version,
            "date": time.strftime("%Y-%m-%d")
        }
        
        if "movie" in media_data:
            payload["movie"] = media_data["movie"]
        
        if "episode" in media_data:
            payload["episode"] = media_data["episode"]
            
        if "show" in media_data:
            payload["show"] = media_data["show"]
            
        try:
            r = requests.post(url, json=payload, headers=self.headers, timeout=5)
            if r.status_code in [201, 200]:
                self._auth_failures = 0  # Reset on success
                return r.json()
            elif r.status_code == 403:
                self._auth_failures = getattr(self, "_auth_failures", 0) + 1
                if self._auth_failures >= 3:
                    logger.warning(f"Trakt: Token expired or revoked (3x 403). Disabling scrobble. Re-authenticate in Settings.")
                else:
                    logger.warning(f"Trakt Scrobble {action} Failed: 403 ({self._auth_failures}/3)")
            else:
                logger.warning(f"Trakt Scrobble {action} Failed: {r.status_code}")
        except Exception as e:
            logger.error(f"Trakt Scrobble Error: {e}")

    def get_user_lists(self):
        """Fetch Watchlist, Personal Lists, and Liked Lists"""
        if not self.access_token: return []
        
        lists = []
        
        # 1. Watchlist (Synthetic)
        try:
            # We don't get metadata for watchlist from an endpoint easily, so we mock it
            # Or assume it exists.
            lists.append({
                "name": "Watchlist",
                "ids": {"trakt": "watchlist", "slug": "watchlist"},
                "item_count": "?",
                "type": "watchlist",
                "user": {"username": "me"}
            })
        except: pass

        # 2. Personal Lists
        try:
            r = requests.get(f"{self.BASE_URL}/users/me/lists", headers=self.headers, timeout=5)
            if r.status_code == 200:
                for l in r.json():
                    l["type"] = "personal"
                    lists.append(l)
        except Exception as e:
            logger.error(f"Trakt Lists Error: {e}")

        # 3. Liked Lists
        try:
            r = requests.get(f"{self.BASE_URL}/users/me/likes/lists", headers=self.headers, timeout=5)
            if r.status_code == 200:
                for item in r.json():
                    if "list" in item:
                        l = item["list"]
                        l["type"] = "liked"
                        # Ensure user info is attached for fetching items later
                        lists.append(l)
        except Exception as e:
            logger.error(f"Trakt Liked Lists Error: {e}")
            
        return lists

    def get_list_items(self, list_id, username="me"):
        """Fetch items from a list."""
        if not self.access_token: return []
        
        url = ""
        if list_id == "watchlist":
            url = f"{self.BASE_URL}/sync/watchlist/movies,shows" # Get all
            # Sorting: usually adding /added
            url += "/added" 
        else:
            url = f"{self.BASE_URL}/users/{username}/lists/{list_id}/items"
            
        try:
            r = requests.get(url, headers=self.headers, timeout=10)
            if r.status_code == 200:
                return r.json()
            else:
                logger.warning(f"Fetch List Items {list_id} failed: {r.status_code}")
                return []
        except Exception as e:
            logger.error(f"Fetch List Items Error: {e}")
            return []
