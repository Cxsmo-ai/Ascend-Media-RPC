import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.trakt import TraktClient


class TestTraktClient:
    def setup_method(self):
        self.client = TraktClient(client_id="test_id", client_secret="test_secret")

    def test_init(self):
        assert self.client.client_id == "test_id"
        assert self.client.client_secret == "test_secret"
        assert self.client.access_token is None

    def test_set_auth(self):
        self.client.set_auth("token123", "refresh456", 3600)
        assert self.client.access_token == "token123"
        assert self.client.refresh_token == "refresh456"
        assert "Authorization" in self.client.headers

    def test_token_needs_refresh_no_token(self):
        assert self.client.token_needs_refresh() is False

    def test_token_needs_refresh_with_expiry(self):
        import time
        self.client.access_token = "token"
        self.client.refresh_token = "refresh"
        self.client._token_expires_at = time.time() + 100
        assert self.client.token_needs_refresh() is True

    def test_no_scrobble_without_auth(self):
        result = self.client.scrobble("start", {"movie": {"ids": {"imdb": "tt123"}}}, 50)
        assert result is None

    def test_no_collection_without_auth(self):
        result = self.client.add_to_collection({"movie": {"ids": {"imdb": "tt123"}}})
        assert result is False

    def test_no_checkin_without_auth(self):
        result = self.client.check_in({"movie": {"ids": {"imdb": "tt123"}}})
        assert result is False

    def test_no_friends_without_auth(self):
        result = self.client.get_friends_watching()
        assert result == []

    def test_no_calendar_without_auth(self):
        result = self.client.get_calendar()
        assert result == []

    def test_no_recommendations_without_auth(self):
        result = self.client.get_recommendations()
        assert result == []

    def test_no_stats_without_auth(self):
        result = self.client.get_stats()
        assert result == {}
