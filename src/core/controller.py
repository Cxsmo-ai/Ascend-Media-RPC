import logging
import hashlib
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from typing import Optional, Dict
from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.auth.sign_pythonrsa import PythonRSASigner

logger = logging.getLogger("stremio-rpc")

ADB_KEY_PATH = os.path.expanduser("~/.android/adbkey")

class StremioController:
    def __init__(self, host: str, port: int = 5555):
        self.host = host
        self.port = port
        self.device: Optional[AdbDeviceTcp] = None
        self.connected = False
        self.last_app_focus = ""
        self.last_app_package = None
        self._position_anchor_key = None
        self._position_anchor_ms = 0
        self._position_anchor_time_ms = 0
        self._logcat_lock = threading.Lock()
        self._logcat_playback_state = None
        self._logcat_thread = None
        self._logcat_stop = threading.Event()
        self.playback_logcat_enabled = False
        self._logcat_failures = 0
        self._logcat_disabled_until = 0
        self._connect_lock = threading.Lock()
        self.last_connect_error = ""
        self.last_disconnect_reason = ""
        # Metadata Toggle: Set False to disable intensive UI scraping (Wako Heist)
        self.metadata_snooping_enabled = os.environ.get('ENABLE_WAKO_METADATA', 'True').lower() == 'true'

    def connect(self) -> bool:
        """Synchronous connection to ADB"""
        if not self.host:
            self.last_connect_error = "ADB host is empty"
            return False
        if not self._connect_lock.acquire(blocking=False):
            self.last_connect_error = "ADB connection already in progress"
            return False
        try:
            self.stop_playback_logcat_watcher()
            if self.device:
                try:
                    self.device.close()
                except Exception:
                    pass
                self.device = None
            self.connected = False
            signer = self._load_adb_signer()

            self.device = self._create_adb_device()
            
            # Connect synchronously
            self.device.connect(rsa_keys=[signer] if signer else [], auth_timeout_s=3)

            self.connected = True
            self.last_connect_error = ""
            self.last_disconnect_reason = ""
            if self.playback_logcat_enabled:
                self.start_playback_logcat_watcher()
            return True
        except Exception as e:
            self.last_connect_error = str(e)
            logger.error(f"Connect failed to {self.host}:{self.port}: {e}")
            self.connected = False
            return False
        finally:
            self._connect_lock.release()

    def _load_adb_signer(self):
        if not os.path.exists(ADB_KEY_PATH):
            return None
        try:
            with open(ADB_KEY_PATH) as f:
                priv_key = f.read()
            with open(ADB_KEY_PATH + '.pub') as f:
                pub_key = f.read()
            return PythonRSASigner(pub_key, priv_key)
        except Exception:
            return None

    def _create_adb_device(self, timeout_s: float = 15.0):
        return AdbDeviceTcp(self.host, self.port, default_transport_timeout_s=timeout_s)

    def mark_disconnected(self, reason: str = ""):
        self.connected = False
        self.last_disconnect_reason = reason or "ADB connection lost"
        self.stop_playback_logcat_watcher()
        try:
            if self.device:
                self.device.close()
        except Exception:
            pass
        self.device = None

    def start_playback_logcat_watcher(self):
        if not self.playback_logcat_enabled:
            return
        if self._logcat_thread and self._logcat_thread.is_alive():
            return
        if not self.device or not self.connected:
            return
        self._logcat_stop.clear()
        self._logcat_thread = threading.Thread(target=self._logcat_playback_loop, daemon=True)
        self._logcat_thread.start()

    def stop_playback_logcat_watcher(self):
        self._logcat_stop.set()

    def _logcat_playback_loop(self, run_once=False):
        command = "logcat -v time | grep --line-buffered 'PlaybackState {'"
        while not self._logcat_stop.is_set() and self.connected:
            stream_device = None
            if time.time() < self._logcat_disabled_until:
                time.sleep(5)
                continue
            try:
                stream_device = self._create_adb_device(timeout_s=4.0)
                signer = self._load_adb_signer()
                stream_device.connect(rsa_keys=[signer] if signer else [], auth_timeout_s=5)
                stream = stream_device.streaming_shell(command)
                for chunk in stream:
                    if self._logcat_stop.is_set():
                        break
                    text = chunk.decode("utf-8", errors="ignore") if isinstance(chunk, bytes) else str(chunk)
                    for line in text.splitlines():
                        parsed = self._parse_logcat_playback_state(line)
                        if parsed:
                            self._logcat_failures = 0
                            self._record_logcat_playback_state(parsed["state_code"], parsed["position"])
            except Exception as e:
                self._logcat_failures += 1
                if self._logcat_failures == 1:
                    logger.debug(f"Playback logcat watcher unavailable: {e}")
                if self._logcat_failures >= 3:
                    self._logcat_disabled_until = time.time() + 60
                    logger.info("Playback logcat watcher paused for 60s after repeated timeouts; using media_session timing fallback.")
            finally:
                if stream_device:
                    try:
                        stream_device.close()
                    except Exception:
                        pass
            if run_once:
                break
            if not self._logcat_stop.is_set():
                time.sleep(2)

    def _parse_logcat_playback_state(self, line: str):
        match = re.search(r"state=(\d+),\s*position=(\d+)", line or "")
        if not match:
            return None
        return {"state_code": int(match.group(1)), "position": int(match.group(2))}

    def _record_logcat_playback_state(self, state_code: int, position: int):
        now = time.time()
        try:
            state_code = int(state_code)
            position = max(0, int(position))
        except (TypeError, ValueError):
            return
        state = "playing" if state_code in (3, 4, 5, 6) else "paused" if state_code == 2 else "stopped"
        with self._logcat_lock:
            self._logcat_playback_state = {
                "state_code": state_code,
                "state": state,
                "position": position,
                "received_at": now,
            }

    def _fresh_logcat_playback_state(self, max_age=3.0):
        with self._logcat_lock:
            snapshot = dict(self._logcat_playback_state or {})
        if not snapshot:
            return None
        if time.time() - float(snapshot.get("received_at") or 0) > max_age:
            return None
        return snapshot

    def get_device_name(self) -> str:
        """Fetch device model name with active caching to prevent ADB spam"""
        if not self.device or not self.connected:
            return "Android TV"
        
        # Return cached name if already found
        if hasattr(self, "_cached_device_name") and self._cached_device_name != "Android TV":
            return self._cached_device_name

        try:
            # 1. Try to get Manufacturer and Model with a slightly safer shell execution
            manufacturer = self.device.shell("getprop ro.product.manufacturer", timeout_s=1.0).strip()
            model = self.device.shell("getprop ro.product.model", timeout_s=1.0).strip()
            
            # 2. Clean up & Cache
            result = "Android TV"
            if manufacturer and model:
                if model.lower().startswith(manufacturer.lower()):
                    result = model
                else:
                    result = f"{manufacturer} {model}"
            elif model:
                result = model
            else:
                # 3. Fallback to hostname
                hostname = self.device.shell("getprop net.hostname", timeout_s=1.0).strip()
                if hostname:
                    result = hostname
            
            # Lock it in
            self._cached_device_name = result
            return result
        except Exception as e:
            # Log only if we've never succeeded before, avoid spamming 10054
            if not hasattr(self, "_cached_device_name"):
                logger.warning(f"Initial device name lookup failed (will retry): {e}")
            return getattr(self, "_cached_device_name", "Android TV")

    def get_playback_status(self, wako_mode: bool = False) -> Dict:
        """Synchronous status check with Clock Synchronization and Focus Detection"""
        if not self.device or not self.connected:
            return {"playing": False, "state": "disconnected"}

        # Fetch Dumpsys, Uptime (optional), and Focus
        cmd = "dumpsys media_session"
        
        fetch_uptime = False
        if not getattr(self, "clock_offset", None) or (time.time() - getattr(self, "last_clock_sync", 0) > 5):
            fetch_uptime = True
            cmd += " && echo '|UPTIME_DIV|' && cat /proc/uptime"
        
        cmd += " && echo '|FOCUS_DIV|' && dumpsys window | grep mCurrentFocus"
        
        try:
            raw_out = self.device.shell(cmd)
            self._shell_failures = 0 
        except Exception as e:
            self._shell_failures = getattr(self, "_shell_failures", 0) + 1
            if self._shell_failures < 3:
                logger.debug(f"ADB shell timeout ({self._shell_failures}/3): {e}")
            if self._shell_failures >= 3:
                logger.info("ADB connection lost or device asleep; auto-reconnect will keep trying.")
                self.mark_disconnected(str(e))
            return {"playing": False, "state": "timeout"}
        
        uptime_str = None
        current_focus = ""
        result = raw_out

        if "|FOCUS_DIV|" in result:
            result, focus_section = result.split("|FOCUS_DIV|", 1)
            current_focus = focus_section.strip()
        if "|UPTIME_DIV|" in result:
            result, uptime_section = result.split("|UPTIME_DIV|", 1)
            uptime_str = uptime_section.strip().split()[0] if uptime_section.strip() else None
        self.last_app_focus = current_focus

        status = {
            "playing": False, "app": None, "title": None, "position": 0, "duration": 0,
            "state": "stopped", "timestamp": 0, "focus": current_focus
        }

        if not result: return status
            
        try:
            # --- Parsing Logic ---
            current_app = None
            MEDIA_APPS = ["app.wako", "com.stremio.one", "com.brouken.player", "org.videolan.vlc", "com.google.android.youtube.tv"]
            blocks = result.split("Session ")
            target_block = None
            
            for block in blocks:
                if "package=" not in block: continue
                this_app = None
                for app in MEDIA_APPS:
                    if f"package={app}" in block:
                        this_app = app
                        break
                
                # If we aren't looking for Wako specifically, skip other apps unless focused
                if wako_mode and not this_app:
                    if "app.wako" in current_focus: 
                        current_app = "Wako"
                    else: 
                        continue
                
                s_match = re.search(r'state=PlaybackState \{state=(\d+)', block)
                if s_match:
                    raw_s = int(s_match.group(1))
                    if raw_s in [2, 3, 4, 5, 6]:
                        target_block = block
                        current_app = this_app or current_app
                        # If we found a playing session (3), that's our winner
                        if raw_s == 3: break
            
            if not target_block:
                if wako_mode and "app.wako" in current_focus: status["app"] = "Wako"
                return status

            status["app"] = current_app or "External Player"
            self.last_app_package = status["app"]

            # Parse State
            state_match = re.search(r'state=PlaybackState \{state=(\d+)', target_block)
            raw_state = int(state_match.group(1)) if state_match else 0
            if raw_state in [3, 4, 5, 6]: status["playing"] = True; status["state"] = "playing"
            elif raw_state == 2: status["state"] = "paused"
            else: status["state"] = "stopped"; return status

            # Duration Parsing
            dur_match = re.search(r'duration=(\d+)', target_block)
            status["duration"] = int(dur_match.group(1)) if dur_match else 0
            if status["duration"] <= 0:
                 cd_match = re.search(r'contentDuration=(\d+)', target_block)
                 if cd_match: status["duration"] = int(cd_match.group(1))
            if status["duration"] <= 0:
                 meta_match = re.search(r'(?:android\.media\.metadata\.DURATION|DURATION)=([0-9]+)', target_block, re.IGNORECASE)
                 if meta_match: status["duration"] = int(meta_match.group(1))
            
            if status["duration"] > 0: self.last_duration = status["duration"]
            elif getattr(self, "last_duration", 0) > 0: status["duration"] = self.last_duration
            
            # Parse Metadata before position anchoring so title changes reset projection.
            desc_match = re.search(r'description=([^,]+)', target_block)
            if desc_match:
                status["title"] = desc_match.group(1).strip()
                self.last_title_cache = status["title"]
                tmatch = re.search(r'(?:S|Season\s*)(\d+)\s*(?:E|Episode\s*)(\d+)', status["title"], re.IGNORECASE)
                if tmatch:
                    status["season"] = int(tmatch.group(1))
                    status["episode"] = int(tmatch.group(2))
                else:
                    tmatch = re.search(r'(\d+)x(\d+)', status["title"])
                    if tmatch:
                        status["season"] = int(tmatch.group(1))
                        status["episode"] = int(tmatch.group(2))

            # Parse Timestamps & Position
            pos_match = re.search(r'position=(\d+)', target_block)
            updated_match = re.search(r'updated=(\d+)', target_block)
            speed_match = re.search(r'speed=([\d\.]+)', target_block)
            base_pos = int(pos_match.group(1)) if pos_match else 0
            updated_ts = int(updated_match.group(1)) if updated_match else 0
            speed = float(speed_match.group(1)) if speed_match else 1.0
            timing_debug = {
                "raw_state": raw_state,
                "dumpsys_raw_position": base_pos,
                "dumpsys_updated": updated_ts,
                "speed": speed,
                "duration": status["duration"],
                "clock_offset": getattr(self, "clock_offset", None),
            }
            
            if speed <= 0.0 and status["playing"]:
                status["playing"] = False
                status["state"] = "paused"
            
            local_now_ms = time.time() * 1000
            if fetch_uptime and uptime_str:
                try:
                    fetched_uptime_ms = float(uptime_str) * 1000
                    self.clock_offset = local_now_ms - fetched_uptime_ms
                    self.last_clock_sync = time.time()
                except: pass
            
            device_uptime_ms = (local_now_ms - getattr(self, "clock_offset", 0)) if getattr(self, "clock_offset", None) else 0
            timing_debug["device_uptime_ms"] = int(device_uptime_ms) if device_uptime_ms else 0
            
            # Anchor to the raw device reported position
            status["position"] = base_pos
            
            # If the device reports a last-update timestamp, project to 'now'
            if status["state"] == "playing" and updated_ts > 0 and device_uptime_ms > updated_ts:
                delta = device_uptime_ms - updated_ts
                projected = int(base_pos + (delta * speed))
                if status["duration"] > 0 and projected > status["duration"]: projected = status["duration"]
                status["position"] = projected
            timing_debug["dumpsys_projected_position"] = status["position"]

            status["position"] = self._project_realtime_position(status, status["position"], speed, local_now_ms)
            timing_debug["local_projected_position"] = status["position"]

            # Anti-Reset Glitch
            if status["position"] < 2000 and getattr(self, "last_position_cache", 0) > 5000:
                desc_check = re.search(r'description=([^,]+)', target_block)
                if desc_check and desc_check.group(1).strip() == getattr(self, "last_title_cache", None):
                    status["position"] = self.last_position_cache

            logcat_state = self._fresh_logcat_playback_state()
            if logcat_state and status.get("state") in ("playing", "paused"):
                timing_debug["logcat_state"] = logcat_state.get("state_code")
                timing_debug["logcat_position"] = logcat_state.get("position")
                timing_debug["logcat_age_ms"] = int((time.time() - float(logcat_state.get("received_at") or 0)) * 1000)
                status["state"] = logcat_state["state"]
                status["playing"] = logcat_state["state"] == "playing"
                status["position"] = self._project_logcat_position(
                    status,
                    logcat_state["position"],
                    local_now_ms,
                    logcat_state.get("received_at"),
                )
                status["timing_source"] = "logcat"
            else:
                timing_debug["logcat_state"] = None
                timing_debug["logcat_position"] = None
                timing_debug["logcat_age_ms"] = None
                status["timing_source"] = "dumpsys"
            timing_debug["source"] = status["timing_source"]
            timing_debug["final_position"] = status["position"]
            status["timing_debug"] = timing_debug

            if status["position"] > 0: self.last_position_cache = status["position"]

            status["calc_time"] = local_now_ms / 1000.0
            return status

        except Exception as e:
            logger.error(f"Status check failed: {e}")
            return {"playing": False, "state": "error"}

    def _project_logcat_position(self, status: Dict, reported_position: int, local_now_ms: float, received_at: float) -> int:
        try:
            reported_position = max(0, int(reported_position or 0))
            duration = int(status.get("duration") or 0)
            received_ms = float(received_at or 0) * 1000
        except (TypeError, ValueError):
            return reported_position

        projected = reported_position
        if status.get("state") == "playing" and received_ms > 0:
            projected += max(0, int(local_now_ms - received_ms))
        if duration > 0:
            projected = min(projected, duration)

        self._position_anchor_key = (
            status.get("app"),
            status.get("title"),
            duration,
            "logcat",
        )
        self._position_anchor_ms = projected
        self._position_anchor_time_ms = local_now_ms
        return projected

    def _project_realtime_position(self, status: Dict, reported_position: int, speed: float, local_now_ms: float) -> int:
        try:
            reported_position = max(0, int(reported_position or 0))
            duration = int(status.get("duration") or 0)
            speed = float(speed or 1.0)
        except (TypeError, ValueError):
            return reported_position

        key = (
            status.get("app"),
            status.get("title"),
            duration,
            "dumpsys",
        )

        if status.get("state") != "playing" or speed <= 0:
            self._position_anchor_key = key
            self._position_anchor_ms = reported_position
            self._position_anchor_time_ms = local_now_ms
            return reported_position

        if self._position_anchor_key != key or not self._position_anchor_time_ms:
            self._position_anchor_key = key
            self._position_anchor_ms = reported_position
            self._position_anchor_time_ms = local_now_ms
            return reported_position

        elapsed_ms = max(0, local_now_ms - self._position_anchor_time_ms)
        projected = int(self._position_anchor_ms + (elapsed_ms * speed))
        if duration > 0:
            projected = min(projected, duration)

        # MediaSession often reports the same raw position for several samples, then jumps.
        # If the new report matches our projection, keep the older anchor for smooth time.
        # If it differs a lot, a seek happened, so reset to Android's new position.
        if abs(reported_position - projected) > 2000:
            self._position_anchor_ms = reported_position
            self._position_anchor_time_ms = local_now_ms
            return min(reported_position, duration) if duration > 0 else reported_position

        return projected

    def send_key(self, keycode: int):
        """Send a key event to the device"""
        if not self.device or not self.connected:
            return

        try:
            self.device.shell(f"input keyevent {keycode}")
        except Exception as e:
            logger.error(f"Error sending key {keycode}: {e}")

    def play_pause(self):
        """Toggle play/pause (KEYCODE_MEDIA_PLAY_PAUSE = 85)"""
        try:
            self.device.shell(f"input keyevent 85")
        except: pass

    def play(self):
        """Force play (KEYCODE_MEDIA_PLAY = 126)"""
        try:
            self.device.shell(f"input keyevent 126")
        except: pass

    def pause(self):
        """Force pause (KEYCODE_MEDIA_PAUSE = 127)"""
        try:
            self.device.shell(f"input keyevent 127")
        except: pass

    def stop(self):
        """Stop playback (KEYCODE_MEDIA_STOP = 86)"""
        try:
            self.device.shell(f"input keyevent 86")
        except: pass

    def next_track(self):
        """Next track (KEYCODE_MEDIA_NEXT = 87)"""
        try:
            self.device.shell(f"input keyevent 87")
        except: pass

    def prev_track(self):
        """Previous track (KEYCODE_MEDIA_PREVIOUS = 88)"""
        try:
            self.device.shell(f"input keyevent 88")
        except: pass

    def volume_up(self):
        """Volume Up (KEYCODE_VOLUME_UP = 24)"""
        try:
            self.device.shell(f"input keyevent 24")
        except: pass

    def volume_down(self):
        """Volume Down (KEYCODE_VOLUME_DOWN = 25)"""
        try:
            self.device.shell(f"input keyevent 25")
        except: pass

    def mute(self):
        """Toggle Mute (KEYCODE_MUTE = 164)"""
        try:
            self.device.shell(f"input keyevent 164")
        except: pass

    def next_episode_macro(self):
        """Netflix-style auto-play next: DPAD_RIGHT then ENTER"""
        try:
            self.device.shell("input keyevent 22")  # RIGHT
            time.sleep(0.3)
            self.device.shell("input keyevent 66")  # ENTER
        except: pass

    def seek_to(self, target_ms: int, current_ms: int = 0):
        """
        Wako Mode: Uses 15s key-event hops (robust for ExoPlayer).
        Direct Mode: Uses media_session dispatch seek-to (fast, direct jumping).
        Returns the best estimated position after the command.
        """
        if not self.device or not self.connected:
            return current_ms
            
        try:
            # Determine if we should use Direct Seek or Hops
            is_wako = "wako" in getattr(self, "last_app_focus", "").lower()
            
            if not is_wako:
                # DIRECT SEEK (Stremio / Standard Player)
                logger.info(f"Direct Seek -> Attempting media_session jump to {target_ms}ms")
                self.device.shell(f"media_session dispatch seek-to {target_ms}")
                return max(0, int(target_ms or 0))

            # WAKO / HOPS MODE
            if current_ms <= 0: return current_ms
            diff_ms = target_ms - current_ms
            HOP_SIZE_MS = 15000 
            landed_ms = current_ms
            
            if diff_ms > 0:
                hops = int(diff_ms / HOP_SIZE_MS)
                if hops > 40: hops = 40
                if hops > 0:
                    logger.info(f"Wako Seek -> Sending {hops} Right Clicks (15s intervals)")
                    key_cmd = " ".join(["22"] * hops)
                    self.device.shell(f"input keyevent {key_cmd}")
                    landed_ms = current_ms + (hops * HOP_SIZE_MS)
            elif diff_ms < -2000:
                hops = int(abs(diff_ms) / HOP_SIZE_MS)
                if hops > 0:
                    logger.info(f"Wako Seek -> Sending {hops} Left Clicks (15s intervals)")
                    key_cmd = " ".join(["21"] * hops)
                    self.device.shell(f"input keyevent {key_cmd}")
                    landed_ms = max(0, current_ms - (hops * HOP_SIZE_MS))
            return landed_ms

        except Exception as e:
            logger.error(f"Error seeking: {e}")
            return current_ms

    @staticmethod
    def _format_wako_ms(ms) -> str:
        try:
            total = max(0, int(ms or 0)) // 1000
        except (TypeError, ValueError):
            return "--:--"

        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)

        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    @classmethod
    def _format_wako_heist_summary(cls, data: Dict) -> str:
        title = data.get("title") or "Unknown"
        season = data.get("season")
        episode = data.get("episode")
        ep_title = data.get("ep_title")

        parts = [title]

        if season is not None and episode is not None:
            ep = f"S{int(season):02d}E{int(episode):02d}"
            if ep_title:
                ep += f" • {ep_title}"
            parts.append(ep)

        position = int(data.get("position") or 0)
        duration = int(data.get("duration") or 0)
        if duration > 0:
            parts.append(f"{cls._format_wako_ms(position)} / {cls._format_wako_ms(duration)}")

        return " • ".join(parts)

    @staticmethod
    def _clean_wako_text(text: str) -> str:
        text = (text or "").strip()
        # 1. Basic HTML Unescape
        text = text.replace("&amp;", "&").replace("&quot;", '"').replace("&apos;", "'")
        # 2. Strip ALL HTML Entities like &#127468; or &nbsp;
        text = re.sub(r"&#\d+;?", "", text)
        text = re.sub(r"&[a-zA-Z]+;", "", text)
        # 3. Strip weird bracket noise [] or ()
        text = text.replace("[]", "").replace("()", "").strip()
        # 4. Clean up whitespace
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _parse_wako_timecode_ms(text: str) -> Optional[int]:
        parts = (text or "").strip().split(":")
        if len(parts) not in (2, 3) or not all(part.isdigit() for part in parts):
            return None
        values = [int(part) for part in parts]
        if len(values) == 2:
            minutes, seconds = values
            hours = 0
        else:
            hours, minutes, seconds = values
        if minutes >= 60 or seconds >= 60:
            return None
        return ((hours * 3600) + (minutes * 60) + seconds) * 1000

    @classmethod
    def _extract_wako_progress(cls, texts) -> Dict:
        timecode = r"\d{1,2}:\d{2}(?::\d{2})?"
        for text in texts:
            match = re.search(rf"\b({timecode})\s*/\s*({timecode})\b", text)
            if not match:
                continue
            position = cls._parse_wako_timecode_ms(match.group(1))
            duration = cls._parse_wako_timecode_ms(match.group(2))
            if duration and position is not None and 0 <= position <= duration:
                return {"position": position, "duration": duration}

        split_times = []
        for text in texts:
            if re.fullmatch(timecode, text):
                parsed = cls._parse_wako_timecode_ms(text)
                if parsed is not None:
                    split_times.append(parsed)
        for idx in range(len(split_times) - 1):
            position = split_times[idx]
            duration = split_times[idx + 1]
            if duration > 0 and 0 <= position <= duration:
                return {"position": position, "duration": duration}
        return {}

    @classmethod
    def _extract_wako_progress_from_xml(cls, xml_data: str) -> Dict:
        if not xml_data:
            return {}

        texts = []
        for node in re.findall(r'(?:text|content-desc)="([^"]*)"', xml_data):
            cleaned = cls._clean_wako_text(node)
            if cleaned:
                texts.append(cleaned)

        return cls._extract_wako_progress(texts)

    @classmethod
    def _is_wako_noise(cls, text: str) -> bool:
        text = cls._clean_wako_text(text)
        if not text or len(text) < 2:
            return True
        if text.startswith("&#"):
            return True
        # Filter out flags, quality, and progress markers
        timecode = r"\d{1,2}:\d{2}(?::\d{2})?"
        if re.match(rf"^{timecode}\s*/\s*{timecode}$", text):
            return True
        if re.match(rf"^{timecode}$", text):
            return True
        if re.match(r"^\d{1,4}p$|^4K$|^HDR$|^HEVC$|^DDP$|^DSNP$|^AMZN$", text, re.IGNORECASE):
            return True
        if cls._is_wako_episode_title_noise(text):
            return True
        # Filter out flag characters/entities if they survived cleaning
        # Using literal range for Regional Indicator Symbols (Flags)
        if re.search("[\U0001F1E6-\U0001F1FF]", text): 
            return True
        if len(text) == 1 and ord(text) > 127:
            return True
        # Filter common non-title nodes
        if text.lower() in ["info", "cast", "crew", "similar", "reviews", "comments", "episodes", "available on"]:
            return True
        return False

    @classmethod
    def _is_wako_episode_title_noise(cls, text: str) -> bool:
        text = cls._clean_wako_text(text)
        if not text:
            return True
        normalized = re.sub(r"[^a-z0-9+]+", "", text.lower())
        if not normalized:
            return True
        noisy_exact = {
            "bluray", "bdrip", "brip", "webrip", "webdl", "web", "hdrip",
            "hdtv", "dvdrip", "remux", "x264", "x265", "h264", "h265",
            "hevc", "avc", "aac", "ac3", "eac3", "dd", "dd+", "ddp",
            "ddp51", "dts", "truehd", "atmos", "dolby", "primevideo",
            "netflix", "amzn", "dsnp", "hulu", "max",
        }
        if normalized in {re.sub(r"[^a-z0-9+]+", "", item.lower()) for item in noisy_exact}:
            return True
        return bool(re.fullmatch(r"(?:\d{3,4}p|4k|uhd|hdr|sdr)", normalized, re.IGNORECASE))

    @classmethod
    def _clean_wako_episode_title(cls, text: str) -> Optional[str]:
        cleaned = cls._clean_wako_text(text)
        if not cleaned or cls._is_wako_noise(cleaned) or cls._is_wako_episode_title_noise(cleaned):
            return None
        return cleaned

    @classmethod
    def _parse_wako_metadata(cls, xml_data: str) -> Dict:
        """Robust Wako XML Parser: Extracts Title, S/E, and Ep Name"""
        if not xml_data:
            return {}

        text_nodes = re.findall(r'text="([^"]+)"', xml_data)
        desc_nodes = re.findall(r'content-desc="([^"]+)"', xml_data)
        all_texts = []
        valid_texts = []
        for node in text_nodes + desc_nodes:
            cleaned = cls._clean_wako_text(node)
            if cleaned:
                all_texts.append(cleaned)
                if not cls._is_wako_noise(cleaned):
                    valid_texts.append(cleaned)

        if not valid_texts:
            return {}

        # 1. Look for combined patterns (Series - S01E01 (Title))
        for text in valid_texts:
            combined = re.search(
                r"(.+?)\s*(?:-|\u2013|\u2014)\s*(?:S|Season\s*)(\d+)\s*[:Ee]\s*(\d+)(?:\s*\((.*?)\))?",
                text,
                re.IGNORECASE
            )
            if not combined:
                combined = re.search(r"(.+?)\s*[-–]\s*(\d+)x(\d+)(?:\s*\((.*?)\))?", text, re.IGNORECASE)
            
            if combined:
                title = re.sub(r"\[.*?\]", "", combined.group(1)).strip()
                if title:
                    return {
                        "title": title,
                        "season": int(combined.group(2)),
                        "episode": int(combined.group(3)),
                        "ep_title": cls._clean_wako_episode_title(combined.group(4)) if (combined.lastindex and combined.lastindex >= 4 and combined.group(4)) else None
                    }

        # 2. Look for isolated S/E and walk backwards for title
        for i, text in enumerate(valid_texts):
            ep_match = re.search(r"\bS(\d+)\s*(?:[:Ee]\s*E?)\s*(\d+)(?:\s*\((.*?)\))?\b", text, re.IGNORECASE)
            if not ep_match:
                ep_match = re.search(r"\b(\d+)x(\d+)(?:\s*\((.*?)\))?\b", text, re.IGNORECASE)
            
            if ep_match:
                season = int(ep_match.group(1))
                episode = int(ep_match.group(2))
                ep_title = cls._clean_wako_episode_title(ep_match.group(3)) if (ep_match.lastindex and ep_match.lastindex >= 3 and ep_match.group(3)) else None
                
                # Title is usually the node BEFORE the S/E node
                title = None
                for candidate in reversed(valid_texts[:i]):
                    if not cls._is_wako_noise(candidate) and not re.search(r"\bS\d+|\d+x\d+", candidate, re.I):
                        title = candidate
                        break
                
                if title:
                    # Look-ahead for ep_title if missing
                    if not ep_title and i + 1 < len(valid_texts):
                        next_node = valid_texts[i+1]
                        ep_title = cls._clean_wako_episode_title(next_node)

                    return {
                        "title": title,
                        "season": season,
                        "episode": episode,
                        "ep_title": ep_title
                    }

        # 3. Fallback to Movie Title (Only if no S/E found anywhere)
        for text in valid_texts:
            if len(text) > 0:
                return {"title": text, "season": None, "episode": None}

        return {}

    @classmethod
    def _wako_xml_has_player_markers(cls, xml_data: str) -> bool:
        if not xml_data or "app.wako" not in xml_data:
            return False

        lower_xml = xml_data.lower()
        non_player_markers = (
            "watch trailer",
            "trailer",
            "cast & crew",
            "similar",
            "reviews",
            "comments",
            "available on",
            "episodes",
            "season ",
            "like",
            "liked",
            "watchlist",
        )
        has_non_player_context = any(marker in lower_xml for marker in non_player_markers)

        strong_markers = (
            "exo_content_frame",
            "exo_subtitles",
            "exo_progress",
            "exo_play",
            "exo_pause",
            "exo_ffwd",
            "exo_rew",
            "StyledPlayerView",
            "PlayerView",
            "SurfaceView",
        )
        if any(marker in xml_data for marker in strong_markers):
            return True

        timecode = r"\d{1,2}:\d{2}(?::\d{2})?"
        if re.search(rf"\b{timecode}\s*/\s*{timecode}\b", xml_data):
            if has_non_player_context and not any(marker in xml_data for marker in ("exo_", "PlayerView", "StyledPlayerView")):
                return False
            return True

        has_time = len(re.findall(rf'(?:text|content-desc)="({timecode})"', xml_data)) >= 2
        has_controls = any(marker in xml_data.lower() for marker in ("play", "pause", "rewind", "forward", "seek"))
        return has_time and has_controls and not has_non_player_context

    @classmethod
    def _wako_xml_is_hidden_player_shell(cls, xml_data: str) -> bool:
        if not xml_data or "app.wako" not in xml_data:
            return False
        if cls._wako_xml_has_player_markers(xml_data):
            return False

        summary = cls._summarize_wako_nodes(xml_data)
        if summary.get("text_nodes") or summary.get("content_desc_nodes") or summary.get("clickable_nodes"):
            return False

        classes = summary.get("classes") or {}
        packages = summary.get("packages") or {}
        return (
            packages.get("app.wako", 0) >= 2
            and summary.get("node_count", 0) <= 5
            and classes.get("android.widget.ScrollView", 0) >= 1
            and classes.get("android.widget.FrameLayout", 0) >= 1
        )

    @classmethod
    def _wako_ui_marker_report(cls, xml_data: str) -> Dict:
        xml_data = xml_data or ""
        lower_xml = xml_data.lower()
        text_nodes = re.findall(r'(?:text|content-desc)="([^"]+)"', xml_data)
        cleaned_texts = []
        for node in text_nodes:
            cleaned = cls._clean_wako_text(node)
            if cleaned and cleaned not in cleaned_texts:
                cleaned_texts.append(cleaned)

        strong_markers = [
            marker for marker in (
                "exo_content_frame",
                "exo_subtitles",
                "exo_progress",
                "exo_play",
                "exo_pause",
                "exo_ffwd",
                "exo_rew",
                "StyledPlayerView",
                "PlayerView",
                "SurfaceView",
            )
            if marker in xml_data
        ]
        blocker_markers = [
            marker for marker in (
                "watch trailer",
                "trailer",
                "cast & crew",
                "similar",
                "reviews",
                "comments",
                "available on",
                "episodes",
                "season ",
                "like",
                "liked",
                "watchlist",
            )
            if marker in lower_xml
        ]
        timecode = r"\d{1,2}:\d{2}(?::\d{2})?"
        time_pairs = re.findall(rf"\b({timecode})\s*/\s*({timecode})\b", xml_data)
        split_times = re.findall(rf'(?:text|content-desc)="({timecode})"', xml_data)
        control_markers = [
            marker for marker in ("play", "pause", "rewind", "forward", "seek")
            if marker in lower_xml
        ]
        is_wako = "app.wako" in xml_data
        has_player = cls._wako_xml_has_player_markers(xml_data)
        hidden_player_shell = cls._wako_xml_is_hidden_player_shell(xml_data)

        if not xml_data:
            classification = "empty"
        elif not is_wako:
            classification = "other_app"
        elif has_player:
            classification = "player"
        elif hidden_player_shell:
            classification = "hidden_player_shell"
        elif "search movies, shows, people" in lower_xml:
            classification = "search"
        elif any(marker in blocker_markers for marker in ("trailer", "watch trailer")):
            classification = "trailer_or_details"
        elif any(marker in blocker_markers for marker in ("like", "liked", "watchlist")):
            classification = "likes_or_watchlist"
        elif blocker_markers:
            classification = "details"
        else:
            classification = "unknown_non_player"

        return {
            "classification": classification,
            "heist_allowed": bool(has_player),
            "hidden_player_shell": bool(hidden_player_shell),
            "is_wako": bool(is_wako),
            "xml_length": len(xml_data),
            "player_markers": strong_markers,
            "blocker_markers": blocker_markers,
            "control_markers": control_markers,
            "time_pairs": [f"{start} / {end}" for start, end in time_pairs[:5]],
            "split_times": split_times[:8],
            "text_samples": cleaned_texts[:30],
            "node_summary": cls._summarize_wako_nodes(xml_data),
            "metadata_candidate": cls._parse_wako_metadata(xml_data) if has_player else {},
            "progress_candidate": cls._extract_wako_progress(cleaned_texts) if has_player else {},
        }

    @classmethod
    def _summarize_wako_nodes(cls, xml_data: str) -> Dict:
        summary = {
            "node_count": 0,
            "packages": {},
            "classes": {},
            "resource_ids": [],
            "clickable_nodes": [],
            "focused_nodes": [],
            "text_nodes": [],
            "content_desc_nodes": [],
        }
        if not xml_data:
            return summary

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError:
            return summary

        def bump(bucket, value):
            if value:
                bucket[value] = bucket.get(value, 0) + 1

        for node in root.iter("node"):
            attrs = node.attrib
            summary["node_count"] += 1
            bump(summary["packages"], attrs.get("package"))
            bump(summary["classes"], attrs.get("class"))

            resource_id = attrs.get("resource-id") or ""
            if resource_id and resource_id not in summary["resource_ids"]:
                summary["resource_ids"].append(resource_id)

            record = {
                "text": cls._clean_wako_text(attrs.get("text") or ""),
                "desc": cls._clean_wako_text(attrs.get("content-desc") or ""),
                "resource_id": resource_id,
                "class": attrs.get("class") or "",
                "package": attrs.get("package") or "",
                "bounds": attrs.get("bounds") or "",
                "clickable": attrs.get("clickable") == "true",
                "focused": attrs.get("focused") == "true",
                "selected": attrs.get("selected") == "true",
                "enabled": attrs.get("enabled") == "true",
            }

            if record["text"]:
                summary["text_nodes"].append(record)
            if record["desc"]:
                summary["content_desc_nodes"].append(record)
            if record["clickable"]:
                summary["clickable_nodes"].append(record)
            if record["focused"]:
                summary["focused_nodes"].append(record)

        for key in ("resource_ids", "clickable_nodes", "focused_nodes", "text_nodes", "content_desc_nodes"):
            summary[key] = summary[key][:80]
        return summary

    def map_wako_ui(self) -> Dict:
        if not self.device or not self.connected:
            return {"error": "ADB is not connected", "classification": "disconnected", "heist_allowed": False}

        diagnostics = {}
        dump_attempts = []

        def safe_shell(name, command):
            try:
                output = self.device.shell(command)
                diagnostics[name] = output
                return output
            except Exception as exc:
                diagnostics[name] = f"{exc.__class__.__name__}: {exc}"
                return ""

        focus = safe_shell("focus", "dumpsys window | grep mCurrentFocus")
        safe_shell("resumed_activity", "dumpsys activity activities | grep mResumedActivity")
        safe_shell("top_activity", "dumpsys activity top | grep ACTIVITY")

        xml_data = ""
        error = None
        dump_commands = [
            (
                "compressed_file",
                "uiautomator dump --compressed /sdcard/wako_mapper.xml",
                "cat /sdcard/wako_mapper.xml",
            ),
            (
                "standard_file",
                "uiautomator dump /sdcard/wako_mapper.xml",
                "cat /sdcard/wako_mapper.xml",
            ),
            (
                "compressed_stdout",
                "uiautomator dump --compressed /dev/tty",
                None,
            ),
        ]

        for name, dump_cmd, read_cmd in dump_commands:
            attempt = {"name": name, "dump_cmd": dump_cmd, "read_cmd": read_cmd, "ok": False}
            try:
                dump_out = self.device.shell(dump_cmd)
                attempt["dump_output"] = (dump_out or "")[:300]
                xml_data = self.device.shell(read_cmd) if read_cmd else dump_out
                if xml_data and "<hierarchy" in xml_data:
                    attempt["ok"] = True
                    dump_attempts.append(attempt)
                    break
                attempt["error"] = "no hierarchy XML returned"
            except Exception as exc:
                error = exc
                attempt["error"] = f"{exc.__class__.__name__}: {exc}"
            dump_attempts.append(attempt)

        if not xml_data or "<hierarchy" not in xml_data:
            lower_focus = (focus or "").lower()
            classification = "wako_no_xml"
            if "app.wako" not in lower_focus:
                classification = "other_app_no_xml"
            elif "mainactivity" in lower_focus:
                classification = "wako_mainactivity_no_xml"
            return {
                "error": f"UI dump failed: {error}" if error else "UI dump returned no hierarchy XML",
                "focus": focus,
                "classification": classification,
                "heist_allowed": False,
                "dump_attempts": dump_attempts,
                "diagnostics": diagnostics,
                "xml_length": 0,
                "xml_hash": "nohash",
                "raw_xml": xml_data or "",
            }

        report = self._wako_ui_marker_report(xml_data)
        report["focus"] = focus.strip() if isinstance(focus, str) else ""
        report["xml_hash"] = hashlib.sha1((xml_data or "").encode("utf-8", errors="ignore")).hexdigest()[:12]
        report["dump_attempts"] = dump_attempts
        report["diagnostics"] = diagnostics
        report["raw_xml"] = xml_data or ""
        return report

    def capture_screenshot(self, local_path: str) -> Dict:
        if not self.device or not self.connected:
            return {"ok": False, "error": "ADB is not connected"}
        remote_path = "/sdcard/wako_mapper_screen.png"
        try:
            self.device.shell(f"screencap -p {remote_path}")
            self.device.pull(remote_path, local_path, read_timeout_s=15.0)
            try:
                self.device.shell(f"rm {remote_path}")
            except Exception:
                pass
            return {"ok": os.path.exists(local_path), "path": local_path}
        except Exception as exc:
            return {"ok": False, "error": f"{exc.__class__.__name__}: {exc}", "path": local_path}

    def launch_deep_link(self, url: str):
        """
        Force stop Stremio and launch a deep link.
        URL formats:
        - stremio://detail/movie/tt1234567
        - stremio://detail/series/tt1234567/tt1234567:1:1
        """
        if not self.device or not self.connected:
            return False
            
        try:
            self.device.shell("am force-stop com.stremio.one")
            cmd = f'am start -a android.intent.action.VIEW -f 0x14000000 -d "{url}"'
            logger.info(f"Running ADB Command: {cmd}")
            output = self.device.shell(cmd)
            logger.info(f"ADB Output: {output}")
            
            if "Error" in output or "does not exist" in output:
                 logger.error(f"Implicit launch failed: {output}")
                 return False
            
            logger.info(f"Launched Deep Link: {url}")
            return True
            
        except Exception as e:
            logger.error(f"Launch Deep Link Failed: {e}")
            return False

    def execute_wako_heist(self, needs_wake: bool = True, xml_data: str = None) -> Dict:
        """Wako Telemetry Heist: Ghost Keystroke -> UI Dump -> Data Extract -> Cleanup
        
        Executes the rapid-fire ADB sequence to extract title and episode
        from Wako's ExoPlayer overlay.
        """
        if not getattr(self, 'metadata_snooping_enabled', True):
            return {}
            
        if not self.device or not self.connected:
            return {}

        heist_started = time.monotonic()
        logger.info(f"Wako Heist DEBUG: start needs_wake={needs_wake}, xml_prefetched={bool(xml_data)}")

        was_playing = None
        try:
            probe_started = time.monotonic()
            state_probe = self.device.shell("dumpsys media_session | grep 'state=PlaybackState' | head -n 1", timeout_s=4.0)
            probe_ms = int((time.monotonic() - probe_started) * 1000)
            state_match = re.search(r"state=PlaybackState \{state=(\d+)", state_probe or "")
            if state_match:
                was_playing = int(state_match.group(1)) in (3, 4, 5, 6)
            logger.info(f"Wako Heist DEBUG: media_probe_ms={probe_ms} was_playing={was_playing} line={(state_probe or '').strip()[:120]}")
        except Exception as e:
            probe_ms = int((time.monotonic() - probe_started) * 1000) if 'probe_started' in locals() else None
            logger.info(f"Wako Heist DEBUG: media_probe_failed_ms={probe_ms} error={e}")
            was_playing = None

        # Try up to 2 attempts with a hard pause strategy
        for attempt in range(2):
            attempt_started = time.monotonic()
            wake_ms = 0
            render_ms = 0
            dump_ms = 0
            gate_ms = 0
            parse_ms = 0
            xml_len = 0
            marker_ok = None
            try:
                current_xml = xml_data if attempt == 0 and xml_data else None
                
                if not current_xml:
                    if needs_wake:
                        delay = 1.5 if attempt == 0 else 3.0
                        # DPAD_CENTER wakes Wako's player overlay without forcing pause/play state.
                        wake_started = time.monotonic()
                        self.device.shell("input keyevent 23")
                        wake_ms = int((time.monotonic() - wake_started) * 1000)
                        
                        logger.info(f"Wako Heist DEBUG: attempt={attempt+1} wake_key=DPAD_CENTER wake_ms={wake_ms} render_wait={delay}s")
                        render_started = time.monotonic()
                        time.sleep(delay)
                        render_ms = int((time.monotonic() - render_started) * 1000)
                    
                    # Give uiautomator enough time on Shield/Wako; 4s caused blank dumps.
                    dump_started = time.monotonic()
                    current_xml = self.device.shell("uiautomator dump /sdcard/window_dump.xml > /dev/null && cat /sdcard/window_dump.xml", timeout_s=9.0)
                    dump_ms = int((time.monotonic() - dump_started) * 1000)
                    
                    if needs_wake:
                        logger.debug("Wako Heist: leaving playback state unchanged after dump.")
                    
                    if not current_xml:
                        logger.warning(
                            f"Wako Heist DEBUG: attempt={attempt+1} empty_dump "
                            f"wake_ms={wake_ms} render_ms={render_ms} dump_ms={dump_ms} "
                            f"total_ms={int((time.monotonic() - attempt_started) * 1000)}"
                        )
                        continue

                    xml_len = len(current_xml)
                    gate_started = time.monotonic()
                    marker_ok = self._wako_xml_has_player_markers(current_xml)
                    gate_ms = int((time.monotonic() - gate_started) * 1000)
                    if not marker_ok:
                        logger.info(
                            f"Wako Heist DEBUG: attempt={attempt+1} gate_failed "
                            f"xml_len={xml_len} wake_ms={wake_ms} render_ms={render_ms} "
                            f"dump_ms={dump_ms} gate_ms={gate_ms} total_ms={int((time.monotonic() - attempt_started) * 1000)}"
                        )
                        continue
                else:
                    xml_len = len(current_xml)
                    gate_started = time.monotonic()
                    marker_ok = self._wako_xml_has_player_markers(current_xml)
                    gate_ms = int((time.monotonic() - gate_started) * 1000)

                # Debug: Log raw XML length
                logger.debug(f"Wako Heist: Raw XML length={len(current_xml)}")
                parse_started = time.monotonic()
                progress = self._extract_wako_progress_from_xml(current_xml)

                parsed = self._parse_wako_metadata(current_xml)
                parse_ms = int((time.monotonic() - parse_started) * 1000)
                if parsed:
                    logger.info(
                        f"Wako Heist DEBUG: attempt={attempt+1} success "
                        f"xml_len={xml_len} marker_ok={marker_ok} wake_ms={wake_ms} "
                        f"render_ms={render_ms} dump_ms={dump_ms} gate_ms={gate_ms} parse_ms={parse_ms} "
                        f"total_ms={int((time.monotonic() - attempt_started) * 1000)} "
                        f"result={self._format_wako_heist_summary(parsed)}"
                    )
                    if progress:
                        parsed.update(progress)

                    logger.debug(f"Wako Heist ✓ {self._format_wako_heist_summary(parsed)}")
                    return parsed
                
                # Phase 5: Parse - Extract ALL attribute values that could contain metadata
                # Check both text="" and content-desc="" attributes
                text_nodes = re.findall(r'text="([^"]+)"', current_xml)
                desc_nodes = re.findall(r'content-desc="([^"]+)"', current_xml)
                
                # Combine and deduplicate
                all_nodes = text_nodes + desc_nodes
                
                # Filter out empty, control chars, and system strings
                valid_texts = [t.strip() for t in all_nodes 
                              if t.strip() 
                              and not t.startswith('&#')
                              and len(t.strip()) > 0]
                
                # Debug: Log ALL non-empty attribute values found
                logger.info(
                    f"Wako Heist DEBUG: attempt={attempt+1} parsed_empty "
                    f"xml_len={xml_len} text={len(text_nodes)} desc={len(desc_nodes)} valid={len(valid_texts)} "
                    f"wake_ms={wake_ms} render_ms={render_ms} dump_ms={dump_ms} gate_ms={gate_ms} parse_ms={parse_ms} "
                    f"total_ms={int((time.monotonic() - attempt_started) * 1000)} samples={valid_texts[:15]}"
                )
                
                if not valid_texts:
                    logger.warning(f"Wako Heist: Attempt {attempt+1} - No text found, will retry")
                    continue
            
                # Strategy: Search for S:E or SxE patterns in all collected text nodes
                # Iterate BACKWARDS because the active player overlay is drawn last (bottom of tree),
                # preventing us from accidentally grabbing "Up Next" background episodes.
                for i in range(len(valid_texts) - 1, -1, -1):
                    text = valid_texts[i]
                    
                    # 1. Try Combined Format FIRST (e.g. "Preacher - S2:E7 (Dallas)")
                    combined_match = re.search(r'(.*?)\s*[-–]\s*(?:S|Season\s*)(\d+)\s*[:E]\s*(\d+)(?:\s*\((.*?)\))?', text, re.IGNORECASE)
                    if not combined_match:
                         # Try 1x01 format inline
                         combined_match = re.search(r'(.*?)\s*[-–]\s*(\d+)x(\d+)', text, re.IGNORECASE)
                    
                    if not combined_match:
                        # Try "Series Title S01E01" format
                        combined_match = re.search(r'(.*?)\s+(?:S|Season\s*)(\d+)\s*[:E]\s*(\d+)', text, re.IGNORECASE)

                    if combined_match:
                         title = combined_match.group(1).strip()
                         title = re.sub(r'\[.*?\]', '', title).strip()
                         if title:
                             result = {
                                 "title": title,
                                 "season": int(combined_match.group(2)),
                                 "episode": int(combined_match.group(3)),
                                 "ep_title": self._clean_wako_episode_title(combined_match.group(4)) if (combined_match.lastindex and combined_match.lastindex >= 4 and combined_match.group(4)) else None
                             }
                             logger.info(f"UI Heist SUCCESS (Combined): {result}")
                             return result

                    # 2. Match Isolated S2:E7 or S03E14
                    ep_match = re.search(r'S(\d+)[eE:](\d+)(?:\s*\((.*?)\))?', text, re.IGNORECASE)
                    if ep_match:
                        season = int(ep_match.group(1))
                        episode = int(ep_match.group(2))
                        ep_title = self._clean_wako_episode_title(ep_match.group(3)) if (ep_match.lastindex and ep_match.lastindex >= 3 and ep_match.group(3)) else None
                        
                        # Look-ahead for episode title if not in the same node
                        if not ep_title and i + 1 < len(valid_texts):
                            candidate = valid_texts[i+1]
                            if 2 < len(candidate) < 60 and not any(x in candidate for x in ["00:", "1:", "2:", "/", "http"]):
                                ep_title = self._clean_wako_episode_title(candidate)
                        
                        title = None
                        # Walk backwards to find the series title
                        for j in range(i - 1, -1, -1):
                            candidate = valid_texts[j]
                            if re.match(r'^\d+:\d+\s*/\s*\d+:\d+$', candidate):
                                continue
                            title = candidate
                            break
                        
                        if title:
                            result = {
                                "title": title,
                                "season": season,
                                "episode": episode,
                                "ep_title": ep_title
                            }
                            logger.info(f"UI Heist SUCCESS (Isolated Match): {result}")
                            return result
                    
                    # 3. Try isolated 1x01 format
                    if re.match(r'^\d+x\d+$', text, re.IGNORECASE):
                        episode_str = text
                        title = None
                        for j in range(i - 1, -1, -1):
                            candidate = valid_texts[j]
                            if re.match(r'^\d+:\d+\s*/\s*\d+:\d+$', candidate):
                                continue
                            title = candidate
                            break
                        
                        if title:
                            ep_match = re.search(r'(\d+)x(\d+)', episode_str, re.IGNORECASE)
                            if ep_match:
                                result = {
                                    "title": title,
                                    "season": int(ep_match.group(1)),
                                    "episode": int(ep_match.group(2))
                                }
                                # Look-ahead for episode title
                                if i + 1 < len(valid_texts):
                                    candidate = valid_texts[i+1]
                                    if 2 < len(candidate) < 60 and not any(x in candidate for x in ["00:", "1:", "2:", "/", "http"]):
                                        result["ep_title"] = self._clean_wako_episode_title(candidate)
                                        
                                logger.info(f"UI Heist SUCCESS (Isolated X): {result}")
                                return result
                
                # Check for "Now Playing" or similar headers that might contain the title
                for text in valid_texts:
                    if len(text) > 2 and not any(x in text for x in ["00:", "1:", "2:", "/", "http"]):
                        logger.info(f"Wako Heist: Potential title found: {text}")
                        # If we have no S/E, we treat it as a movie candidate
                
                # Fallback: If we found valid text but no episode pattern,
                # return first valid text as a movie title
                if valid_texts:
                    first = valid_texts[0]
                    if not re.match(r'^\d+:\d+', first):
                        logger.info(f"Wako Heist: No episode pattern, treating as movie: {first}")
                        return {"title": first, "season": None, "episode": None}
                
                logger.warning(f"Wako Heist: Attempt {attempt+1} - Could not extract metadata")
                    
            except Exception as e:
                elapsed_ms = int((time.monotonic() - attempt_started) * 1000)
                if attempt == 0:
                    logger.info(
                        f"Wako Heist DEBUG: attempt=1 exception after {elapsed_ms}ms "
                        f"wake_ms={wake_ms} render_ms={render_ms} dump_ms={dump_ms}: {e}; retrying"
                    )
                else:
                    logger.info(
                        f"Wako Heist DEBUG: final attempt exception after {elapsed_ms}ms "
                        f"wake_ms={wake_ms} render_ms={render_ms} dump_ms={dump_ms}: {e}"
                    )

        if needs_wake and was_playing:
            try:
                fallback_started = time.monotonic()
                logger.info("Wako Heist DEBUG: normal overlay wake failed; trying temporary pause fallback.")
                pause_started = time.monotonic()
                self.device.shell("input keyevent 127", timeout_s=4.0)
                pause_ms = int((time.monotonic() - pause_started) * 1000)
                time.sleep(1.3)
                dump_started = time.monotonic()
                current_xml = self.device.shell("uiautomator dump /sdcard/window_dump.xml > /dev/null && cat /sdcard/window_dump.xml", timeout_s=9.0)
                dump_ms = int((time.monotonic() - dump_started) * 1000)
                marker_ok = bool(current_xml and self._wako_xml_has_player_markers(current_xml))
                logger.info(
                    f"Wako Heist DEBUG: pause_fallback dump xml_len={len(current_xml or '')} "
                    f"marker_ok={marker_ok} pause_ms={pause_ms} dump_ms={dump_ms}"
                )
                if current_xml and marker_ok:
                    parse_started = time.monotonic()
                    progress = self._extract_wako_progress_from_xml(current_xml)
                    parsed = self._parse_wako_metadata(current_xml)
                    parse_ms = int((time.monotonic() - parse_started) * 1000)
                    if parsed:
                        if progress:
                            parsed.update(progress)
                        logger.info(
                            f"UI Heist SUCCESS (Pause Fallback): {parsed} "
                            f"parse_ms={parse_ms} total_ms={int((time.monotonic() - fallback_started) * 1000)}"
                        )
                        return parsed
                    text_nodes = re.findall(r'text="([^"]+)"', current_xml)
                    desc_nodes = re.findall(r'content-desc="([^"]+)"', current_xml)
                    valid = [self._clean_wako_text(node) for node in text_nodes + desc_nodes]
                    valid = [node for node in valid if node and not self._is_wako_noise(node)]
                    logger.info(f"Wako Heist DEBUG: pause fallback text={len(text_nodes)}, desc={len(desc_nodes)}, valid={len(valid)}, samples={valid[:15]}")
            except Exception as e:
                logger.info(f"Wako Heist DEBUG: pause fallback failed: {e}")
            finally:
                try:
                    self.device.shell("input keyevent 126", timeout_s=4.0)
                except Exception:
                    pass
        
        logger.info(f"Wako Heist DEBUG: all attempts exhausted total_ms={int((time.monotonic() - heist_started) * 1000)}")
        return {}

    def execute_wako_lite_heist(self) -> Dict:
        """Lite Heist V10: Context-Aware Wako Intelligence (Logo-only Title Support)"""
        if not self.device or not self.connected:
            return {}
            
        try:
            xml_data = self.device.shell("uiautomator dump /sdcard/lite_dump.xml > /dev/null && cat /sdcard/lite_dump.xml", timeout_s=9.0)
            
            if not xml_data: 
                return {}
            
            # 1. Player Shield (Immediate exit if playing)
            if self._wako_xml_has_player_markers(xml_data):
                return {"state": "playing_detected", "xml_data": xml_data}
            if self._wako_xml_is_hidden_player_shell(xml_data):
                return {"state": "hidden_player_shell", "xml_data": xml_data}
                
            # 2. Searching
            if "Search movies, shows, people..." in xml_data:
                return {"state": "searching"}
                
            # 3. Deep-Scan: Episode View
            # Pattern: Episode Title + SxxExx (e.g. S01E01 · Pilot)
            ep_meta_match = re.search(r'text="([sS]\d+[eE]\d+)\s*·\s*([^"]+)"', xml_data)
            if ep_meta_match:
                ep_code = ep_meta_match.group(1)
                text_nodes = re.findall(r'text="([^"]+)"', xml_data)
                try:
                    for i, t in enumerate(text_nodes):
                        if ep_code in t and i > 0:
                            # Strategy: text_nodes[i-1] is often the Episode Name.
                            # We search the rest of the nodes for the Series Name.
                            breadcrumb_match = re.search(r'text="([^"]+)\s*>\s*Season\s*\d+"', xml_data)
                            series_name = breadcrumb_match.group(1) if breadcrumb_match else (text_nodes[0] if text_nodes else "Unknown Show")
                            
                            episode_name = text_nodes[i-1]
                            return {
                                "state": "viewing_details", 
                                "title": series_name or "Unknown Show", 
                                "episode_title": episode_name, 
                                "episode_code": ep_code
                            }
                except: pass

            # 4. Deep-Scan: Show/Movie Page (Logo-only Title Support)
            is_show_page = any(x in xml_data for x in ["Cast & Crew", "Available on", "eps ·", "Similar"])
            if is_show_page:
                text_nodes = re.findall(r'text="([^"]+)"', xml_data)
                
                # Check for Breadcrumbs first (Series Name is often here)
                # Pattern: [Series Name] > [Season Name]
                crumb_match = re.search(r'text="([^"]+)\s*>\s*Season\s*\d+"', xml_data)
                series_hint = crumb_match.group(1) if crumb_match else None
                
                blacklist = ["Cast & Crew", "Comments", "Episodes", "Reviews", "Similar", "Trakt", "IMDb", "Available on", "Plan to Watch", "Add to List"]
                candidates = [t.strip() for t in text_nodes if len(t.strip()) > 3 and not any(b in t for b in blacklist)]
                
                if candidates:
                    title = candidates[0]
                    # If we found a series hint in the crumbs, that is our target
                    # We accept series_hint if found, fallback to candidate[0]
                    resolved_title = series_hint if series_hint else title
                    
                    if len(resolved_title) > 60: # Likely a description
                        return {"state": "viewing_details", "title": resolved_title[:50] + "...", "is_lookup_needed": True}
                    return {"state": "viewing_details", "title": resolved_title or "Unknown Content"}
            
            # 5. Catalog Browsing (Spatial 'Rectabox' Intelligence)
            if "app.wako" in xml_data:
                # Find the 'Rectabox' (Focused Node Bounds)
                focused_node = re.search(r'<node [^>]*focused="true"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml_data)
                if focused_node:
                    fx1, fy1, fx2, fy2 = map(int, focused_node.groups())
                    
                    # Find all text nodes inside these spatial bounds
                    potential_nodes = re.findall(r'text="([^"]+)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml_data)
                    found_titles = []
                    for text, x1, y1, x2, y2 in potential_nodes:
                        x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])
                        # If node is inside the focused Rectabox
                        if x1 >= fx1 and y1 >= fy1 and x2 <= fx2 and y2 <= fy2:
                            # Specialized Junk Filter for Catalog Posters (Ignore S/E)
                            blacklist = [r"Play", r"S\d+", r"E\d+", r"\d+min", r"Season", r"Episode"]
                            is_junk = any(re.search(b, text, re.I) for b in blacklist)
                            is_badge = text.startswith("+") or text.isdigit()
                            
                            if len(text.strip()) > 1 and not is_junk and not is_badge:
                                found_titles.append(text.strip())
                    
                    if found_titles:
                        # Grab the section header above/near the Rectabox
                        section_header = "Catalog"
                        for section in ["Continue Watching", "Trending", "Popular", "Plan to Watch", "Explore"]:
                            if section in xml_data:
                                section_header = section
                                break
                        return {"state": "browsing", "title": found_titles[0], "context": section_header}
                
                # Contextual Fallback (Sections)
                for section in ["Continue Watching", "Trending", "Popular", "Plan to Watch", "Explore"]:
                    if section in xml_data:
                        return {"state": "browsing", "context": section}
                
                return {"state": "browsing"}
                
            return {}
        except Exception as e:
            logger.debug(f"Wako Lite Heist unavailable: {e}")
            return {"state": "error"}

    def is_screensaver_active(self) -> bool:
        """Robust screensaver detection using multiple markers (Power, Dreams, and Focus)"""
        if not self.device or not self.connected:
            return False
            
        try:
            # 1. Check Power State (Ambient/Off)
            # 2. Check for active Dreams (Screensavers)
            # 3. Check Focus for known screensaver packages
            cmd = "dumpsys power | grep 'mScreenOn|Display Power' && dumpsys dream && dumpsys window | grep mCurrentFocus"
            raw = self.device.shell(cmd).lower()
            
            # Screensaver Packages
            SCREENSAVERS = [
                "dream", "ambient", "com.google.android.apps.tv.dream", 
                "com.google.android.backdrop", "arielview", "aerial"
            ]
            
            # logic: If Display Power is off, or Dreaming is true, or Focus is a screensaver
            is_dreaming = "dreaming: true" in raw or "mshowingdream=true" in raw
            is_screen_off = "mscreenon=false" in raw or "state=off" in raw or "state=doze" in raw
            focus_is_ss = any(ss in raw for ss in SCREENSAVERS)
            
            if is_dreaming or is_screen_off or focus_is_ss:
                return True
                
            return False
        except:
            return False
