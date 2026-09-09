import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.gui.app import App


def make_app():
    app = App.__new__(App)
    app._0x0_cache = {}
    app._0x0_last_error = 0
    app._rpc_image_url_limit = lambda: 256
    return app


def test_small_icon_gif_upload_uses_tmpfiles_direct_download_url():
    app = make_app()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "status": "success",
        "data": {"url": "https://tmpfiles.org/12345/network.gif"},
    }

    valid_gif = MagicMock(status_code=200, headers={"Content-Type": "image/gif"})
    with patch("src.gui.app.requests.post", return_value=response) as post, \
         patch("src.gui.app.requests.get", return_value=valid_gif):
        hosted = app._upload_bytes_to_tmpfiles(
            "gif-key", b"GIF89a", "network.gif", "image/gif"
        )

    assert hosted == "https://tmpfiles.org/dl/12345/network.gif"
    assert post.call_args.args[0] == "https://tmpfiles.org/api/v1/upload"
    assert post.call_args.kwargs["files"]["file"] == (
        "network.gif",
        b"GIF89a",
        "image/gif",
    )


def test_small_icon_gif_upload_rejects_fileditch_html_and_falls_back_to_tmpfiles():
    app = make_app()
    fileditch = MagicMock(
        status_code=200,
        json=lambda: {
            "success": True,
            "url": "https://fileditchfiles.st/beta/network.gif",
        },
    )
    tmpfiles = MagicMock(
        status_code=200,
        json=lambda: {
            "status": "success",
            "data": {"url": "https://tmpfiles.org/67890/network.gif"},
        },
    )
    html_page = MagicMock(status_code=200, headers={"Content-Type": "text/html"})
    valid_gif = MagicMock(status_code=200, headers={"Content-Type": "image/gif"})

    with patch("src.gui.app.requests.post", side_effect=[fileditch, tmpfiles]), \
         patch("src.gui.app.requests.get", side_effect=[html_page, valid_gif]):
        hosted = app._upload_bytes_to_tmpfiles(
            "gif-fallback", b"GIF89a", "network.gif", "image/gif"
        )

    assert hosted == "https://tmpfiles.org/dl/67890/network.gif"
    assert app._0x0_cache["gif-fallback"] == hosted


def test_ultramax_gif_stays_on_official_source_without_upload_proxy():
    app = make_app()
    official = "https://ultramax.vip/images/Hulu.gif"
    with patch.object(app, "_center_crop_animated_gif_to_0x0", return_value="https://x0.at/cropped.gif") as crop:
        assert app._wsrv_small_rpc_image(official, animated=True) == "https://x0.at/cropped.gif"
    with patch.object(app, "_center_crop_animated_gif_to_0x0", return_value=None):
        assert app._wsrv_small_rpc_image(official, animated=True) == official
