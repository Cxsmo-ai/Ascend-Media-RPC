import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.gui.app import App


class FakeController:
    def __init__(self):
        self.lite_calls = 0
        self.full_calls = 0

    def detect_wako_player_gate(self, state="playing"):
        return {"allow_heist": True, "reason": "confirmed"}

    def execute_wako_lite_heist(self):
        self.lite_calls += 1
        return {"state": "playing_detected", "xml_data": "<node package=\"app.wako\" />"}

    def execute_wako_heist(self, needs_wake=True, xml_data=None):
        self.full_calls += 1
        return {}


def make_app():
    app = App.__new__(App)
    app.config = {"wako_mode": True, "wako_stay_awake_on_pause": True}
    app.controller = FakeController()
    app.wako_cached_position = None
    app.wako_cached_duration = None
    app.wako_progress_anchor_time = None
    app.wako_heist_failure_key = None
    app.wako_heist_failure_until = 0
    app.wako_cached_title = None
    app.wako_cached_season = None
    app.wako_cached_episode = None
    app.wako_cached_ep_title = None
    app.wako_good_polls = 0
    app.wako_bad_polls = 0
    app.wako_ui_heist_enabled = False
    app._display_app_name = lambda value: value
    app._wako_cache_looks_stale_for_next_episode = lambda status, state: False
    app._apply_wako_progress_cache = lambda status, state: None
    app._apply_cached_wako_metadata = lambda status: None
    return app


def test_empty_paused_wako_heist_is_backed_off():
    app = make_app()
    status = {
        "focus": "app.wako/.PlayerActivity",
        "position": 659071,
        "duration": 3600000,
    }

    # Poll 1: candidate state (no heist calls yet)
    assert app._apply_wako_heist(status, "", "paused", "Wako", status["position"]) == ("", status, "paused")
    assert app.controller.lite_calls == 0
    assert app.controller.full_calls == 0

    # Poll 2: active state (heist calls triggered, returns fallback generic title on empty heist)
    res_title, res_status, res_state = app._apply_wako_heist(status, "", "paused", "Wako", status["position"])
    assert res_title == "Watching on Wako"
    assert res_state == "paused"
    assert app.controller.lite_calls == 0
    assert app.controller.full_calls == 1

    # Poll 3: failure backoff should prevent new calls
    res_title, res_status, res_state = app._apply_wako_heist(status, "", "paused", "Wako", status["position"])
    assert res_title == "Watching on Wako"
    assert res_state == "paused"
    assert app.controller.lite_calls == 0
    assert app.controller.full_calls == 1
