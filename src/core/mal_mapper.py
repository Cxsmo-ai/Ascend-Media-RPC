import requests
import logging
import urllib.parse

class MalMapper:
    BASE_URL = "https://api.myanimelist.net/v2/anime"

    def __init__(self, client_id):
        self.logger = logging.getLogger(__name__)
        self.client_id = client_id

    def search_anime(self, title):
        """
        Searches MAL for an anime by title and returns the ID of the first match.
        Returns: int (MAL ID) or None
        """
        if not self.client_id:
            self.logger.warning("No MAL Client ID provided. Cannot search MAL.")
            return None

        headers = {
            "X-MAL-CLIENT-ID": self.client_id
        }
        
        # Simple search
        # q: search query, limit: 1 (we hope the first match is correct)
        params = {
            "q": title,
            "limit": 1
        }
        
        try:
            response = requests.get(self.BASE_URL, headers=headers, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                data_list = data.get("data", [])
                if data_list:
                    # Return the ID of the first result
                    return data_list[0].get("node", {}).get("id")
                else:
                    return None
            elif response.status_code == 403:
                self.logger.error("MAL API Authentication Failed. Check Client ID.")
                return None
            else:
                self.logger.warning(f"MAL API Error {response.status_code}: {response.text}")
                return None
        except Exception as e:
            self.logger.error(f"Failed to connect to MAL API: {e}")
            return None

    def get_anime_details(self, mal_id):
        """
        Fetches details (title, main_picture) for a specific MAL ID.
        Returns: { "title": str, "image_url": str } or None
        """
        if not self.client_id or not mal_id:
            return None
            
        url = f"{self.BASE_URL}/{mal_id}"
        headers = { "X-MAL-CLIENT-ID": self.client_id }
        # Request specific fields to save bandwidth
        params = { "fields": "title,main_picture" }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                title = data.get("title")
                image_url = data.get("main_picture", {}).get("large") or data.get("main_picture", {}).get("medium")
                return { "title": title, "image_url": image_url }
            else:
                self.logger.warning(f"MAL Details Error {response.status_code}")
                return None
        except Exception as e:
            self.logger.error(f"Failed to fetch MAL details: {e}")
            return None
