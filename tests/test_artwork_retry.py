"""Regression tests for the Top Posters / hosted artwork pipeline fixes.

Verifies:
1. `_resize_artwork_to_square` retries 3x on SSL/Connection errors with a
   browser-like UA, succeeds when a later attempt returns 200.
2. `_upload_to_0x0` has per-host circuit breaker requiring 3 consecutive
   failures (not 1) and recovers on success.
3. `_best_dashboard_image_url` falls back to raw TMDB/ERDB URL when local
   cache fetch fails so dashboard preview is never blank.
"""
import os
import sys
import io
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
import pytest
from PIL import Image


def _make_app():
    """Build a minimal App-like object that exposes the patched methods only.

    We avoid instantiating the real App (it spins up threads / connects to
    Discord / etc.) by binding the methods to a SimpleNamespace.
    """
    from src.gui.app import App

    # Borrow the unbound methods we want to test.
    class Stub:
        config = {"artwork_cache_size": 512, "artwork_cache_enabled": True}
        last_episode_image_url = None
        last_season_image_url = None
        last_content_image_url = None
        last_erdb_show_url = None
        last_erdb_backdrop_url = None
        last_erdb_episode_url = None
        rpc_artwork_upload_cache = {}
        rpc_artwork_upload_manifest_loaded = True

        # Stub helpers the methods under test call into.
        def _rpc_image_url_limit(self):
            return 256

        def _rpc_artwork_key(self, source_url, fit="contain"):
            return "testkey"

        def _rpc_artwork_cache_path(self, key):
            return os.path.join(os.path.dirname(__file__), f"_tmp_{key}.png")

        def _public_dashboard_base_url(self):
            return None

        def _rpc_cached_artwork_public_url(self, key):
            return None

        def _rpc_cached_artwork_local_url(self, key):
            return f"/i/{key}.png"

        def _upload_cached_rpc_artwork(self, key, path):
            return None

        def _load_rpc_artwork_manifest(self):
            return None

        def _best_artwork_source_url(self):
            src = self._artwork_source
            return ("TOP_POSTERS" if src and "top-posters" in src else "TMDB", src, "contain")

        def _is_top_posters_image_url(self, url):
            return "top-posters" in (url or "")

        def _is_erdb_image_url(self, url):
            return "erdb" in (url or "")

        def _clean_top_posters_rpc_url(self, url):
            return url

        def _top_posters_wsrv_short_url(self, url, size=512):
            # Minimal stub mimicking the real wsrv URL shape
            return f"https://wsrv.nl/?url={url}&w=512&h=512&fit=contain"

        def _wsrv_rpc_image(self, url, fit="contain"):
            import urllib.parse
            return f"https://wsrv.nl/?url={urllib.parse.quote(url, safe=':/%')}&w=512&h=512&fit={fit}&output=png"

        def _upload_to_fileditch(self, url):
            # No-op fallback in tests; individual tests can monkeypatch.
            return None

        def _upload_local_file_to_fileditch(self, source_url, local_path, fit="contain"):
            return None

    # Attach the *real* methods we want to test.
    Stub._resize_artwork_to_square = App._resize_artwork_to_square
    Stub._upload_to_0x0 = App._upload_to_0x0
    Stub._upload_to_fileditch = App._upload_to_fileditch
    Stub._upload_to_pixeldrain = App._upload_to_pixeldrain
    Stub._upload_local_file_to_0x0 = App._upload_local_file_to_0x0
    Stub._upload_local_file_to_fileditch = App._upload_local_file_to_fileditch
    Stub._upload_local_file_to_pixeldrain = App._upload_local_file_to_pixeldrain
    Stub._best_dashboard_image_url = App._best_dashboard_image_url
    Stub._lazy_cached_or_uploaded_rpc_artwork_url = (
        App._lazy_cached_or_uploaded_rpc_artwork_url
    )
    Stub._proxy_rpc_image = App._proxy_rpc_image

    return Stub()


