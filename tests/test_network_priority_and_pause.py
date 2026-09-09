import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.gui.app import App


def test_tv_original_network_gif_prioritized():
    app = App.__new__(App)
    app.config = {
        "rpc_small_icon_mode": "content_network_gif",
        "rpc_small_icon_tv_chain": ["network_gif", "streaming_gif", "studio_gif", "genre_gif", "actor_gif", "network_logo", "poster", "app"]
    }
    app.last_media_type = "tv"
    app.last_original_networks = ["HBO"]
    app.last_streaming_networks = ["Max", "Hulu"]
    app.last_network_name = "HBO"
    app.last_network_image_url = "https://image.tmdb.org/t/p/w780/hbo.png"
    app.last_genres = ["Drama"]
    app.last_cast = []
    app.shared_state = {}

    url, label = app._small_rpc_art("playing", "com.nuvio.tv.test")
    assert url == "https://ultramax.vip/images/HBO.gif"
    assert label == "HBO"


def test_tv_original_network_falls_back_to_streaming_gif_when_original_has_no_gif():
    app = App.__new__(App)
    app.config = {
        "rpc_small_icon_mode": "content_network_gif",
        "rpc_small_icon_tv_chain": ["network_gif", "streaming_gif", "studio_gif", "genre_gif", "actor_gif", "network_logo", "poster", "app"]
    }
    # The Mentalist originally aired on CBS, streaming on Paramount+ / Hulu
    app.last_media_type = "tv"
    app.last_original_networks = ["CBS"]
    app.last_streaming_networks = ["Paramount+", "Hulu"]
    app.last_network_name = "CBS"
    app.last_network_image_url = "https://image.tmdb.org/t/p/w780/cbs.png"
    app.last_genres = ["Drama", "Crime"]
    app.last_cast = ["Simon Baker"]
    app.shared_state = {}

    url, label = app._small_rpc_art("playing", "com.nuvio.tv.test")
    # CBS has no direct GIF, so streaming_gif step chooses Paramount+
    assert url == "https://ultramax.vip/images/Paramount.gif"
    assert label == "Paramount+"


def test_the_mentalist_title_guarantees_paramount_plus_as_main_streaming_gif():
    app = App.__new__(App)
    app.config = {
        "rpc_small_icon_mode": "content_network_gif",
        "rpc_small_icon_tv_chain": ["network_gif", "streaming_gif", "network_logo", "poster", "app"],
    }
    app.last_media_type = "tv"
    app.last_item = "The Mentalist"
    app.last_original_networks = []
    app.last_streaming_networks = ["Netflix", "Hulu"]
    app.shared_state = {"title": "The Mentalist"}

    url, label = app._small_rpc_art("playing", "com.nuvio.tv.test")
    assert url == "https://ultramax.vip/images/Paramount.gif"
    assert label == "Paramount+"


def test_cbs_prefers_paramount_plus_over_regional_watch_provider_order():
    app = App.__new__(App)
    app.config = {
        "rpc_small_icon_mode": "content_network_gif",
        "rpc_small_icon_tv_chain": ["network_gif", "streaming_gif", "network_logo", "poster", "app"],
    }
    app.last_media_type = "tv"
    app.last_original_networks = ["CBS"]
    app.last_streaming_networks = ["Hulu", "Netflix"]
    app.last_network_name = "CBS"
    app.last_network_image_url = "https://image.tmdb.org/t/p/w780/cbs.png"
    app.shared_state = {}

    url, label = app._small_rpc_art("playing", "com.nuvio.tv.test")

    assert url == "https://ultramax.vip/images/Paramount.gif"
    assert label == "Paramount+"


def test_tv_original_network_logo_used_when_no_streaming_gif():
    app = App.__new__(App)
    app.config = {
        "rpc_small_icon_mode": "content_network_gif",
        "rpc_small_icon_tv_chain": ["network_gif", "streaming_gif", "network_logo", "poster", "app"]
    }
    app.last_media_type = "tv"
    app.last_original_networks = ["Unknown Network XYZ"]
    app.last_streaming_networks = ["UnknownStreamer"]
    app.last_network_name = "Unknown Network XYZ"
    app.last_network_image_url = "https://image.tmdb.org/t/p/w780/cbs_eye_logo.png"
    app.last_genres = []
    app.last_cast = []
    app.shared_state = {}

    url, label = app._small_rpc_art("playing", "com.nuvio.tv.test")
    assert url == "https://image.tmdb.org/t/p/w780/cbs_eye_logo.png"
    assert label == "Unknown Network XYZ"


def test_paused_state_omits_timestamps_to_prevent_timer_drift():
    app = App.__new__(App)
    app.config = {"rpc_branding": "on Stremio", "wako_mode": False}
    app.rpc_timeline_key = None
    app.rpc_timeline_start_timestamp = 1000
    app.rpc_timeline_end_timestamp = 2000

    timestamps = app._rpc_timestamps("The Mentalist", {"state": "paused", "position": 30000, "duration": 120000}, "com.nuvio.tv.test")
    assert timestamps == {}
    assert app.rpc_timeline_start_timestamp is None
    assert app.rpc_timeline_end_timestamp is None


def test_playing_state_generates_precise_timestamps():
    app = App.__new__(App)
    app.config = {"rpc_branding": "on Stremio", "wako_mode": False}
    app.rpc_timeline_key = None
    app.rpc_timeline_start_timestamp = None
    app.rpc_timeline_end_timestamp = None

    status = {"state": "playing", "position": 30000, "duration": 120000, "calc_time": 1000.0}
    timestamps = app._rpc_timestamps("The Mentalist", status, "com.nuvio.tv.test")
    assert timestamps["start_timestamp"] == 970
    assert timestamps["end_timestamp"] == 970 + 120

