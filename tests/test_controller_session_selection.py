from src.core.controller import StremioController


def _session(package, state, updated=0, description="Test"):
    return (
        f"Session package={package}\n"
        f"state=PlaybackState {{state={state}, position=1000, speed=1.0, updated={updated}}}\n"
        f"description={description}, duration=60000\n"
    )


def test_playing_session_beats_stale_paused_session():
    raw = _session("com.stremio.one", 2, 10) + _session("com.brouken.player", 3, 20)
    block, package = StremioController._select_media_session(
        raw, "mCurrentFocus=Window{abc u0 com.brouken.player/.MainActivity}", False
    )
    assert package == "com.brouken.player"
    assert "state=3" in block


def test_unknown_active_media_session_is_detected_in_normal_mode():
    raw = _session("com.spotify.tv.android", 3, 30)
    block, package = StremioController._select_media_session(raw, "", False)
    assert block is not None
    assert package == "com.spotify.tv.android"


def test_focused_unknown_external_player_is_allowed_for_wako():
    raw = _session("com.example.externalplayer", 3, 40)
    block, package = StremioController._select_media_session(
        raw, "mCurrentFocus=Window{abc u0 app.wako/.MainActivity}", True
    )
    assert block is not None
    assert package == "com.example.externalplayer"
