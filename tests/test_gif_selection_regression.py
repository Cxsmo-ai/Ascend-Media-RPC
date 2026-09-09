import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.config import DEFAULT_CONFIG
from src.gui.app import App
from src.core.config import load_config


def test_default_tv_chain_uses_streaming_before_generic_gif_fallbacks():
    chain = DEFAULT_CONFIG["rpc_small_icon_tv_chain"]
    assert chain.index("network_gif") < chain.index("streaming_gif")
    assert chain.index("streaming_gif") < chain.index("genre_gif")


def test_mentalist_uses_streaming_gif_when_cbs_has_no_ultramax_asset():
    app = App.__new__(App)
    app.config = {
        "rpc_small_icon_mode": "content_network_gif",
        "rpc_small_icon_tv_chain": DEFAULT_CONFIG["rpc_small_icon_tv_chain"],
    }
    app.last_media_type = "tv"
    app.last_original_networks = ["CBS"]
    app.last_streaming_networks = ["Paramount+", "Hulu"]
    app.last_network_name = "CBS"
    app.last_network_image_url = "https://image.tmdb.org/t/p/w780/cbs.png"
    app.last_production_companies = []
    app.last_genres = ["Drama"]
    app.last_cast = ["Simon Baker"]
    app.shared_state = {}

    url, label = app._small_rpc_art("playing", "com.nuvio.tv.test")

    assert url == "https://ultramax.vip/images/Paramount.gif"
    assert label == "Paramount+"


def test_load_config_repairs_legacy_tv_chain(tmp_path, monkeypatch):
    config_path = Path(tmp_path) / "config.json"
    config_path.write_text(
        json.dumps({
            "rpc_small_icon_tv_chain": [
                "network_gif", "genre_gif", "actor_gif", "network_logo", "poster", "app"
            ]
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("ASCEND_CONFIG_PATH", str(config_path))

    config = load_config()

    assert config["rpc_small_icon_tv_chain"][:3] == [
        "network_gif", "streaming_gif", "genre_gif"
    ]
