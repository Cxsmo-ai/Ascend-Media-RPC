"""Tests for the single-instance / port-collision protection added to the
dashboard web server. Ensures two builds can't silently fight over port 5466.
"""
import os
import sys
import socket
import json
import threading
import time
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


def _grab_free_port():
    """Ask the OS for a free port, then immediately close so caller can rebind."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestPortHelpers:
    def test_port_is_free_when_unbound(self):
        from src.web.server import _port_is_free
        port = _grab_free_port()
        assert _port_is_free(port, host="127.0.0.1") is True

    def test_port_is_taken_when_bound(self):
        from src.web.server import _port_is_free
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        try:
            assert _port_is_free(port, host="127.0.0.1") is False
        finally:
            s.close()

    def test_find_free_port_skips_taken(self):
        from src.web.server import _find_free_port, _port_is_free
        # Bind on 0.0.0.0 so the helper (which probes 0.0.0.0) sees us.
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("0.0.0.0", 0))
        s.listen(1)
        port = s.getsockname()[1]
        try:
            chosen = _find_free_port(port, max_attempts=20)
            assert chosen is not None
            assert chosen != port
            assert _port_is_free(chosen) is True
        finally:
            s.close()

    def test_find_free_port_exhausted(self):
        from src.web.server import _find_free_port
        # Hold a contiguous block on 0.0.0.0 so the helper sees them.
        held = []
        try:
            # Grab 5 free ports first
            free_ports = []
            tmp_socks = []
            for _ in range(5):
                tmp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                tmp.bind(("0.0.0.0", 0))
                free_ports.append(tmp.getsockname()[1])
                tmp_socks.append(tmp)

            # Close the temps so we can rebind them deliberately one by one.
            # Track which we successfully rebind so the test only scans those.
            for tmp in tmp_socks:
                tmp.close()

            for p in free_ports:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.bind(("0.0.0.0", p))
                    s.listen(1)
                    held.append(s)
                except OSError:
                    s.close()

            if len(held) < 2:
                pytest.skip("could not reserve enough ports for the test")

            # Build a sequential range we know is fully held: pick contiguous
            # ports from `held`. If not contiguous, just confirm the helper
            # returns None when max_attempts only covers held ports.
            taken_ports = sorted(s.getsockname()[1] for s in held)
            # Scan only ports we explicitly hold.
            with patch(
                "src.web.server._port_is_free",
                side_effect=lambda port, host="0.0.0.0": port not in taken_ports,
            ):
                pass  # Just shows the technique; not used below.

            # Direct check: pass start=first taken, max_attempts=count of held
            # but force contiguous scan by patching _port_is_free to only
            # report 'taken' for our held set.
            with patch(
                "src.web.server._port_is_free",
                side_effect=lambda port, host="0.0.0.0": port not in taken_ports,
            ):
                # All taken_ports are "taken"; scan a window that contains only them.
                start = taken_ports[0]
                # Build a virtual range of length len(taken_ports) that maps
                # to fully-taken slots by also extending the "taken" set.
                chosen = _find_free_port(start, max_attempts=len(taken_ports))
                # Helper marches start, start+1, ... but taken_ports may not be
                # contiguous, so middle gaps would let it succeed. To guarantee
                # exhaustion, extend the "taken" set to cover the whole window.
                # Re-patch:
            range_set = set(range(taken_ports[0], taken_ports[0] + len(taken_ports)))
            with patch(
                "src.web.server._port_is_free",
                side_effect=lambda port, host="0.0.0.0": port not in range_set,
            ):
                chosen = _find_free_port(taken_ports[0], max_attempts=len(range_set))
                assert chosen is None
        finally:
            for s in held:
                try: s.close()
                except Exception: pass


class TestPeekExistingInstance:
    def test_returns_none_when_nothing_listening(self):
        from src.web.server import _peek_existing_instance
        # Pick a port that's almost certainly free
        port = _grab_free_port()
        assert _peek_existing_instance(port) is None

    def test_returns_info_for_real_instance(self):
        """Spin up a tiny HTTP server that mimics /api/instance and verify
        we identify it as an Ascend RPC instance."""
        from http.server import BaseHTTPRequestHandler, HTTPServer

        payload = {
            "app": "ascend-media-rpc",
            "pid": 12345,
            "python": "C:/x/python.exe",
            "cwd": "C:/x",
            "started_at": 0,
            "port": 0,
        }

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/instance":
                    body = json.dumps(payload).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_error(404)

            def log_message(self, *a, **kw):
                pass  # silence

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            time.sleep(0.05)
            from src.web.server import _peek_existing_instance
            info = _peek_existing_instance(port)
            assert info is not None
            assert info["app"] == "ascend-media-rpc"
            assert info["pid"] == 12345
        finally:
            server.shutdown()
            server.server_close()

    def test_returns_none_for_unrelated_server(self):
        """If something else is on the port but doesn't look like us, treat
        it as foreign — don't match."""
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'{"app":"someone-else"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *a, **kw): pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            time.sleep(0.05)
            from src.web.server import _peek_existing_instance
            assert _peek_existing_instance(port) is None
        finally:
            server.shutdown()
            server.server_close()


class TestInstanceEndpoint:
    def test_instance_endpoint_returns_self_identifying_payload(self):
        from src.web.server import app
        client = app.test_client()
        resp = client.get("/api/instance")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["app"] == "ascend-media-rpc"
        assert data["pid"] == os.getpid()
        assert isinstance(data["python"], str) and data["python"]
        assert isinstance(data["cwd"], str) and data["cwd"]
        assert "started_at" in data
