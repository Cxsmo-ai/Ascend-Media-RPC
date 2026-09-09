import os
import sys
import io

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.network_gifs import NetworkGifsClient, DEFAULT_NETWORK_GIFS
from src.core.nuvio import NuvioCoversClient


def test_network_gifs_direct_link_resolution():
    client = NetworkGifsClient()

    netflix = client.find_popular_gif("Netflix")
    assert netflix is not None
    assert netflix["image_url"] == DEFAULT_NETWORK_GIFS["netflix"]["image_url"]

    hbo = client.find_popular_gif("HBO Max")
    assert hbo is not None
    assert "ultramax.vip" in hbo["image_url"]

    disney = client.find_popular_gif("Disney+")
    assert disney is not None
    assert "ultramax.vip" in disney["image_url"]


def test_network_gifs_custom_mapping():
    client = NetworkGifsClient(custom_mappings={
        "custom net": "https://example.com/custom.gif"
    })
    res = client.find_popular_gif("Custom Net")
    assert res is not None
    assert res["image_url"] == "https://example.com/custom.gif"


def test_nuvio_backwards_compatibility_shim():
    client = NuvioCoversClient()
    hulu = client.find_popular_gif("Hulu")
    assert hulu is not None
    assert "ultramax.vip" in hulu["image_url"]
    assert client._nuvio_backoff_active() is False


def test_ultramax_mapping_does_not_substitute_another_network():
    client = NetworkGifsClient()

    assert client.find_popular_gif("Hulu")["image_url"] == "https://ultramax.vip/images/Hulu.gif"
    assert client.find_popular_gif("Paramount+")["image_url"] == "https://ultramax.vip/images/Paramount.gif"
    assert client.find_popular_gif("BritBox")["image_url"] == "https://ultramax.vip/images/Brit.gif"
    assert client.find_popular_gif("Showtime") is None
    assert client.find_popular_gif("BBC") is None


class _ImageResponse:
    def __init__(self, body: bytes, content_type: str):
        self.status_code = 200
        self.headers = {"Content-Type": content_type}
        self.raw = io.BytesIO(body)

    def close(self):
        self.raw.close()


class _ImageSession:
    def __init__(self, response):
        self.response = response

    def get(self, *args, **kwargs):
        return self.response


def test_live_validation_accepts_gif_and_rejects_html_challenge():
    gif_client = NetworkGifsClient(
        session=_ImageSession(_ImageResponse(b"GIF89a" + b"\x00" * 8, "image/gif")),
        verify_urls=True,
    )
    assert gif_client.find_popular_gif("Netflix") is not None

    html_client = NetworkGifsClient(
        session=_ImageSession(_ImageResponse(b"<html>challenge</html>", "text/html")),
        verify_urls=True,
    )
    assert html_client.find_popular_gif("Netflix") is None


def test_live_validation_rejects_static_jpeg_disguised_as_gif():
    jpeg_client = NetworkGifsClient(
        session=_ImageSession(_ImageResponse(b"\xff\xd8\xff\xe0" + b"\x00" * 8, "image/jpeg")),
        verify_urls=True,
    )
    assert jpeg_client.find_popular_gif("Drama") is None
