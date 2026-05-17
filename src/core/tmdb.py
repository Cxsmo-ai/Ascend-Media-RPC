import logging
import requests
import re
import urllib.parse
from typing import Optional, Dict
from PIL import Image
from io import BytesIO

logger = logging.getLogger("stremio-rpc")

class TMDBClient:
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w780"
    CINEMETA_BASE_URL = "https://v3-cinemeta.strem.io"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.cache = {}
        self.genre_map = {"movie": {}, "tv": {}}
        self._fetch_genres()

    def _fetch_genres(self):
        """Pre-fetch genre mappings for movies and TV shows"""
        if not self.api_key: return
        try:
            for mtype in ["movie", "tv"]:
                resp = self.session.get(f"{self.BASE_URL}/genre/{mtype}/list", params={"api_key": self.api_key})
                if resp.status_code == 200:
                    for g in resp.json().get("genres", []):
                        self.genre_map[mtype][g["id"]] = g["name"]
        except: pass

    def get_full_details(self, media_id: int, media_type: str) -> Optional[Dict]:
        """Fetch rich details including cast, genres, and ratings"""
        if not self.api_key or not media_id: return None
        try:
            url = f"{self.BASE_URL}/{media_type}/{media_id}"
            params = {
                "api_key": self.api_key,
                "append_to_response": "credits,external_ids"
            }
            resp = self.session.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            genres = [g.get("name") for g in data.get("genres", [])]
            cast = [c.get("name") for c in data.get("credits", {}).get("cast", [])[:3]] # Top 3
            imdb_id = data.get("external_ids", {}).get("imdb_id")
            
            network_logo = None
            network_name = None
            if media_type == "tv" and data.get("networks"):
                network = data["networks"][0]
                logo_path = network.get("logo_path")
                network_name = network.get("name")
                if logo_path: network_logo = f"{self.IMAGE_BASE_URL}{logo_path}"
            elif media_type == "movie" and data.get("production_companies"):
                prod = data["production_companies"][0]
                logo_path = prod.get("logo_path")
                network_name = prod.get("name")
                if logo_path: network_logo = f"{self.IMAGE_BASE_URL}{logo_path}"

            return {
                "genres": genres,
                "cast": cast,
                "vote_average": data.get("vote_average"),
                "vote_count": data.get("vote_count"),
                "imdb_id": imdb_id,
                "tagline": data.get("tagline"),
                "network_logo": network_logo,
                "network_name": network_name,
                "runtime": data.get("runtime"),
                "episode_run_time": data.get("episode_run_time", [])
            }
        except Exception as e:
            logger.error(f"TMDB full details failed: {e}")
            return None

    def search_content(self, query: str, media_type_hint: str = None, year: str = None) -> Optional[Dict]:
        if not query:
            return None

        cache_key = f"{query}_{media_type_hint}_{year}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        if not self.api_key:
            processed = self.search_cinemeta_content(query, media_type_hint=media_type_hint, year=year)
            if processed:
                self.cache[cache_key] = processed
            return processed

        try:
            # Determine Endpoint
            endpoint = "multi"
            if media_type_hint == "tv": endpoint = "tv"
            elif media_type_hint == "movie": endpoint = "movie"
            
            params = {
                "api_key": self.api_key,
                "query": query,
                "include_adult": False
            }
            
            if year:
                field = "first_air_date_year" if endpoint == "tv" else "primary_release_year"
                if endpoint == "multi": field = "year" # Multi-search uses 'year'
                params[field] = year

            response = self.session.get(f"{self.BASE_URL}/search/{endpoint}", params=params)
            response.raise_for_status()
            results = response.json().get("results", [])
            
            # If multi-search was used, filter/sort by hint
            if endpoint == "multi" and media_type_hint:
                results.sort(key=lambda x: 0 if x.get("media_type") == media_type_hint else 1)

            for item in results:
                # Force media_type if using specific endpoint
                m_type = item.get("media_type") or media_type_hint or ("tv" if "first_air_date" in item else "movie")
                if m_type in ["movie", "tv"]:
                    media_id = item["id"]
                    
                    try:
                        ext_resp = self.session.get(f"{self.BASE_URL}/{m_type}/{media_id}/external_ids", params={"api_key": self.api_key})
                        ext_data = ext_resp.json()
                        imdb_id = ext_data.get("imdb_id")
                    except:
                        imdb_id = None

                    item["media_type"] = m_type # Ensure it's set for _process_item
                    processed = self._process_item(item, imdb_id)
                    if not processed.get("imdb_id"):
                        cinemeta = self.search_cinemeta_content(query, media_type_hint=m_type, year=year)
                        if cinemeta and cinemeta.get("imdb_id"):
                            processed["imdb_id"] = cinemeta["imdb_id"]
                    self.cache[cache_key] = processed
                    return processed
            return None
        except Exception as e:
            logger.error(f"TMDB search failed: {e}")
            return self.search_cinemeta_content(query, media_type_hint=media_type_hint, year=year)

    def search_cinemeta_content(self, query: str, media_type_hint: str = None, year: str = None) -> Optional[Dict]:
        """No-key fallback for IMDb ids/artwork using Stremio Cinemeta catalogs."""
        if not query:
            return None
        query = str(query).strip()
        if not query:
            return None
        catalog_types = []
        if media_type_hint == "tv":
            catalog_types = [("series", "tv")]
        elif media_type_hint == "movie":
            catalog_types = [("movie", "movie")]
        else:
            catalog_types = [("series", "tv"), ("movie", "movie")]

        encoded = urllib.parse.quote(f"search={query}", safe="=")
        for catalog_type, media_type in catalog_types:
            try:
                url = f"{self.CINEMETA_BASE_URL}/catalog/{catalog_type}/top/{encoded}.json"
                response = self.session.get(url, timeout=6)
                response.raise_for_status()
                metas = response.json().get("metas", [])
                for item in metas:
                    imdb_id = self._cinemeta_imdb_id(item.get("id"))
                    if not imdb_id:
                        continue
                    release_year = self._cinemeta_year(item)
                    if year and release_year and str(year) != str(release_year):
                        continue
                    poster = item.get("poster") or item.get("background")
                    return {
                        "title": item.get("name") or query,
                        "id": None,
                        "imdb_id": imdb_id,
                        "type": media_type,
                        "year": release_year,
                        "image_url": poster,
                        "overview": item.get("description", ""),
                        "source": "cinemeta",
                    }
            except Exception as e:
                logger.debug(f"Cinemeta search failed for {catalog_type} '{query}': {e}")
        return None

    @staticmethod
    def _cinemeta_imdb_id(value: str) -> Optional[str]:
        if not value:
            return None
        match = re.search(r"(tt\d+)", str(value))
        return match.group(1) if match else None

    @staticmethod
    def _cinemeta_year(item: Dict) -> Optional[str]:
        for key in ("releaseInfo", "year", "released"):
            value = item.get(key)
            if not value:
                continue
            match = re.search(r"(19|20)\d{2}", str(value))
            if match:
                return match.group(0)
        return None

    def get_season_details(self, tv_id: int, season: int) -> Optional[Dict]:
        """Fetch specific season details including posters"""
        if not self.api_key or not tv_id: return None
        try:
            url = f"{self.BASE_URL}/tv/{tv_id}/season/{season}"
            params = {"api_key": self.api_key}
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            poster_path = data.get("poster_path")
            image_url = f"{self.IMAGE_BASE_URL}{poster_path}" if poster_path else None
            return {
                "name": data.get("name"),
                "image_url": image_url,
                "overview": data.get("overview")
            }
        except Exception as e:
            logger.error(f"TMDB Season lookup failed: {e}")
            return None

    def get_content_trailer(self, media_id: int, media_type: str) -> Optional[str]:
        """Fetch primary YouTube trailer URL"""
        if not self.api_key or not media_id: return None
        try:
            url = f"{self.BASE_URL}/{media_type}/{media_id}/videos"
            params = {"api_key": self.api_key}
            response = self.session.get(url, params=params)
            response.raise_for_status()
            videos = response.json().get("results", [])
            
            # Look for YouTube Trailer
            for v in videos:
                if v.get("site") == "YouTube" and v.get("type") == "Trailer":
                    return f"https://www.youtube.com/watch?v={v.get('key')}"
            
            # Fallback to any Teaser if no trailer
            for v in videos:
                if v.get("site") == "YouTube":
                    return f"https://www.youtube.com/watch?v={v.get('key')}"
            return None
        except Exception as e:
            logger.error(f"TMDB Trailer lookup failed: {e}")
            return None

    def get_episode_details(self, tv_id: int, season: int, episode: int) -> Optional[Dict]:
        """Fetch specific episode details"""
        if not self.api_key or not tv_id: return None
        
        try:
            url = f"{self.BASE_URL}/tv/{tv_id}/season/{season}/episode/{episode}"
            params = {"api_key": self.api_key}
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            still_path = data.get("still_path")
            image_url = f"{self.IMAGE_BASE_URL}{still_path}" if still_path else None
            
            runtime_min = data.get("runtime")
            if not runtime_min:
                # Fallback to series-level typical runtime
                series_data = self.session.get(f"{self.BASE_URL}/tv/{tv_id}", params={"api_key": self.api_key}).json()
                run_times = series_data.get("episode_run_time", [])
                runtime_min = run_times[0] if run_times else 45 # Default to 45 mins if totally unknown
            
            return {
                "name": data.get("name"),
                "overview": data.get("overview"),
                "image_url": image_url,
                "vote_average": data.get("vote_average"),
                "runtime_ms": (runtime_min or 0) * 60 * 1000,
                "season": season,
                "episode": episode
            }
        except Exception as e:
            logger.error(f"TMDB Episode lookup failed: {e}")
            return None

    def get_cinemeta_episode_details(self, series_imdb_id: str, season: int, episode: int) -> Optional[Dict]:
        if not series_imdb_id or season is None or episode is None:
            return None
        imdb_id = self._cinemeta_imdb_id(series_imdb_id)
        if not imdb_id:
            return None
        try:
            url = f"{self.CINEMETA_BASE_URL}/meta/series/{imdb_id}.json"
            response = self.session.get(url, timeout=6)
            response.raise_for_status()
            videos = response.json().get("meta", {}).get("videos", [])
            for video in videos:
                try:
                    video_season = int(video.get("season") or 0)
                    video_episode = int(video.get("episode") or 0)
                except Exception:
                    continue
                if video_season != int(season) or video_episode != int(episode):
                    continue
                thumbnail = video.get("thumbnail") or video.get("poster")
                runtime_ms = None
                if video.get("runtime"):
                    try:
                        runtime_ms = int(float(video.get("runtime")) * 60 * 1000)
                    except Exception:
                        runtime_ms = None
                return {
                    "name": video.get("title") or video.get("name"),
                    "overview": video.get("overview") or video.get("description", ""),
                    "image_url": thumbnail,
                    "runtime_ms": runtime_ms,
                    "season": int(season),
                    "episode": int(episode),
                    "source": "cinemeta",
                }
        except Exception as e:
            logger.debug(f"Cinemeta episode lookup failed for {imdb_id} S{season}E{episode}: {e}")
        return None

    def find_episode_by_name(self, tv_id: int, season: int, episode_name: str) -> Optional[Dict]:
        """Find episode by name within a season to correct numbering offsets"""
        if not self.api_key or not tv_id or not episode_name: return None
        
        try:
            url = f"{self.BASE_URL}/tv/{tv_id}/season/{season}"
            params = {"api_key": self.api_key}
            response = self.session.get(url, params=params)
            response.raise_for_status()
            episodes = response.json().get("episodes", [])
            
            clean_input = episode_name.lower().strip()
            for ep in episodes:
                if ep.get("name") and ep.get("name").lower().strip() == clean_input:
                    still_path = ep.get("still_path")
                    image_url = f"{self.IMAGE_BASE_URL}{still_path}" if still_path else None
                    return {
                        "name": ep.get("name"),
                        "overview": ep.get("overview"),
                        "image_url": image_url,
                        "vote_average": ep.get("vote_average"),
                        "runtime_ms": (ep.get("runtime", 0) or 0) * 60 * 1000,
                        "season": season,
                        "episode": ep.get("episode_number")
                    }
            return None
        except Exception as e:
            logger.error(f"TMDB Episode lookup by name failed: {e}")
            return None

    def _process_item(self, item: Dict, imdb_id: str = None) -> Dict:
        poster_path = item.get("poster_path")
        image_url = f"{self.IMAGE_BASE_URL}{poster_path}" if poster_path else None
        
        # Extract Year
        release_date = item.get("release_date") or item.get("first_air_date")
        year = release_date.split("-")[0] if release_date else None
        
        return {
            "title": item.get("title") or item.get("name"),
            "id": item["id"],
            "imdb_id": imdb_id,
            "type": item["media_type"],
            "year": year,
            "image_url": image_url,
            "overview": item.get("overview", "")
        }

    def download_image(self, url: str) -> Optional[Image.Image]:
        if not url: return None
        try:
            response = self.session.get(url, stream=True)
            response.raise_for_status()
            return Image.open(BytesIO(response.content))
        except Exception:
            return None
