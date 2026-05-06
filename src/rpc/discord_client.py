import time
import logging
from typing import Optional
from pypresence import Presence
from pypresence.types import ActivityType

try:
    from pypresence.exceptions import DiscordNotFound, InvalidPipe, PipeClosed
except ImportError:
    from pypresence.exceptions import DiscordNotFound, InvalidPipe

    class PipeClosed(Exception):
        pass


logger = logging.getLogger("stremio-rpc")


class DiscordRPC:
    def __init__(self, client_id: str):
        self.client_id = str(client_id or "").strip()
        self.rpc: Optional[Presence] = None
        self.connected = False

        self._last_reconnect_attempt = 0
        self._discord_missing_logged = False

        # Discord RPC should not be spammed every dashboard tick.
        self._last_update_sent = 0
        self._last_payload_signature = None
        self.min_update_interval = 15.0

        self.pipe = 0

    def connect(self):
        if not self.client_id:
            logger.info("RPC: No Client ID provided.")
            return

        if self.connected and self.rpc:
            return

        now = time.time()
        if now - self._last_reconnect_attempt < 15:
            return

        self._last_reconnect_attempt = now

        if self.rpc:
            try:
                self.rpc.close()
            except Exception:
                pass

        self.rpc = None
        self.connected = False

        logger.info(f"RPC: Attempting to connect with ID {self.client_id}...")

        # Try standard Discord pipe first, then PTB/Canary/other pipes.
        for pipe in range(10):
            try:
                rpc = Presence(self.client_id, pipe=pipe)
                rpc.connect()

                self.rpc = rpc
                self.pipe = pipe
                self.connected = True
                self._discord_missing_logged = False

                logger.info(f"RPC: Successfully Connected with ID {self.client_id} on pipe {pipe}!")
                return

            except (DiscordNotFound, InvalidPipe, ConnectionRefusedError, FileNotFoundError):
                continue

            except Exception as e:
                logger.debug(f"RPC: Pipe {pipe} failed: {e}")
                continue

        if not self._discord_missing_logged:
            logger.warning("RPC: Discord not found. Open Discord desktop and enable Activity Status.")
            self._discord_missing_logged = True

    def reconnect_with_id(self, new_client_id: str):
        new_client_id = str(new_client_id or "").strip()

        if new_client_id == self.client_id and self.connected:
            return

        logger.info(f"RPC: Switching to App ID {new_client_id}.")

        self.close()
        self.client_id = new_client_id
        self._last_reconnect_attempt = 0
        self._last_payload_signature = None
        self._last_update_sent = 0
        self.connect()

    def _freeze(self, value):
        if isinstance(value, dict):
            return tuple(sorted((k, self._freeze(v)) for k, v in value.items()))
        if isinstance(value, list):
            return tuple(self._freeze(v) for v in value)
        return value

    def _payload_signature(self, payload: dict):
        # Ignore timer-only changes. Discord runs the progress timer itself.
        ignored = {"start", "end"}
        return tuple(
            sorted(
                (k, self._freeze(v))
                for k, v in payload.items()
                if k not in ignored
            )
        )

    def _payload_summary(self, payload: dict) -> str:
        from src.core.logger import make_table

        details = payload.get("details") or "Unknown"
        state = payload.get("state") or "Connected"

        has_timer = bool(payload.get("start") or payload.get("end"))
        has_art = bool(payload.get("large_image"))
        has_small = bool(payload.get("small_image"))

        button_count = len(payload.get("buttons") or [])

        activity = payload.get("activity_type")
        if hasattr(activity, "name"):
            activity_text = activity.name.title()
        else:
            activity_text = "Watching"

        return make_table(
            "Discord RPC",
            {
                "Activity": activity_text,
                "Details": details,
                "State": state,
                "Timer": "yes" if has_timer else "no",
                "Large Art": "yes" if has_art else "no",
                "Small Icon": "yes" if has_small else "no",
                "Buttons": str(button_count),
                "Pipe": str(getattr(self, "pipe", "?")),
            },
            icon="🎮",
        )

    def update(
        self,
        details: str,
        state: str,
        image_url: Optional[str] = None,
        small_image: Optional[str] = None,
        small_text: Optional[str] = None,
        large_text: Optional[str] = None,
        start_timestamp: Optional[int] = None,
        end_timestamp: Optional[int] = None,
        buttons: Optional[list] = None,
        activity_type: Optional[ActivityType] = None,
        party_id: Optional[str] = None,
        join_secret: Optional[str] = None,
        **kwargs
    ):
        if not self.connected or not self.rpc:
            self.connect()
            if not self.connected or not self.rpc:
                return

        if not image_url and "large_image" in kwargs:
            image_url = kwargs["large_image"]
        if not start_timestamp and "start_time" in kwargs:
            start_timestamp = kwargs["start_time"]
        if not end_timestamp and "end_time" in kwargs:
            end_timestamp = kwargs["end_time"]

        try:
            details = str(details or "Watching Content")[:128]
            state = str(state)[:128] if state else None

            if activity_type is None:
                activity_type = ActivityType.WATCHING

            # Keep the enum object if possible. pypresence 4.6.1 supports ActivityType directly.
            if hasattr(activity_type, "value"):
                safe_activity_type = activity_type
            else:
                safe_activity_type = int(activity_type)

            large_image = str(image_url).strip() if image_url else None

            # Do not send a missing Discord application asset key.
            # If the app does not have an asset named stremio_logo, Discord shows '?'.
            if large_image == "stremio_logo":
                large_image = None

            elif isinstance(large_image, str) and len(large_image) > 256:
                logger.warning("RPC: large_image URL too long; removing large image.")
                large_image = None

            if isinstance(small_image, str):
                small_image = small_image.strip()

                if small_image == "stremio_logo":
                    small_image = None

                elif len(small_image) > 256:
                    logger.warning(f"RPC: small_image URL too long ({len(small_image)}); removing small image. prefix={small_image[:140]}")
                    small_image = None

            payload = {
                "activity_type": safe_activity_type,
                "details": details,
                "state": state,
                "large_image": large_image,
                "large_text": str(large_text)[:128] if large_text else details,
                "small_image": small_image,
                "small_text": str(small_text)[:128] if small_text else None,
                "start": start_timestamp,
                "end": end_timestamp,
                "buttons": buttons,
                "party_id": party_id,
                "join": join_secret,
                "party_size": [1, 100] if party_id else None,
            }

            payload = {k: v for k, v in payload.items() if v is not None}

            signature = self._payload_signature(payload)
            now = time.time()

            # Do not spam Discord with the same presence every 1–2 seconds.
            if (
                self._last_payload_signature == signature
                and now - self._last_update_sent < self.min_update_interval
            ):
                return

            # Only log the table if content changed
            if self._last_payload_signature != signature:
                logger.info(self._payload_summary(payload))

            self.rpc.update(**payload)

            self._last_update_sent = now
            self._last_payload_signature = signature

        except (InvalidPipe, PipeClosed, BrokenPipeError, AttributeError, OSError) as e:
            logger.warning(f"RPC pipe closed; will retry after cooldown. reason={e.__class__.__name__}")
            self.connected = False

            try:
                if self.rpc:
                    self.rpc.close()
            except Exception:
                pass

            self.rpc = None
            self._last_reconnect_attempt = time.time()

        except Exception as e:
            logger.error(f"RPC Update Failed: {e}")
            self.connected = False

            try:
                if self.rpc:
                    self.rpc.close()
            except Exception:
                pass

            self.rpc = None
            self._last_reconnect_attempt = time.time()

    def clear(self):
        if self.rpc and self.connected:
            try:
                self.rpc.clear()
            except Exception:
                pass

    def close(self):
        if self.rpc:
            try:
                self.rpc.close()
            except Exception:
                pass

        self.rpc = None
        self.connected = False
