import unittest
import sys
import os
from unittest.mock import MagicMock, patch

# Ensure the src directory is in the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.gui.app import App
from src.core.top_posters import TopPostersClient

class TestTopPostersModes(unittest.TestCase):
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
        # Disable background threads and networking in App.__init__
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
            self.app.tmdb = MagicMock()
            self.app.top_posters = MagicMock()
            
            # Mock the availability check to always return True for Top Posters
            self.app._top_posters_artwork_available = MagicMock(return_value=True)
            
            # Mock _proxy_rpc_image to just return the URL (bypass cache/upload logic)
            self.app._proxy_rpc_image = MagicMock(side_effect=lambda url, **kwargs: url)

    def test_desktop_mode_top_posters(self):
        """Tests Top Posters in Desktop mode."""
        status = {
            "active": True,
            "title": "Breaking Bad",
            "season": 1,
            "episode": 1,
            "episode_title": "Pilot",
            "state": "playing",
            "position": 1000,
            "duration": 3000000,
            "app": "Stremio Desktop"
        }
        
        # Simulate Metadata Lookup
        self.app.last_meta = {"imdb_id": "tt0903747", "id": 1396, "type": "tv"}
        self.app.last_imdb_id = "tt0903747"
        self.app.shared_state["title"] = "Breaking Bad"
        
        # Mock Top Posters URL
        expected_url = "https://api.top-posters.com/test_key/imdb/thumbnail/tt0903747/S01E01.jpg?badge_size=medium&badge_position=bottom-left&blur=false"
        self.app.top_posters.build_thumbnail_url.return_value = expected_url
        self.app.top_posters.is_enabled.return_value = True

        # Perform Refresh
        self.app._refresh_rpc_artwork(status)

        # Build Payload as Desktop
        with patch('platform.release', return_value="11"):
            payload = self.app._build_rpc_payload("Breaking Bad", status, "Stremio Desktop")

        print(f"Desktop Payload Image: {payload.get('image_url')}")
        self.assertEqual(payload.get('image_url'), expected_url)
        self.assertIn("Windows 11", payload.get("small_text"))
        print("Desktop Mode [SUCCESS]")

    def test_adb_mode_top_posters(self):
        """Tests Top Posters in ADB (Android) Mode."""
        status = {
            "playing": True,
            "state": "playing",
            "title": "Breaking Bad S01E01",
            "season": 1,
            "episode": 1,
            "position": 1000,
            "duration": 3000000,
            "app": "com.stremio.one",
            "focus": "com.stremio.one"
        }

        # Simulate Metadata Lookup
        self.app.last_meta = {"imdb_id": "tt0903747", "id": 1396, "type": "tv"}
        self.app.last_imdb_id = "tt0903747"
        self.app.shared_state["title"] = "Breaking Bad"
        self.app.device_name = "NVIDIA SHIELD TV"
        
        # Mock Top Posters URL
        expected_url = "https://api.top-posters.com/test_key/imdb/thumbnail/tt0903747/S01E01.jpg?badge_size=medium&badge_position=bottom-left&blur=false"
        self.app.top_posters.build_thumbnail_url.return_value = expected_url
        self.app.top_posters.is_enabled.return_value = True

        # Perform Refresh
        self.app._refresh_rpc_artwork(status)

        # Build Payload as Android
        payload = self.app._build_rpc_payload("Breaking Bad", status, "com.stremio.one")

        print(f"ADB Payload Image: {payload.get('image_url')}")
        self.assertEqual(payload.get('image_url'), expected_url)
        self.assertIn("NVIDIA SHIELD TV", payload.get("small_text"))
        print("ADB Mode [SUCCESS]")

    def test_movie_mode_top_posters(self):
        """Tests Top Posters for Movies (fallback to show poster)."""
        status = {
            "active": True,
            "title": "Interstellar",
            "state": "playing",
            "position": 1000,
            "duration": 7200000,
            "app": "Stremio Desktop"
        }
        
        # Simulate Metadata Lookup
        self.app.last_meta = {"imdb_id": "tt0816692", "id": 157336, "type": "movie"}
        self.app.last_imdb_id = "tt0816692"
        self.app.shared_state["title"] = "Interstellar"
        
        # Mock Top Posters URL
        expected_url = "https://api.top-posters.com/test_key/imdb/poster/tt0816692.jpg?style=modern"
        self.app.top_posters.build_poster_url.return_value = expected_url
        self.app.top_posters.is_enabled.return_value = True

        # Perform Refresh
        self.app._refresh_rpc_artwork(status)

        # Build Payload
        payload = self.app._build_rpc_payload("Interstellar", status, "Stremio Desktop")

        print(f"Movie Payload Image: {payload.get('image_url')}")
        self.assertEqual(payload.get('image_url'), expected_url)
        print("Movie Mode [SUCCESS]")

if __name__ == '__main__':
    unittest.main()
