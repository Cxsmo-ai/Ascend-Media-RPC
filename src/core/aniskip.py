import requests
import logging

class AniskipClient:
    BASE_URL = "https://api.aniskip.com/v2"

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_skip_times(self, mal_id, episode_number):
        """
        Fetches skip times from Aniskip API.
        Returns a list of tuples: [(start_time, end_time), ...] or None if failed/empty.
        """
        url = f"{self.BASE_URL}/skip-times/{mal_id}/{episode_number}"
        params = {
            "types": ["op", "ed"], 
            "episodeLength": 0 # Optional but good practice
        }
        
        try:
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("found"):
                    results = []
                    for skip in data.get("results", []):
                        # skip['interval'] contains {'startTime': X, 'endTime': Y}
                        start = skip.get("interval", {}).get("startTime")
                        end = skip.get("interval", {}).get("endTime")
                        skip_type = skip.get("skipType") # "op" or "ed" usually
                        
                        # Map API type to readable type
                        type_str = "intro"
                        if skip_type == "ed":
                             type_str = "outro"
                        elif skip_type == "op":
                             type_str = "intro"
                        
                        if start is not None and end is not None:
                            results.append({"start": start, "end": end, "type": type_str})
                    return results if results else None
            elif response.status_code == 404:
                # Not found is normal
                return None
            else:
                self.logger.warning(f"Aniskip API Error {response.status_code}: {response.text}")
                return None
        except Exception as e:
            self.logger.error(f"Failed to connect to Aniskip: {e}")
            return None
