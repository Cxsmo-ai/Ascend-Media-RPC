import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAniListClient:
    def test_init(self):
        from src.core.integrations.anilist import AniListClient
        client = AniListClient(access_token="test")
        assert client.access_token == "test"

    def test_no_update_without_token(self):
        from src.core.integrations.anilist import AniListClient
        client = AniListClient()
        assert client.update_progress(123, 1) is False


class TestSimklClient:
    def test_init(self):
        from src.core.integrations.simkl import SimklClient
        client = SimklClient(client_id="test_id")
        assert client.client_id == "test_id"

    def test_no_scrobble_without_token(self):
        from src.core.integrations.simkl import SimklClient
        client = SimklClient()
        assert client.scrobble({"movie": {"title": "Test"}}, 50) is False


class TestKitsuClient:
    def test_init(self):
        from src.core.integrations.kitsu import KitsuClient
        client = KitsuClient(access_token="test")
        assert client.access_token == "test"

    def test_no_update_without_token(self):
        from src.core.integrations.kitsu import KitsuClient
        client = KitsuClient()
        assert client.update_progress("123", 1) is False


class TestLastFMClient:
    def test_init(self):
        from src.core.integrations.lastfm import LastFMClient
        client = LastFMClient(api_key="key", api_secret="secret")
        assert client.api_key == "key"

    def test_no_scrobble_without_session(self):
        from src.core.integrations.lastfm import LastFMClient
        client = LastFMClient()
        assert client.scrobble("Artist", "Track") is False


class TestFanArtClient:
    def test_init(self):
        from src.core.integrations.fanart import FanArtClient
        client = FanArtClient(api_key="test")
        assert client.api_key == "test"

    def test_no_images_without_key(self):
        from src.core.integrations.fanart import FanArtClient
        client = FanArtClient()
        assert client.get_movie_images("123") is None
        assert client.get_best_poster("123") is None


class TestLetterboxdClient:
    def test_init(self):
        from src.core.integrations.letterboxd import LetterboxdClient
        client = LetterboxdClient(api_key="test")
        assert client.api_key == "test"


class TestJustWatchClient:
    def test_init(self):
        from src.core.integrations.justwatch import JustWatchClient
        client = JustWatchClient(country="US")
        assert client.country == "US"


class TestMediaServerClients:
    def test_plex_init(self):
        from src.core.integrations.media_server import PlexClient
        client = PlexClient(url="http://localhost:32400", token="test")
        assert client.url == "http://localhost:32400"

    def test_jellyfin_init(self):
        from src.core.integrations.media_server import JellyfinClient
        client = JellyfinClient(url="http://localhost:8096", api_key="test")
        assert client.url == "http://localhost:8096"

    def test_plex_no_sessions_without_config(self):
        from src.core.integrations.media_server import PlexClient
        client = PlexClient()
        assert client.get_sessions() == []

    def test_jellyfin_no_sessions_without_config(self):
        from src.core.integrations.media_server import JellyfinClient
        client = JellyfinClient()
        assert client.get_sessions() == []


class TestNotionObsidian:
    def test_notion_init(self):
        from src.core.integrations.notion_obsidian import NotionWatchLog
        client = NotionWatchLog(api_key="test", database_id="db123")
        assert client.api_key == "test"

    def test_obsidian_init(self):
        from src.core.integrations.notion_obsidian import ObsidianWatchLog
        client = ObsidianWatchLog(vault_path="/tmp/vault")
        assert client.vault_path == "/tmp/vault"

    def test_notion_no_entry_without_config(self):
        from src.core.integrations.notion_obsidian import NotionWatchLog
        client = NotionWatchLog()
        assert client.create_entry("Test") is False
