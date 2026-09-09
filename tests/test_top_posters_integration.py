import unittest
import sys
import os
from unittest.mock import MagicMock, patch

# Ensure the src directory is in the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.gui.app import App
from src.core.top_posters import TopPostersClient

class TestTopPostersIntegration(unittest.TestCase):
    def setUp(self):
        self.test_config = {
            "top_posters_enabled": True,
            "top_posters_api_key": "test_key",
            "top_posters_style": "modern",
            "rpc_large_image_mode": "episode",
            "artwork_fallback_chain": ["top_posters", "tmdb"],
            "rpc_small_icon_mode": "streaming_service",
            "rpc_branding": "on Stremio",
            "top_posters_badge_size": "medium",
            "top_posters_badge_position": "bottom-left",
            "top_posters_blur": False,
            "artwork_provider": "top_posters",
            "adb_host": "127.0.0.1",
            "adb_port": 5555,
            "stremio_desktop_enabled": True
        }
        
        # Patch App initialization
        with patch('src.gui.app.load_config', return_value=self.test_config), \
             patch('src.gui.app.DiscordRPC'), \
             patch('src.gui.app.TMDBClient'), \
             patch('src.gui.app.StremioDesktopWatcher'), \
             patch('src.gui.app.SkipManager'), \
             patch('src.gui.app.ConfigWatcher'), \
             patch('src.gui.app.ADBDiscovery'), \
             patch('src.gui.app.TraktClient'), \
             patch('src.gui.app.App.start_gui'), \
             patch('src.gui.app.threading.Thread'):
            
            self.app = App()
            # Real TopPostersClient
            self.app.top_posters = TopPostersClient(self.test_config)
            
            # Mock TMDB
            self.app.tmdb = MagicMock()
            
            # Mock proxying - return string
            self.app._proxy_rpc_image = MagicMock(side_effect=lambda url, **kwargs: str(url))

    @patch('requests.Session.request')
    def test_full_artwork_chain_success(self, mock_request):
        """Tests the full chain when Top Posters API returns 200 OK."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "image/jpeg"}
        mock_request.return_value = mock_resp

        status = {
            "active": True,
            "title": "Breaking Bad",
            "season": 1,
            "episode": 1,
            "state": "playing",
            "app": "Stremio Desktop",
            "id": 1396
        }
        
        self.app.last_meta = {"id": 1396, "imdb_id": "tt0903747", "type": "tv"}
        self.app.last_imdb_id = "tt0903747"
        self.app.shared_state["title"] = "Breaking Bad"
        
        self.app._refresh_rpc_artwork(status)
        
        self.assertIsNotNone(self.app.last_top_posters_episode_url)
        self.assertIn("1396", self.app.last_top_posters_episode_url)
        
        payload = self.app._build_rpc_payload("Breaking Bad", status, "Stremio Desktop")
        print(f"Chain Success Image: {payload.get('image_url')}")
        self.assertTrue(str(payload.get('image_url')).startswith("https://api.top-posters.com"))

    @patch('requests.Session.request')
    def test_full_artwork_chain_fallback_to_tmdb(self, mock_request):
        """Tests fallback to TMDB when Top Posters returns 404."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_request.return_value = mock_resp

        status = {
            "active": True,
            "title": "Unknown Show",
            "season": 1,
            "episode": 1,
            "state": "playing",
            "app": "Stremio Desktop",
            "id": 12345
        }
        
        self.app.last_meta = {"id": 12345, "imdb_id": "tt1234567", "type": "tv"}
        self.app.last_imdb_id = "tt1234567"
        self.app.shared_state["title"] = "Unknown Show"
        
        # Mock TMDB to return specific image
        self.app.tmdb.get_season_details.return_value = {"image_url": "https://tmdb.org/fallback.jpg"}
        
        self.app._refresh_rpc_artwork(status)
        
        payload = self.app._build_rpc_payload("Unknown Show", status, "Stremio Desktop")
        print(f"Chain Fallback Image: {payload.get('image_url')}")
        self.assertEqual(payload.get('image_url'), "https://tmdb.org/fallback.jpg")

    @patch('requests.Session.request')
    def test_movie_top_posters_integration(self, mock_request):
        """Tests Movie artwork integration."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "image/jpeg"}
        mock_request.return_value = mock_resp

        status = {
            "active": True,
            "title": "Interstellar",
            "state": "playing",
            "app": "Stremio Desktop",
            "id": 157336
        }
        
        self.app.last_meta = {"id": 157336, "imdb_id": "tt0816692", "type": "movie"}
        self.app.last_imdb_id = "tt0816692"
        self.app.shared_state["title"] = "Interstellar"
        
        self.app._refresh_rpc_artwork(status)
        
        payload = self.app._build_rpc_payload("Interstellar", status, "Stremio Desktop")
        print(f"Movie Integration Image: {payload.get('image_url')}")
        self.assertTrue("157336" in str(payload.get('image_url')) or "tt0816692" in str(payload.get('image_url')))

if __name__ == '__main__':
    unittest.main()
