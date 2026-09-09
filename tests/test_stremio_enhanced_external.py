import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.integrations.stremio_desktop import StremioDesktopWatcher


class TestStremioEnhancedExternal(unittest.TestCase):
    def test_parse_enhanced_overlay_title(self):
        watcher = StremioDesktopWatcher()

        parsed = watcher.parse_title("Ghosts - Viking Wedding (5x2)")

        self.assertEqual(parsed["title"], "Ghosts")
        self.assertEqual(parsed["episode_title"], "Viking Wedding")
        self.assertEqual(parsed["season"], 5)
        self.assertEqual(parsed["episode"], 2)
        self.assertFalse(parsed["is_movie"])

    def test_filename_parser_extracts_show_episode(self):
        watcher = StremioDesktopWatcher()

        parsed = watcher.parse_media_hint("Ghosts.S05E02.Viking.Wedding.1080p.WEB-DL.mkv")

        self.assertEqual(parsed["title"], "Ghosts")
        self.assertEqual(parsed["episode_title"], "Viking Wedding")
        self.assertEqual(parsed["season"], 5)
        self.assertEqual(parsed["episode"], 2)
        self.assertFalse(parsed["is_movie"])

    def test_detects_spaced_stremio_enhanced_process_name(self):
        watcher = StremioDesktopWatcher()

        self.assertTrue(watcher._is_stremio_process_name("Stremio Enhanced.exe"))

    def test_configured_devtools_port_is_first(self):
        watcher = StremioDesktopWatcher({"stremio_enhanced_devtools_port": 9333})

        self.assertEqual(watcher._devtools_ports[0], 9333)

    def test_profile_paths_use_appdata_environment(self):
        with patch.dict(os.environ, {"APPDATA": r"D:\Profiles\Someone\Roaming"}):
            watcher = StremioDesktopWatcher()

        self.assertIn(
            os.path.join(r"D:\Profiles\Someone\Roaming", "stremio-enhanced", "Cache", "Cache_Data"),
            watcher._enhanced_cache_dirs,
        )

    def test_enhanced_executable_fallback_uses_standard_env_paths(self):
        env = {
            "LOCALAPPDATA": r"D:\Users\Someone\AppData\Local",
            "PROGRAMFILES": r"D:\Program Files",
            "PROGRAMFILES(X86)": r"D:\Program Files (x86)",
        }
        watcher = StremioDesktopWatcher()

        candidates = watcher._enhanced_executable_candidates(env)

        self.assertIn(
            os.path.join(r"D:\Users\Someone\AppData\Local", "Programs", "stremio-enhanced", "Stremio Enhanced.exe"),
            candidates,
        )
        self.assertIn(
            os.path.join(r"D:\Program Files", "Stremio Enhanced", "Stremio Enhanced.exe"),
            candidates,
        )

    def test_devtools_payload_builds_exact_enhanced_state(self):
        watcher = StremioDesktopWatcher()
        watcher._devtools_ports = [9229]
        page = {
            "webSocketDebuggerUrl": "ws://127.0.0.1:9229/devtools/page/1",
            "url": "https://app.strem.io/#/detail/series/tt8594324/tt8594324:5:2",
            "title": "Ghosts - Viking Wedding (5x2)",
        }
        eval_result = {
            "href": "https://app.strem.io/#/detail/series/tt8594324/tt8594324:5:2",
            "title": "Ghosts - Viking Wedding (5x2)",
            "currentTime": 26.2,
            "duration": 1271.1,
            "paused": True,
            "ended": False,
            "playbackRate": 1,
            "videoSrc": "http://127.0.0.1:11470/stream/Ghosts.S05E02.Viking.Wedding.mkv",
        }

        with patch("src.core.integrations.stremio_desktop.requests.get") as get, \
             patch.object(watcher, "_cdp_evaluate", return_value=eval_result):
            get.return_value = MagicMock(status_code=200, json=MagicMock(return_value=[page]))
            state = watcher._get_enhanced_devtools_state()

        self.assertTrue(state["active"])
        self.assertEqual(state["source"], "stremio_enhanced_devtools")
        self.assertEqual(state["telemetry_mode"], "devtools")
        self.assertEqual(state["app"], "Stremio Enhanced")
        self.assertEqual(state["title"], "Ghosts")
        self.assertEqual(state["episode_title"], "Viking Wedding")
        self.assertEqual(state["season"], 5)
        self.assertEqual(state["episode"], 2)
        self.assertEqual(state["position"], 26200)
        self.assertEqual(state["duration"], 1271100)
        self.assertEqual(state["state"], "paused")
        self.assertEqual(state["imdb_id"], "tt8594324")

    def test_devtools_without_video_does_not_claim_active_playback(self):
        watcher = StremioDesktopWatcher()
        watcher._devtools_ports = [9229]
        page = {
            "webSocketDebuggerUrl": "ws://127.0.0.1:9229/devtools/page/1",
            "url": "https://web.stremio.com/#/detail/series/tt11379026/tt11379026%3A5%3A2",
            "title": "Stremio - Freedom to Stream",
        }
        eval_result = {
            "href": page["url"],
            "title": "Stremio - Freedom to Stream",
            "currentTime": None,
            "duration": None,
            "paused": None,
            "ended": None,
            "playbackRate": None,
            "videoSrc": None,
        }

        with patch("src.core.integrations.stremio_desktop.requests.get") as get, \
             patch.object(watcher, "_cdp_evaluate", return_value=eval_result):
            get.return_value = MagicMock(status_code=200, json=MagicMock(return_value=[page]))
            state = watcher._get_enhanced_devtools_state()

        self.assertEqual(state, {"active": False})

    def test_tool_managed_relaunch_starts_enhanced_with_devtools(self):
        watcher = StremioDesktopWatcher({
            "stremio_enhanced_auto_devtools": True,
            "stremio_enhanced_devtools_port": 9333,
        })
        proc = MagicMock()
        proc.info = {"name": "Stremio Enhanced.exe", "pid": 123}
        proc.exe.return_value = r"C:\Apps\Stremio Enhanced.exe"
        watcher._is_enhanced_process = True

        with patch.object(watcher, "_devtools_pages", return_value=[]), \
             patch("src.core.integrations.stremio_desktop.psutil.process_iter", return_value=[proc]), \
             patch("src.core.integrations.stremio_desktop.psutil.wait_procs"), \
             patch("src.core.integrations.stremio_desktop.os.path.exists", return_value=True), \
             patch("src.core.integrations.stremio_desktop.subprocess.Popen") as popen:
            self.assertTrue(watcher._maybe_relaunch_enhanced_with_devtools())

        proc.terminate.assert_called_once()
        popen.assert_called_once()
        command = popen.call_args.args[0]
        self.assertEqual(command[0], r"C:\Apps\Stremio Enhanced.exe")
        self.assertIn("--remote-debugging-port=9333", command)
        self.assertIn("--remote-debugging-address=127.0.0.1", command)

    def test_tool_managed_relaunch_disabled_by_config(self):
        watcher = StremioDesktopWatcher({"stremio_enhanced_auto_devtools": False})
        watcher._target_exe = r"C:\Apps\Stremio Enhanced.exe"
        watcher._is_enhanced_process = True

        with patch("src.core.integrations.stremio_desktop.subprocess.Popen") as popen:
            self.assertFalse(watcher._maybe_relaunch_enhanced_with_devtools())

        popen.assert_not_called()

    def test_log_fallback_extracts_identity_without_timestamp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = os.path.join(temp_dir, "stremio-server.log")
            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write("stream opened http://127.0.0.1/Ghosts.S05E02.Viking.Wedding.1080p.mkv imdb=tt8594324\n")

            watcher = StremioDesktopWatcher()
            watcher._enhanced_log_paths = [log_path]
            state = watcher._get_enhanced_log_state()

        self.assertTrue(state["active"])
        self.assertEqual(state["source"], "stremio_enhanced_logs")
        self.assertEqual(state["telemetry_mode"], "logs")
        self.assertEqual(state["title"], "Ghosts")
        self.assertEqual(state["episode_title"], "Viking Wedding")
        self.assertEqual(state["season"], 5)
        self.assertEqual(state["episode"], 2)
        self.assertEqual(state["imdb_id"], "tt8594324")
        self.assertIsNone(state["position"])
        self.assertIsNone(state["duration"])

    def test_cache_fallback_extracts_current_stream_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = os.path.join(temp_dir, "Cache", "Cache_Data")
            os.makedirs(cache_dir)
            cache_path = os.path.join(cache_dir, "f_000001")
            with open(cache_path, "w", encoding="utf-8") as handle:
                handle.write(
                    '{"streams":[{"behaviorHints":{"filename":'
                    '"Ghosts.US.S05E02.Viking.Wedding.720p.HEVC.x265-MeGusta.mkv"},'
                    '"url":"https://example.test/Ghosts.US.S05E02.Viking.Wedding.mkv"}]}'
                )

            watcher = StremioDesktopWatcher()
            watcher._enhanced_cache_dirs = [cache_dir]
            state = watcher._get_enhanced_cache_state()

        self.assertTrue(state["active"])
        self.assertEqual(state["source"], "stremio_enhanced_cache")
        self.assertEqual(state["telemetry_mode"], "cache")
        self.assertEqual(state["title"], "Ghosts")
        self.assertEqual(state["episode_title"], "Viking Wedding")
        self.assertEqual(state["season"], 5)
        self.assertEqual(state["episode"], 2)
        self.assertIsNone(state["position"])
        self.assertIsNone(state["duration"])

    def test_enhanced_get_state_prefers_external_source(self):
        watcher = StremioDesktopWatcher()
        watcher._is_enhanced_process = True

        with patch.object(watcher, "is_running", return_value=True), \
             patch.object(watcher, "_get_enhanced_external_state", return_value={"active": True, "title": "Ghosts", "source": "stremio_enhanced_logs"}), \
             patch.object(watcher, "_get_uia_state", return_value={"active": False}), \
             patch.object(watcher, "get_playback_stats", return_value={}):
            state = watcher.get_state()

        self.assertEqual(state["title"], "Ghosts")
        self.assertEqual(state["source"], "stremio_enhanced_logs")

    def test_enhanced_uses_windows_device_text(self):
        from src.gui.app import App

        config = {
            "adb_host": "127.0.0.1",
            "adb_port": 5555,
            "rpc_branding": "on Stremio",
            "rpc_small_icon_mode": "play_status",
            "show_device_name": True,
            "wako_mode": False,
        }
        with patch("src.gui.app.load_config", return_value=config), \
             patch("src.gui.app.DiscordRPC"), \
             patch("src.gui.app.TMDBClient"), \
             patch("src.gui.app.StremioDesktopWatcher"), \
             patch("src.gui.app.SkipManager"), \
             patch("src.gui.app.ConfigWatcher"), \
             patch("src.gui.app.ADBDiscovery"), \
             patch("src.gui.app.TraktClient"), \
             patch("src.gui.app.App.start_gui"), \
             patch("src.gui.app.threading.Thread"), \
             patch("platform.release", return_value="11"):
            app = App()
            app._best_rpc_image_url = MagicMock(return_value="https://example.test/art.png")
            app._small_rpc_art = MagicMock(return_value=("play", "Play"))

            payload = app._build_rpc_payload(
                "Ghosts",
                {"state": "paused", "position": 26000, "duration": 1271000},
                "Stremio Enhanced",
            )

        self.assertEqual(payload["small_text"], "Paused on Windows 11")


if __name__ == "__main__":
    unittest.main()
