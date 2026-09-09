from src.core.controller import StremioController


class FakeDevice:
    def __init__(self, outputs):
        self.outputs = iter(outputs)

    def shell(self, _command):
        return next(self.outputs)


def _output(title, position, duration=None):
    duration_text = f", duration={duration}" if duration is not None else ""
    return (
        "Session package=com.brouken.player\n"
        f"state=PlaybackState {{state=3, position={position}, speed=1.0, updated=0}}\n"
        f"description={title}{duration_text}\n"
        "|UPTIME_DIV|\n1000.0 0.0\n"
        "|FOCUS_DIV|\n"
        "mCurrentFocus=Window{abc u0 com.brouken.player/.MainActivity}\n"
    )


def test_new_title_does_not_inherit_previous_timeline():
    controller = StremioController("127.0.0.1")
    controller.connected = True
    controller.device = FakeDevice([
        _output("First Movie", 50000, 60000),
        _output("Second Movie", 0, None),
    ])

    first = controller.get_playback_status()
    second = controller.get_playback_status()

    assert first["duration"] == 60000
    assert first["position"] >= 50000
    assert second["title"] == "Second Movie"
    assert second["duration"] == 0
    assert second["position"] < 2000
