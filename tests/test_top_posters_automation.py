import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.gui.app import App

class TestTopPostersAutomation(unittest.TestCase):
    def setUp(self):
        self.test_config = {
            "adb_host": "127.0.0.1",
            "adb_port": 5555,
            "top_posters_enabled": True,
            "top_posters_api_key": "test_key",
            "top_posters_style": "modern",
            "rpc_large_image_mode": "episode",
            "artwork_fallback_chain": ["top_posters", "tmdb"],
            "rpc_small_icon_mode": "streaming_service",
            "rpc_branding": "on Stremio",
            "skip_mode": "off",
            "config_hot_reload": False,
            "rpc_history_limit": 100,
            "privacy_mode": False,
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
            self.app.config = dict(self.test_config)
            self.app.tmdb = MagicMock()
            self.app.top_posters = MagicMock()
            self.app.shared_state = {"device": "Windows", "title": "Breaking Bad"}
            self.app._proxy_rpc_image = MagicMock(side_effect=lambda url, **kwargs: url)

    def test_full_top_posters_flow(self):
        """
        Tests the full flow from Stremio Desktop title detection 
        to Top Posters URL selection in the RPC payload.
        """
        status = {
            "active": True,
            "title": "Breaking Bad",
            "season": 1,
            "episode": 1,
            "episode_title": "Pilot",
            "state": "playing",
            "position": 1000,
            "duration": 3600000
        }

        self.app.last_meta = {"imdb_id": "tt0903747", "id": 1396, "type": "tv"}
        self.app.last_imdb_id = "tt0903747"

        # Mock Top Posters
        expected_url = "https://api.top-posters.com/test_key/imdb/thumbnail/tt0903747/S01E01.jpg"
        self.app.top_posters.build_thumbnail_url.return_value = expected_url
        self.app.top_posters.is_enabled.return_value = True
        self.app._top_posters_artwork_available = MagicMock(return_value=True)

        # Mock TMDB
        self.app.tmdb.get_full_details.return_value = {"network_logo": None, "network_name": None, "imdb_id": "tt0903747"}
        self.app.tmdb.get_episode_details.return_value = {"name": "Pilot", "image_url": "https://tmdb.com/p.jpg"}
        self.app.tmdb.get_season_details.return_value = {"name": "Season 1", "image_url": "https://tmdb.com/s.jpg"}

        # Perform Refresh
        self.app._refresh_rpc_artwork(status)

        # Build Payload
        with patch('platform.release', return_value="10"):
            payload = self.app._build_rpc_payload("Breaking Bad", status, "Stremio Desktop")

        # Assertions
        self.assertIn("S01E01.jpg", payload.get("image_url") or "")
        self.assertEqual(payload.get("small_image"), "https://app.strem.io/images/stremio.png")
        self.assertEqual(payload.get("small_text"), "Watching on Windows 10")

        print("\n✅ Top Posters Automation Test PASSED")
        print(f"   Payload Image: {payload.get('image_url')}")
        print(f"   Logo URL:      {payload.get('small_image')}")

if __name__ == "__main__":
    unittest.main()
