import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.gui.app import App


def test_better_posters_tv_and_movie_artwork_url():
    app = App.__new__(App)
    app.config = {
        "rpc_large_image_mode": "episode",
        "artwork_provider": "better_posters",
        "artwork_fallback_chain": ["better_posters", "tmdb"],
        "better_posters_enabled": True,
        "better_posters_style": "auto~gr",
        "better_posters_base_url": "https://btttr.cc",
    }
    app.last_imdb_id = "tt1196946"
    app._refresh_better_posters_artwork("episode", "tv", 1, 12)
    assert app.last_better_posters_url == "https://btttr.cc/poster/series/tt1196946:1:12/auto~gr.png"

    provider, url, _fit = app._best_artwork_source_url()
    assert provider == "BETTER_POSTERS"
    assert url == "https://btttr.cc/poster/series/tt1196946:1:12/auto~gr.png"

    app.last_imdb_id = "tt0816692"
    app._refresh_better_posters_artwork("episode", "movie", None, None)
    assert app.last_better_posters_url == "https://btttr.cc/poster/movie/tt0816692/auto~gr.png"
    provider, url, _fit = app._best_artwork_source_url()
    assert provider == "BETTER_POSTERS"
    assert url == "https://btttr.cc/poster/movie/tt0816692/auto~gr.png"
