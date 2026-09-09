from src.core.controller import StremioController
from src.gui.app import App


class _FakeDevice:
    def __init__(self, outputs):
        self.outputs = iter(outputs)

    def shell(self, _command):
        return next(self.outputs)


def test_episode_parser_accepts_nuvio_media_description():
    assert StremioController._parse_episode_identity(
        "The Mentalist, S1:E10 – Red Brick and Ivy, null"
    ) == (1, 10)
    assert StremioController._parse_episode_identity("Show S01E02") == (1, 2)
    assert StremioController._parse_episode_identity("Show 3x04") == (3, 4)


def test_ui_progress_parser_combines_elapsed_and_remaining_clocks():
    xml = """<hierarchy>
      <node text=\"1080p\" />
      <node text=\"S1 E10 • Red Brick and Ivy\" />
      <node text=\"0:31\" />
      <node text=\"-41:45\" />
    </hierarchy>"""

    parsed = StremioController._parse_ui_playback_metadata(xml)

    assert parsed["season"] == 1
    assert parsed["episode"] == 10
    assert parsed["position"] == 31_000
    assert parsed["duration"] == 2_536_000


def test_ui_progress_parser_ignores_non_clock_text():
    parsed = StremioController._parse_ui_playback_metadata(
        '<hierarchy><node text="The Mentalist" /></hierarchy>'
    )
    assert parsed == {"season": None, "episode": None, "duration": 0, "position": None}


def test_large_rpc_art_prefers_top_posters_then_erdb():
    app = App.__new__(App)
    app.config = {
        "rpc_large_image_mode": "episode",
        "artwork_fallback_chain": ["top_posters", "erdb", "tmdb"],
    }
    app.shared_state = {"title": "The Mentalist"}
    app.last_top_posters_episode_url = "https://api.top-posters.com/key/imdb/thumbnail/id/S01E10.jpg"
    app.last_erdb_episode_url = "https://easyratingsdb.com/token/thumbnail/realimdb:id:1:10.jpg"

    provider, url, _fit = app._best_artwork_source_url()

    assert provider == "TOP_POSTERS"
    assert url == app.last_top_posters_episode_url


def test_nuvio_duration_survives_when_controls_hide():
    media = (
        "Session package=com.nuvio.tv.test\n"
        "state=PlaybackState {state=3, position=1000, speed=1.0, updated=0}\n"
        "metadata: size=10, description=The Mentalist, S1:E10 – Red Brick and Ivy, null\n"
        "|FOCUS_DIV|\n"
        "mCurrentFocus=Window{abc u0 com.nuvio.tv.test/com.nuvio.tv.MainActivity}\n"
    )
    xml = (
        '<hierarchy><node text="S1 E10" /><node text="0:31" />'
        '<node text="-41:45" /></hierarchy>'
    )
    controller = StremioController("127.0.0.1")
    controller.connected = True
    controller.device = _FakeDevice([media, xml, media.replace("position=1000", "position=2000")])

    first = controller.get_playback_status()
    second = controller.get_playback_status()

    assert first["duration"] == 2_536_000
    assert second["duration"] == 2_536_000


def test_wako_setting_does_not_classify_nuvio_as_wako():
    app = App.__new__(App)
    app.config = {"wako_mode": True}

    assert not app._is_wako_app(
        "com.nuvio.tv.test.debug",
        {"focus": "mCurrentFocus=Window{u0 com.nuvio.tv.test.debug/com.nuvio.tv.MainActivity}"},
    )
    assert app._is_wako_app(
        "app.wako",
        {"focus": "mCurrentFocus=Window{u0 app.wako/.MainActivity}"},
    )
