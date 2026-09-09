import logging
import requests
from typing import Dict, Optional, List

logger = logging.getLogger("stremio-rpc")


class JustWatchClient:
    """JustWatch integration to show streaming availability."""

    BASE_URL = "https://apis.justwatch.com/contentpartner/v2"
    GRAPHQL_URL = "https://apis.justwatch.com/graphql"

    def __init__(self, country: str = "US"):
        self.country = country.upper()

    def search(self, title: str, content_type: str = "movie") -> Optional[List[Dict]]:
        try:
            query = """
            query SearchContent($searchTerm: String!, $country: Country!, $language: Language!) {
                popularTitles(
                    country: $country
                    first: 5
                    searchTitlesFilter: { searchQuery: $searchTerm }
                    language: $language
                ) {
                    edges {
                        node {
                            id
                            objectType
                            content(country: $country, language: $language) {
                                title
                                originalReleaseYear
                                shortDescription
                                posterUrl
                            }
                            offers(country: $country, platform: WEB) {
                                monetizationType
                                presentationType
                                package {
                                    clearName
                                    icon
                                }
                                standardWebURL
                            }
                        }
                    }
                }
            }
            """
            variables = {
                "searchTerm": title,
                "country": self.country,
                "language": "en",
            }
            r = requests.post(
                self.GRAPHQL_URL,
                json={"query": query, "variables": variables},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                edges = data.get("data", {}).get("popularTitles", {}).get("edges", [])
                return [edge["node"] for edge in edges if edge.get("node")]
        except Exception as e:
            logger.error(f"JustWatch search error: {e}")
        return None

    def get_streaming_providers(self, title: str) -> List[str]:
        results = self.search(title)
        if not results:
            return []
        providers = set()
        for result in results[:1]:
            for offer in result.get("offers", []):
                pkg = offer.get("package", {})
                name = pkg.get("clearName", "")
                if name:
                    providers.add(name)
        return sorted(providers)

    def format_availability(self, title: str) -> str:
        providers = self.get_streaming_providers(title)
        if not providers:
            return ""
        return f"Also on {', '.join(providers[:3])}"
