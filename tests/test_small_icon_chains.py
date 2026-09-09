import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.gui.app import App


def test_tv_small_icon_fallback_chain():
    app = App.__new__(App)
    app.config = {
        "rpc_small_icon_mode": "content_network_gif",
        "rpc_small_icon_tv_chain": ["network_gif", "genre_gif", "actor_gif", "network_logo", "poster", "app"],
        "rpc_small_icon_movie_chain": ["studio_gif", "network_gif", "genre_gif", "actor_gif", "network_logo", "poster", "app"]
    }
    app.last_media_type = "tv"
    app.last_network_name = "Netflix"
    app.last_genres = ["Drama", "Sci-Fi"]
    app.last_cast = ["Millie Bobby Brown"]
    app.shared_state = {}

    url, label = app._small_rpc_art("playing", "com.stremio")
    assert url is not None
    assert "netflix" in url.lower() or "ultramax.vip" in url.lower()


def test_movie_small_icon_fallback_chain():
    app = App.__new__(App)
    app.config = {
        "rpc_small_icon_mode": "content_network_gif",
        "rpc_small_icon_tv_chain": ["network_gif", "genre_gif", "actor_gif", "network_logo", "poster", "app"],
        "rpc_small_icon_movie_chain": ["studio_gif", "network_gif", "genre_gif", "actor_gif", "network_logo", "poster", "app"]
    }
    app.last_media_type = "movie"
    app.last_network_name = "Warner Bros"
    app.last_genres = ["Action", "Adventure"]
    app.last_cast = ["Tom Holland"]
    app.shared_state = {}

    url, label = app._small_rpc_art("playing", "com.stremio")
    assert url is not None
    assert "warner_bros" in url.lower() or "ultramax.vip" in url.lower()


def test_genre_fallback_when_network_gif_missing():
    app = App.__new__(App)
    app.config = {
        "rpc_small_icon_mode": "content_network_gif",
        "rpc_small_icon_tv_chain": ["network_gif", "genre_gif", "actor_gif", "network_logo", "poster", "app"],
    }
    app.last_media_type = "tv"
    app.last_network_name = "Unknown Network XYZ"
    app.last_genres = ["Anime"]
    app.last_cast = []
    app.shared_state = {}

    url, label = app._small_rpc_art("playing", "com.stremio")
    assert url is not None
    assert "anime" in url.lower() or "ultramax.vip" in url.lower()


def test_rpc_uses_ultramax_even_when_nuvio_is_enabled():
    app = App.__new__(App)
    app.config = {
        "rpc_small_icon_mode": "content_network_gif",
        "network_gifs_enabled": True,
        "network_gifs_validate_urls": False,
        "nuvio_covers_enabled": True,
        "rpc_small_icon_tv_chain": ["network_gif", "app"],
    }
    app.network_gifs = None
    app.nuvio_covers = object()  # A configured Nuvio client must not win RPC selection.
    app.last_media_type = "tv"
    app.last_network_name = "Hulu"
    app.shared_state = {}

    url, label = app._small_rpc_art("playing", "com.nuvio.tv.test")
    assert url == "https://ultramax.vip/images/Hulu.gif"
    assert label == "Hulu"
