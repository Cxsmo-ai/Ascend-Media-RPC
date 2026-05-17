import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests

from src.core.nuvio import NuvioCoversClient


def test_refresh_failures_open_five_minute_circuit():
    client = NuvioCoversClient(
        token="",
        email="user@example.com",
        password="secret",
        outage_failure_threshold=2,
        outage_cooldown_seconds=300,
    )

    with patch("src.core.nuvio.time.time", return_value=1000), \
         patch("src.core.nuvio.requests.post", side_effect=requests.exceptions.Timeout("down")) as post:
        assert client.find_popular_gif("AMC") is None
        assert client.find_popular_gif("AMC") is None
        assert client.find_popular_gif("AMC") is None

    assert post.call_count == 2
    assert client._nuvio_outage_until == 1300


def test_lookup_failures_open_five_minute_circuit():
    client = NuvioCoversClient(
        token="token",
        outage_failure_threshold=2,
        outage_cooldown_seconds=300,
    )

    with patch("src.core.nuvio.time.time", return_value=2000), \
         patch.object(client.session, "get", side_effect=requests.exceptions.Timeout("down")) as get:
        assert client.find_popular_gif("AMC") is None
        assert client.find_popular_gif("AMC") is None
        assert client.find_popular_gif("AMC") is None

    assert get.call_count == 2
    assert client._nuvio_outage_until == 2300


def test_success_resets_failure_count():
    client = NuvioCoversClient(
        token="token",
        outage_failure_threshold=2,
        outage_cooldown_seconds=300,
    )

    class Response:
        status_code = 200

        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"items": []}

    client._record_nuvio_failure("first")
    with patch.object(client.session, "get", return_value=Response()):
        assert client.find_popular_gif("AMC") is None

    assert client._nuvio_failure_count == 0
    assert client._nuvio_outage_until == 0