def _png_bytes():
    """Generate a tiny valid PNG so PIL.Image.open works in the cache path."""
    img = Image.new("RGB", (16, 16), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fix 1: _resize_artwork_to_square retries
# ---------------------------------------------------------------------------
class TestResizeArtworkRetries:
    def test_retries_on_ssl_error_then_succeeds(self, tmp_path):
        app = _make_app()
        out = str(tmp_path / "out.png")

        call_log = []

        def fake_get(url, timeout=None, headers=None, **kw):
            call_log.append({"headers": headers, "timeout": timeout})
            if len(call_log) < 3:
                raise requests.exceptions.SSLError("UNEXPECTED_EOF_WHILE_READING")
            resp = MagicMock()
            resp.status_code = 200
            resp.content = _png_bytes()
            resp.headers = {"Content-Type": "image/png"}
            resp.raise_for_status = lambda: None
            return resp

        with patch("src.gui.app.requests.get", side_effect=fake_get):
            ok = app._resize_artwork_to_square(
                "https://api.top-posters.com/x.jpg", out
            )

        assert ok is True
        assert len(call_log) == 3
        # Verify browser UA is being sent
        ua = call_log[0]["headers"]["User-Agent"]
        assert "Mozilla" in ua and "Chrome" in ua

    def test_gives_up_after_three_attempts(self, tmp_path):
        app = _make_app()
        out = str(tmp_path / "out.png")

        with patch(
            "src.gui.app.requests.get",
            side_effect=requests.exceptions.SSLError("EOF"),
        ) as g:
            ok = app._resize_artwork_to_square("https://x/y.jpg", out)

        assert ok is False
        assert g.call_count == 3

    def test_non_retryable_error_does_not_loop(self, tmp_path):
        app = _make_app()
        out = str(tmp_path / "out.png")

        resp = MagicMock()
        resp.status_code = 404
        resp.headers = {"Content-Type": "text/html"}
        def _raise():
            raise requests.exceptions.HTTPError("404")
        resp.raise_for_status = _raise

        with patch("src.gui.app.requests.get", return_value=resp) as g:
            ok = app._resize_artwork_to_square("https://x/y.jpg", out)

        assert ok is False
        # HTTPError is NOT in the retry whitelist -> exactly 1 attempt.
        assert g.call_count == 1


# ---------------------------------------------------------------------------
# Fix 2: _upload_to_0x0 circuit breaker requires 3 failures
# ---------------------------------------------------------------------------
class TestUpload0x0CircuitBreaker:
    def test_one_failure_does_not_trip_breaker(self):
        app = _make_app()
        with patch(
            "src.gui.app.requests.get",
            side_effect=requests.exceptions.SSLError("EOF"),
        ):
            # Need to also patch `import requests` inside the function — it
            # re-imports. So we patch via the module.
            res = app._upload_to_0x0("https://api.top-posters.com/a.jpg")
            assert res is None

        host_fails = app._0x0_failures.get("api.top-posters.com", {})
        assert host_fails.get("count", 0) == 1
        # Different host should NOT be affected
        other = app._0x0_failures.get("api.tmdb.org", {"count": 0})
        assert other.get("count", 0) == 0

    def test_three_failures_trip_breaker_then_skip(self):
        app = _make_app()
        url = "https://api.top-posters.com/a.jpg"
        with patch(
            "src.gui.app.requests.get",
            side_effect=requests.exceptions.SSLError("EOF"),
        ):
            for _ in range(3):
                assert app._upload_to_0x0(url) is None
        assert app._0x0_failures["api.top-posters.com"]["count"] == 3

        # 4th call must be a no-op (breaker active) — patched func should not
        # even be called.
        with patch.object(app, "_upload_to_fileditch", return_value=None), \
             patch.object(app, "_upload_to_pixeldrain", return_value=None), \
             patch("src.gui.app.requests.get") as g:
            assert app._upload_to_0x0(url) is None
            g.assert_not_called()

    def test_success_clears_breaker(self):
        app = _make_app()
        url = "https://erdb.example/img.jpg"

        # Two failures
        with patch(
            "src.gui.app.requests.get",
            side_effect=requests.exceptions.SSLError("EOF"),
        ):
            app._upload_to_0x0(url)
            app._upload_to_0x0(url)
        assert app._0x0_failures["erdb.example"]["count"] == 2

        # Now a success
        img_resp = MagicMock(status_code=200, content=_png_bytes())
        up_resp = MagicMock(status_code=200, text="https://x0.at/abc.jpg")
        with patch("src.gui.app.requests.get", return_value=img_resp), \
             patch("src.gui.app.requests.post", return_value=up_resp):
            hosted = app._upload_to_0x0(url)

        assert hosted == "https://x0.at/abc.jpg"
        assert "erdb.example" not in app._0x0_failures

    def test_per_host_isolation(self):
        """A flaky host must not poison a healthy host."""
        app = _make_app()
        bad = "https://api.top-posters.com/x.jpg"
        good = "https://image.tmdb.org/y.jpg"

        with patch(
            "src.gui.app.requests.get",
            side_effect=requests.exceptions.SSLError("EOF"),
        ):
            for _ in range(3):
                app._upload_to_0x0(bad)

        # Breaker is open on bad host; good host should still attempt.
        img_resp = MagicMock(status_code=200, content=_png_bytes())
        up_resp = MagicMock(status_code=200, text="https://x0.at/ok.jpg")
        with patch.object(app, "_upload_to_fileditch", return_value=None), \
             patch.object(app, "_upload_to_pixeldrain", return_value=None), \
             patch("src.gui.app.requests.get", return_value=img_resp) as g_get, \
             patch("src.gui.app.requests.post", return_value=up_resp):
            hosted = app._upload_to_0x0(good)

        assert hosted == "https://x0.at/ok.jpg"
        g_get.assert_called_once()


# ---------------------------------------------------------------------------
# Fix 3: _best_dashboard_image_url surfaces raw URL when cache fails
# ---------------------------------------------------------------------------
class TestDashboardFallback:
    def test_falls_back_to_tmdb_when_cache_fails(self, tmp_path):
        app = _make_app()
        app._artwork_source = "https://api.top-posters.com/broken.jpg"
        app.last_episode_image_url = "https://image.tmdb.org/p/episode.jpg"
        app.last_content_image_url = "https://image.tmdb.org/p/show.jpg"
        # Force the cache path to a non-existent place
        app._rpc_artwork_cache_path = (
            lambda key: str(tmp_path / f"{key}.png")
        )

        # All artwork fetches fail
        with patch(
            "src.gui.app.requests.get",
            side_effect=requests.exceptions.SSLError("EOF"),
        ):
            url = app._best_dashboard_image_url()

        # Cache failed but we got the raw TMDB URL instead of None
        assert url == "https://image.tmdb.org/p/episode.jpg"

    def test_returns_local_route_when_cache_succeeds(self, tmp_path):
        app = _make_app()
        app._artwork_source = "https://api.top-posters.com/ok.jpg"
        cache_file = tmp_path / "testkey.png"
        # Pre-create the cache file so the lazy path returns the local URL
        Image.new("RGB", (8, 8)).save(str(cache_file))
        app._rpc_artwork_cache_path = lambda key: str(cache_file)

        url = app._best_dashboard_image_url()
        assert url == "/i/testkey.png"

    def test_returns_none_when_no_source_and_no_fallback(self):
        app = _make_app()
        app._artwork_source = None
        url = app._best_dashboard_image_url()
        assert url is None


# ---------------------------------------------------------------------------
# Fix 5: _upload_local_file_to_0x0 — bypass broken upstream GET
# ---------------------------------------------------------------------------
class TestUploadLocalFileTo0x0:
    def test_uploads_existing_file(self, tmp_path):
        app = _make_app()
        f = tmp_path / "poster.png"
        Image.new("RGB", (32, 32), (0, 0, 255)).save(str(f))

        up = MagicMock(status_code=200, text="https://x0.at/zz.png")
        with patch("src.gui.app.requests.post", return_value=up) as p:
            url = app._upload_local_file_to_0x0(
                "https://api.top-posters.com/x.jpg", str(f)
            )
        assert url == "https://x0.at/zz.png"
        assert p.call_args_list[-1].args[0] == "https://x0.at"
        # Both keys must be cached
        assert app._0x0_cache["https://api.top-posters.com/x.jpg"] == url

    def test_missing_file_returns_none(self, tmp_path):
        app = _make_app()
        url = app._upload_local_file_to_0x0(
            "https://x/y.jpg", str(tmp_path / "missing.png")
        )
        assert url is None

    def test_empty_file_returns_none(self, tmp_path):
        app = _make_app()
        f = tmp_path / "empty.png"
        f.write_bytes(b"")
        url = app._upload_local_file_to_0x0("https://x/y.jpg", str(f))
        assert url is None

    def test_http_error_returns_none(self, tmp_path):
        app = _make_app()
        f = tmp_path / "poster.png"
        Image.new("RGB", (8, 8)).save(str(f))
        up = MagicMock(status_code=500, text="server error")
        with patch("src.gui.app.requests.post", return_value=up):
            url = app._upload_local_file_to_0x0("https://x/y.jpg", str(f))
        assert url is None


class TestFileDitchCurrentApi:
    def test_remote_upload_uses_current_fileditch_endpoint_and_top_level_url(self):
        app = _make_app()
        img = MagicMock(status_code=200, content=_png_bytes(), headers={"Content-Type": "image/png"})
        hosted_probe = MagicMock(status_code=200, headers={"Content-Type": "image/png"}, content=_png_bytes())
        upload = MagicMock(
            status_code=200,
            json=lambda: {
                "success": True,
                "url": "https://fileditchfiles.me/file.php?f=/abc/artwork.png",
            },
        )

        with patch("src.gui.app.requests.get", side_effect=[img, hosted_probe]), \
             patch("src.gui.app.requests.post", return_value=upload) as post:
            hosted = app._upload_to_fileditch("https://image.example/poster.png")

        assert hosted == "https://fileditchfiles.me/file.php?f=/abc/artwork.png"
        post_url = post.call_args.args[0]
        assert post_url.startswith("https://new.fileditch.com/upload.php")
        assert "catbox" not in post_url.lower()

    def test_local_upload_uses_current_fileditch_endpoint_and_top_level_url(self, tmp_path):
        app = _make_app()
        local_file = tmp_path / "poster.png"
        Image.new("RGB", (16, 16), (255, 0, 0)).save(str(local_file))
        hosted_probe = MagicMock(status_code=200, headers={"Content-Type": "image/png"}, content=_png_bytes())
        upload = MagicMock(
            status_code=200,
            json=lambda: {
                "success": True,
                "url": "https://fileditchfiles.me/file.php?f=/abc/poster.png",
            },
        )

        with patch("src.gui.app.requests.get", return_value=hosted_probe), \
             patch("src.gui.app.requests.post", return_value=upload) as post:
            hosted = app._upload_local_file_to_fileditch(
                "https://api.top-posters.com/TP/imdb/thumbnail/tt0903747/S01E01.jpg",
                str(local_file),
            )

        assert hosted == "https://fileditchfiles.me/file.php?f=/abc/poster.png"
        post_url = post.call_args.args[0]
        assert post_url.startswith("https://new.fileditch.com/upload.php")
        assert "catbox" not in post_url.lower()

    def test_fileditch_html_file_page_is_rejected_for_discord(self):
        app = _make_app()
        img = MagicMock(status_code=200, content=_png_bytes(), headers={"Content-Type": "image/png"})
        hosted_probe = MagicMock(
            status_code=200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=b"<!DOCTYPE html><html></html>",
        )
        upload = MagicMock(
            status_code=200,
            json=lambda: {
                "success": True,
                "url": "https://fileditchfiles.me/file.php?f=/abc/artwork.png",
            },
        )

        with patch("src.gui.app.requests.get", side_effect=[img, hosted_probe]), \
             patch("src.gui.app.requests.post", return_value=upload):
            hosted = app._upload_to_fileditch("https://image.example/poster.png")

        assert hosted is None


# ---------------------------------------------------------------------------
# Fix 6: _proxy_rpc_image — Top Posters uses direct-from-cache upload
# ---------------------------------------------------------------------------
class TestProxyRpcImageTopPosters:
    def test_top_posters_uses_uploaded_resized_url_before_direct_provider_url(self, tmp_path):
        app = _make_app()
        source = "https://api.top-posters.com/TP/tmdb/thumbnail/1396/S01E01.jpg?badge_size=large"
        cache_path = tmp_path / "testkey.png"
        Image.new("RGB", (16, 16), (255, 0, 0)).save(str(cache_path))
        app._rpc_artwork_cache_path = lambda key: str(cache_path)

        with patch.object(app, "_upload_local_file_to_0x0", return_value="https://x0.at/duda.png"):
            result = app._proxy_rpc_image(source)

        assert result.startswith("https://wsrv.nl/?url=")
        assert "fit=contain" in result
        assert "w=512" in result
        assert "h=512" in result
        assert "x0.at/duda.png" in result
        assert "top-posters" not in result

    def test_erdb_uses_uploaded_resized_url_before_direct_provider_url(self, tmp_path):
        app = _make_app()
        source = "https://erdb.example/poster/tt0903747.png?token=secret"
        cache_path = tmp_path / "testkey.png"
        Image.new("RGB", (16, 16), (255, 0, 0)).save(str(cache_path))
        app._rpc_artwork_cache_path = lambda key: str(cache_path)

        with patch.object(app, "_upload_local_file_to_0x0", return_value="https://x0.at/erdb.png"):
            result = app._proxy_rpc_image(source)

        assert result.startswith("https://wsrv.nl/?url=")
        assert "fit=contain" in result
        assert "x0.at/erdb.png" in result
        assert "token=secret" not in result

    def test_top_posters_uses_local_cache_then_uploads_to_0x0(self, tmp_path):
        """Full flow: upstream GET fails -> local cache exists ->
        direct upload of local file gives Discord a public URL."""
        app = _make_app()
        cache_path = tmp_path / "testkey.png"
        Image.new("RGB", (16, 16), (255, 0, 0)).save(str(cache_path))
        app._rpc_artwork_cache_path = lambda key: str(cache_path)

        fileditch_html = MagicMock(
            status_code=200,
            json=lambda: {
                "success": True,
                "url": "https://fileditchfiles.me/file.php?f=/abc/artwork.png",
            },
        )
        pixeldrain_ok = MagicMock(
            status_code=201,
            json=lambda: {"success": True, "id": "pd123"},
        )
        fileditch_probe = MagicMock(
            status_code=200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            content=b"<!DOCTYPE html>",
        )

        with patch("src.gui.app.requests.get",
                   side_effect=[requests.exceptions.SSLError("EOF"), fileditch_probe]), \
             patch("src.gui.app.requests.post", side_effect=[fileditch_html, pixeldrain_ok]):
            result = app._proxy_rpc_image(
                "https://api.top-posters.com/TP/imdb/thumbnail/tt9794044/S2E1.jpg"
            )

        # Discord must receive a resized uploaded URL, not FileDitch's HTML page or a tokenized wsrv URL.
        assert result.startswith("https://wsrv.nl/?url=https://pixeldrain.com/api/file/pd123")

    def test_top_posters_wraps_x0_fallback_for_large_art(self, tmp_path):
        app = _make_app()
        cache_path = tmp_path / "testkey.png"
        Image.new("RGB", (16, 16), (255, 0, 0)).save(str(cache_path))
        app._rpc_artwork_cache_path = lambda key: str(cache_path)

        x0_ok = MagicMock(status_code=200, text="https://x0.at/abc.png")

        with patch.object(app, "_upload_local_file_to_fileditch", return_value=None), \
             patch.object(app, "_upload_local_file_to_pixeldrain", return_value=None), \
             patch("src.gui.app.requests.post", return_value=x0_ok):
            result = app._proxy_rpc_image(
                "https://api.top-posters.com/TP/imdb/thumbnail/tt9794044/S2E1.jpg"
            )

        assert result.startswith("https://wsrv.nl/?url=https://x0.at/abc.png")

    def test_top_posters_falls_back_to_wsrv_only_if_all_uploads_fail(self, tmp_path):
        """If local cache can't be created AND can't be uploaded, the last
        resort is no artwork rather than leaking a tokenized URL to wsrv."""
        app = _make_app()
        app._rpc_artwork_cache_path = lambda key: str(tmp_path / "nope.png")

        with patch("src.gui.app.requests.get",
                   side_effect=requests.exceptions.SSLError("EOF")), \
             patch("src.gui.app.requests.post",
                   side_effect=requests.exceptions.SSLError("EOF")):
            result = app._proxy_rpc_image(
                "https://api.top-posters.com/TP/imdb/thumbnail/tt9794044/S2E1.jpg"
            )

        assert result is None
