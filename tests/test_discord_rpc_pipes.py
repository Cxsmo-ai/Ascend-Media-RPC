import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.rpc.discord_client import DiscordRPC


class TestDiscordRPCPipes(unittest.TestCase):
    def test_connect_updates_all_available_pipes_when_enabled(self):
        instances = {}

        def fake_presence(client_id, pipe=0):
            if pipe in (0, 1):
                rpc = MagicMock()
                rpc.pipe = pipe
                instances[pipe] = rpc
                return rpc
            raise FileNotFoundError()

        rpc = DiscordRPC("123")
        rpc.update_all_pipes = True

        with patch("src.rpc.discord_client.Presence", side_effect=fake_presence):
            rpc.update(details="Ghosts", state="S05:E02")

        self.assertTrue(rpc.connected)
        self.assertEqual(rpc.pipe, 0)
        self.assertIn(1, rpc._extra_rpcs)
        instances[0].update.assert_called_once()
        instances[1].update.assert_called_once()

    def test_close_closes_extra_pipes(self):
        rpc = DiscordRPC("123")
        primary = MagicMock()
        extra = MagicMock()
        rpc.rpc = primary
        rpc._extra_rpcs = {1: extra}
        rpc.connected = True

        rpc.close()

        primary.close.assert_called_once()
        extra.close.assert_called_once()
        self.assertEqual(rpc._extra_rpcs, {})


if __name__ == "__main__":
    unittest.main()
