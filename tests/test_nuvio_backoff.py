import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
from src.core.nuvio import NuvioCoversClient


def test_nuvio_auth_refresh_success():
    client = NuvioCoversClient(
        base_url="https://nuvio.tv",
        email="test@example.invalid",
        password="test-password"
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "fresh_test_jwt_token_123"}

    with patch("src.core.nuvio.requests.post", return_value=mock_resp) as mock_post:
        success = client._refresh_token()
        assert success is True
        assert client.token == "fresh_test_jwt_token_123"
        assert mock_post.called


def test_nuvio_circuit_breaker():
    client = NuvioCoversClient(
        base_url="https://nuvio.tv",
        email="test@example.invalid",
        password="test-password",
        outage_failure_threshold=2,
        outage_cooldown_seconds=300
    )

    with patch("src.core.nuvio.time.time", return_value=1000), \
         patch("src.core.nuvio.requests.post", side_effect=requests.exceptions.Timeout("down")):
        client._record_nuvio_failure("timeout")
        client._record_nuvio_failure("timeout")
        assert client._nuvio_backoff_active() is True
        assert client._nuvio_outage_until == 1300


def test_nuvio_success_resets_circuit():
    client = NuvioCoversClient(base_url="https://nuvio.tv")
    client._record_nuvio_failure("first")
    client._record_nuvio_success()
    assert client._nuvio_failure_count == 0
    assert client._nuvio_outage_until == 0


def test_nuvio_anon_key_is_local_only():
    client = NuvioCoversClient(anon_key="test-local-anon-key")
    headers = client._headers()
    assert headers["apikey"] == "test-local-anon-key"
    assert NuvioCoversClient.NUVIO_ANON_KEY == ""
