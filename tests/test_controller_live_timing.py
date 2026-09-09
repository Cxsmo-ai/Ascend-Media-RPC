from src.core.controller import StremioController


def _controller():
    controller = StremioController("127.0.0.1")
    return controller


def _status(state="playing", title="The Mentalist"):
    return {
        "app": "com.nuvio.tv.test",
        "title": title,
        "duration": 120_000,
        "state": state,
    }


class _NoUiDevice:
    def __init__(self, output):
        self.output = output

    def shell(self, _command):
        return self.output


def test_get_playback_status_uses_media_session_when_ui_is_unavailable():
    output = (
        "Session package=com.nuvio.tv.test\n"
        "state=PlaybackState {state=3, position=10000, speed=1.0, updated=490000}\n"
        "description=The Mentalist, S1:E1, duration=120000\n"
        "|UPTIME_DIV|\n500.0 0.0\n"
        "|FOCUS_DIV|\n"
        "mCurrentFocus=Window{abc u0 com.nuvio.tv.test/com.nuvio.tv.MainActivity}\n"
    )
    controller = StremioController("127.0.0.1")
    controller.connected = True
    controller.device = _NoUiDevice(output)

    status = controller.get_playback_status()

    assert status["state"] == "playing"
    assert status["timing_source"] == "dumpsys"
    assert status["position"] >= 10_000
    assert status["duration"] == 120_000


def test_media_session_clock_advances_without_ui_samples():
    controller = _controller()
    status = _status()

    first = controller._project_realtime_position(
        status, 10_000, 1.0, 1_000_000, updated_ts=490_000, device_uptime_ms=500_000
    )
    second = controller._project_realtime_position(
        status, 10_000, 1.0, 1_001_500, updated_ts=490_000, device_uptime_ms=501_500
    )

    assert first == 20_000
    assert 21_400 <= second <= 21_600


def test_rapid_forward_and_backward_seeks_are_adopted_immediately():
    controller = _controller()
    status = _status()

    first = controller._project_realtime_position(
        status, 10_000, 1.0, 1_000_000, updated_ts=490_000, device_uptime_ms=500_000
    )
    forward = controller._project_realtime_position(
        status, 50_000, 1.0, 1_001_000, updated_ts=501_000, device_uptime_ms=501_000
    )
    backward = controller._project_realtime_position(
        status, 5_000, 1.0, 1_002_000, updated_ts=502_000, device_uptime_ms=502_000
    )
    forward_again = controller._project_realtime_position(
        status, 90_000, 1.0, 1_003_000, updated_ts=503_000, device_uptime_ms=503_000
    )

    assert first == 20_000
    assert forward == 50_000
    assert backward == 5_000
    assert forward_again == 90_000
    assert controller._position_last_seek_detected is True


def test_out_of_order_media_session_sample_cannot_undo_a_seek():
    controller = _controller()
    status = _status()

    controller._project_realtime_position(
        status, 80_000, 1.0, 1_000_000, updated_ts=500_000, device_uptime_ms=500_000
    )
    current = controller._project_realtime_position(
        status, 20_000, 1.0, 1_001_000, updated_ts=499_000, device_uptime_ms=501_000
    )

    assert current >= 80_000
    assert controller._position_last_sample_stale is True


def test_seek_to_near_zero_is_not_replaced_by_old_position_cache():
    controller = _controller()
    status = _status()

    controller._project_realtime_position(
        status, 60_000, 1.0, 1_000_000, updated_ts=500_000, device_uptime_ms=500_000
    )
    landed = controller._project_realtime_position(
        status, 0, 1.0, 1_001_000, updated_ts=501_000, device_uptime_ms=501_000
    )

    assert landed == 0


def test_players_without_updated_timestamp_still_follow_large_seeks():
    controller = _controller()
    status = _status()

    controller._project_realtime_position(status, 10_000, 1.0, 1_000_000)
    forward = controller._project_realtime_position(status, 50_000, 1.0, 1_001_000)
    backward = controller._project_realtime_position(status, 5_000, 1.0, 1_002_000)

    assert forward == 50_000
    assert backward == 5_000


def test_pause_and_resume_reanchor_the_ui_free_clock():
    controller = _controller()
    playing = _status("playing")
    paused = _status("paused")

    controller._project_realtime_position(
        playing, 30_000, 1.0, 1_000_000, updated_ts=500_000, device_uptime_ms=500_000
    )
    paused_position = controller._project_realtime_position(
        paused, 45_000, 0.0, 1_001_000, updated_ts=501_000, device_uptime_ms=501_000
    )
    resumed_position = controller._project_realtime_position(
        playing, 45_000, 1.0, 1_002_000, updated_ts=502_000, device_uptime_ms=502_000
    )
    resumed_live = controller._project_realtime_position(
        playing, 45_000, 1.0, 1_002_500, updated_ts=502_000, device_uptime_ms=502_500
    )

    assert paused_position == 45_000
    assert resumed_position == 45_000
    assert 45_400 <= resumed_live <= 45_600
