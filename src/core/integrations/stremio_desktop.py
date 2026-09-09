import psutil
import requests
import time
import logging
import re
import os
import json
import socket
import base64
import struct
import urllib.parse
import subprocess
from typing import Optional, Dict, Any
try:
    import pygetwindow as gw
except Exception as exc:
    gw = None
    _PYGETWINDOW_IMPORT_ERROR = exc
else:
    _PYGETWINDOW_IMPORT_ERROR = None
try:
    from pywinauto import Application, Desktop
    from pywinauto.findwindows import ElementAmbiguousError, ElementNotFoundError
except Exception:
    Application = None
    Desktop = None

logger = logging.getLogger("StremioDesktop")

class StremioDesktopWatcher:
    """
    Monitors the local Stremio Desktop application (v5) for playback state and metadata.
    Uses UI Automation (UIA) to scrape the WebView2 shell and stats.json for tracking.
    """
    
    def __init__(self, config=None):
        self.config = config or {}
        self.last_title = ""
        self.last_stats = {}
        self.stats_url = "http://localhost:11470/stats.json"
        self._last_process_check = 0
        self._process_cache_ttl = 3  # seconds
        self._cached_running = False
        self._app_connection = None
        self._main_window = None
        self._last_uia_poll = 0
        self._uia_poll_interval = 2.0  # seconds
        self._is_enhanced_process = False
        configured_port = self._coerce_int(self.config.get("stremio_enhanced_devtools_port")) or 9229
        self._devtools_ports = [configured_port, 9222]
        self._devtools_ports = list(dict.fromkeys(self._devtools_ports))
        self._target_exe = None
        self._last_enhanced_relaunch_attempt = 0
        appdata = os.environ.get("APPDATA") or ""
        self._enhanced_log_paths = [
            os.path.join(appdata, "stremio-enhanced", "stremio-server.log"),
            os.path.join(appdata, "Stremio Enhanced", "stremio-server.log"),
        ]
        self._enhanced_cache_dirs = [
            os.path.join(appdata, "stremio-enhanced", "Cache", "Cache_Data"),
            os.path.join(appdata, "Stremio Enhanced", "Cache", "Cache_Data"),
        ]

    def _is_stremio_process_name(self, process_name: str) -> bool:
        name = (process_name or "").lower().strip()
        return name in {
            'stremio-shell-ng.exe',
            'stremio-shell-ng',
            'stremio.exe',
            'stremio',
            'stremio enhanced.exe',
            'stremio enhanced',
            'stremio-enhanced.exe',
            'stremio-enhanced',
            'stremio_enhanced.exe',
            'stremio_enhanced',
        }
        
    def is_running(self) -> bool:
        """Checks if Stremio shell is currently in the process list (cached)."""
        now = time.time()
        if now - self._last_process_check < self._process_cache_ttl:
            return self._cached_running
        self._last_process_check = now
        
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                name = (proc.info.get('name') or "").lower()
                if self._is_stremio_process_name(name):
                    self.is_stremio_running = True
                    self._cached_running = True
                    self._target_pid = proc.info['pid']
                    self._is_enhanced_process = "enhanced" in name
                    try:
                        self._target_exe = proc.exe()
                    except Exception:
                        self._target_exe = None
                    self._discover_devtools_ports(proc)
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        self.is_stremio_running = False
        self._cached_running = False
        self._app_connection = None
        self._main_window = None
        self._is_enhanced_process = False
        self._target_exe = None
        return False

    def _discover_devtools_ports(self, proc):
        try:
            cmdline = proc.cmdline()
        except Exception:
            return
        discovered = []
        for arg in cmdline or []:
            match = re.search(r'--remote-debugging-port=(\d+)', str(arg))
            if match:
                discovered.append(int(match.group(1)))
        for port in discovered:
            if port not in self._devtools_ports:
                self._devtools_ports.insert(0, port)

    def _enhanced_executable_candidates(self, env=None):
        env = env or os.environ
        candidates = []
        local_appdata = env.get("LOCALAPPDATA") or ""
        program_files = env.get("PROGRAMFILES") or ""
        program_files_x86 = env.get("PROGRAMFILES(X86)") or ""
        roots = [
            local_appdata,
            program_files,
            program_files_x86,
        ]
        relative_paths = [
            os.path.join("Programs", "stremio-enhanced", "Stremio Enhanced.exe"),
            os.path.join("Programs", "Stremio Enhanced", "Stremio Enhanced.exe"),
            os.path.join("stremio-enhanced", "Stremio Enhanced.exe"),
            os.path.join("Stremio Enhanced", "Stremio Enhanced.exe"),
        ]
        for root in roots:
            if not root:
                continue
            for relative_path in relative_paths:
                candidate = os.path.normpath(os.path.join(root, relative_path))
                if candidate not in candidates:
                    candidates.append(candidate)
        return candidates

    def _find_enhanced_executable(self):
        if self._target_exe and os.path.exists(self._target_exe):
            return self._target_exe
        for proc in self._enhanced_processes():
            try:
                exe_path = proc.exe()
                if exe_path and os.path.exists(exe_path):
                    return exe_path
            except Exception:
                continue
        for candidate in self._enhanced_executable_candidates():
            if os.path.exists(candidate):
                return candidate
        return None

    def _enhanced_devtools_available(self):
        return any(self._devtools_pages(port) for port in self._devtools_ports)

    def _enhanced_processes(self):
        processes = []
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                name = proc.info.get('name') or ""
                if self._is_stremio_process_name(name) and "enhanced" in name.lower():
                    processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return processes

    def _maybe_relaunch_enhanced_with_devtools(self):
        if not self.config.get("stremio_enhanced_auto_devtools", True):
            return False
        if not self._is_enhanced_process:
            return False
        if self._enhanced_devtools_available():
            return False

        now = time.time()
        cooldown = float(self.config.get("stremio_enhanced_relaunch_cooldown", 90) or 90)
        if now - self._last_enhanced_relaunch_attempt < cooldown:
            return False
        self._last_enhanced_relaunch_attempt = now

        exe_path = self._find_enhanced_executable()
        if not exe_path or not os.path.exists(exe_path):
            logger.info("Stremio Enhanced exact telemetry unavailable: could not locate executable for managed relaunch.")
            return False

        processes = self._enhanced_processes()
        for proc in processes:
            try:
                proc.terminate()
            except Exception:
                pass
        try:
            gone, alive = psutil.wait_procs(processes, timeout=5)
            for proc in alive:
                try:
                    proc.kill()
                except Exception:
                    pass
        except Exception:
            pass

        port = self._devtools_ports[0]
        command = [
            exe_path,
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
        ]
        try:
            subprocess.Popen(command, cwd=os.path.dirname(exe_path) or None)
            self._last_process_check = 0
            self._cached_running = False
            self._app_connection = None
            self._main_window = None
            logger.info(
                f"Stremio Enhanced exact telemetry: relaunched with local DevTools on 127.0.0.1:{port}."
            )
            return True
        except Exception as exc:
            logger.warning(f"Stremio Enhanced exact telemetry relaunch failed: {exc}")
            return False

    def _get_uia_state(self) -> Dict[str, Any]:
        """Scrapes playback info from the Stremio UI using UIA."""
        state = {"active": False}
        if not Application:
            return state

        now = time.time()
        if now - self._last_uia_poll < self._uia_poll_interval:
            # Return last known state but update time if playing?
            # Actually, the main loop handles interpolation if we set duration/position correctly.
            # For now, just return a cached state or empty to wait for next poll.
            return getattr(self, '_last_cached_state', state)
        
        self._last_uia_poll = now
        try:
            # Reconnect if process changed or connection lost
            if not self._app_connection:
                self._app_connection = Application(backend='uia').connect(process=self._target_pid)
                self._main_window = self._app_connection.top_window()
            
            # Fast scan for text elements
            # We look for:
            # 1. Content Title (e.g. "Ghosts - Viking Wedding (5x2)")
            # 2. Timestamps (e.g. "00:11:15", "00:21:11")
            # 3. Play/Pause button state
            
            descendants = self._main_window.descendants()
            
            title = ""
            current_time = 0
            duration = 0
            is_playing = False
            
            times = []
            
            for e in descendants:
                try:
                    text = e.window_text().strip()
                    if not text:
                        continue
                    
                    # Pattern 1: Title with Season/Episode in parens
                    if '(' in text and ')' in text and ('x' in text.lower() or 's' in text.lower()):
                        title = text
                    
                    # Pattern 2: Timestamps
                    if re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', text):
                        times.append(text)
                    
                    # Pattern 3: Play/Pause button
                    if text == "Pause":
                        is_playing = True
                    elif text == "Play":
                        is_playing = False
                        
                except: continue

            if title:
                state["active"] = True
                state["window_title"] = title
                # Parse title
                metadata = self.parse_title(title)
                state.update(metadata)
                
                # Parse times
                if len(times) >= 2:
                    state["position"] = self._parse_time_str(times[0])
                    state["duration"] = self._parse_time_str(times[1])
                elif len(times) == 1:
                    state["duration"] = self._parse_time_str(times[0])
                
                state["is_playing"] = is_playing
                
            self._last_cached_state = state
            return state
        except Exception as e:
            logger.debug(f"UIA Scrape Error: {e}")
            self._app_connection = None # Force reconnect next time
            return state

    def _parse_time_str(self, time_str: str) -> int:
        """Converts HH:MM:SS or MM:SS to milliseconds."""
        parts = list(map(int, time_str.split(':')))
        if len(parts) == 3: # HH:MM:SS
            return (parts[0] * 3600 + parts[1] * 60 + parts[2]) * 1000
        elif len(parts) == 2: # MM:SS
            return (parts[0] * 60 + parts[1]) * 1000
        return 0

    def _coerce_ms(self, value) -> int:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0
        if number <= 0:
            return 0
        if number < 10000:
            number *= 1000
        return int(number)

    def _coerce_int(self, value):
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    def parse_media_hint(self, text: str) -> Dict[str, Any]:
        """Parses filenames, stream URLs, or route fragments into metadata hints."""
        value = urllib.parse.unquote(str(text or ""))
        value = value.replace("\\", "/").split("/")[-1]
        value = re.sub(r'\.(mkv|mp4|avi|mov|m4v|webm)(?:\?.*)?$', '', value, flags=re.I)
        value = re.sub(r'\b(2160p|1080p|720p|480p|web[-_. ]?dl|webrip|bluray|brrip|hdr|dv|x264|x265|h264|h265|hevc|aac|ddp?\d?\.?\d?|atmos)\b.*$', '', value, flags=re.I)
        value = re.sub(r'[._]+', ' ', value).strip(" -")

        se_match = re.search(r'(.+?)\s+S(\d{1,2})E(\d{1,3})(?:\s+(.+))?$', value, re.I)
        if se_match:
            title = re.sub(r'\s+(US|UK)$', '', se_match.group(1).strip(" -"), flags=re.I)
            ep_title = (se_match.group(4) or "").strip(" -")
            ep_title = re.sub(r'\s+', ' ', ep_title)
            return {
                "title": title,
                "season": int(se_match.group(2)),
                "episode": int(se_match.group(3)),
                "episode_title": ep_title,
                "is_movie": False,
            }

        x_match = re.search(r'(.+?)\s+(\d{1,2})x(\d{1,3})(?:\s+(.+))?$', value, re.I)
        if x_match:
            return {
                "title": x_match.group(1).strip(" -"),
                "season": int(x_match.group(2)),
                "episode": int(x_match.group(3)),
                "episode_title": (x_match.group(4) or "").strip(" -"),
                "is_movie": False,
            }

        return self.parse_title(value)

    def _extract_imdb_id(self, text: str):
        match = re.search(r'\btt\d{6,10}\b', str(text or ""))
        return match.group(0) if match else None

    def _enhanced_base_state(self, metadata, source, telemetry_mode, **extra):
        is_playing = extra.pop("is_playing", None)
        if is_playing is None:
            is_playing = True
        state = {
            "active": True,
            "source": source,
            "telemetry_mode": telemetry_mode,
            "app": "Stremio Enhanced",
            "focus": "Stremio Enhanced",
            "position": extra.pop("position", None),
            "duration": extra.pop("duration", None),
            "is_playing": bool(is_playing),
            "state": "playing" if is_playing else "paused",
        }
        state.update(metadata or {})
        state.update(extra)
        return state

    def _read_tail(self, path, max_bytes=65536):
        try:
            with open(path, "rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - max_bytes), os.SEEK_SET)
                return handle.read().decode("utf-8", errors="ignore")
        except OSError:
            return ""

    def _get_enhanced_log_state(self) -> Dict[str, Any]:
        for path in self._enhanced_log_paths:
            tail = self._read_tail(path)
            if not tail:
                continue
            lines = [line.strip() for line in tail.splitlines() if line.strip()]
            for line in reversed(lines):
                if not re.search(r'(stream|mkv|mp4|avi|webm|tt\d{6,10}|S\d{1,2}E\d{1,3}|\d+x\d+)', line, re.I):
                    continue
                hint = None
                url_match = re.search(r'https?://\S+', line)
                if url_match:
                    parsed_url = urllib.parse.urlparse(url_match.group(0))
                    hint = os.path.basename(parsed_url.path)
                if not hint:
                    file_match = re.search(r'([A-Za-z0-9][^\s"]{2,}\.(?:mkv|mp4|avi|webm))', line, re.I)
                    hint = file_match.group(1) if file_match else line
                metadata = self.parse_media_hint(hint)
                if metadata.get("title"):
                    return self._enhanced_base_state(
                        metadata,
                        "stremio_enhanced_logs",
                        "logs",
                        imdb_id=self._extract_imdb_id(line),
                        stream_url=url_match.group(0) if url_match else None,
                        filename=hint,
                        confidence={"identity": 0.65, "playback": 0.25, "timestamp": 0.0},
                    )
        return {"active": False}

    def _json_from_cache_text(self, text):
        if not text:
            return None
        start_candidates = [pos for pos in (text.find('{"streams"'), text.find('{"metas"')) if pos >= 0]
        if not start_candidates:
            return None
        start = min(start_candidates)
        decoder = json.JSONDecoder()
        try:
            payload, _ = decoder.raw_decode(text[start:])
            return payload
        except json.JSONDecodeError:
            return None

    def _candidate_from_stream(self, stream):
        if not isinstance(stream, dict):
            return None
        hints = stream.get("behaviorHints") if isinstance(stream.get("behaviorHints"), dict) else {}
        filename = hints.get("filename") or stream.get("filename") or ""
        stream_url = stream.get("url") or stream.get("externalUrl") or ""
        description = stream.get("description") or ""
        hint = filename or stream_url or description
        metadata = self.parse_media_hint(hint)
        if not metadata.get("title"):
            return None
        score = 1
        if metadata.get("season") is not None and metadata.get("episode") is not None:
            score += 5
        if metadata.get("episode_title"):
            score += 3
        if filename:
            score += 2
        if stream_url:
            score += 1
        return {
            "score": score,
            "metadata": metadata,
            "filename": filename or None,
            "stream_url": stream_url or None,
        }

    def _candidate_from_meta(self, meta):
        if not isinstance(meta, dict):
            return None
        name = meta.get("name") or meta.get("title") or ""
        metadata = self.parse_media_hint(name)
        if not metadata.get("title"):
            return None
        return {
            "score": 2,
            "metadata": metadata,
            "filename": name,
            "stream_url": None,
        }

    def _get_enhanced_cache_state(self) -> Dict[str, Any]:
        files = []
        for cache_dir in self._enhanced_cache_dirs:
            try:
                for name in os.listdir(cache_dir):
                    path = os.path.join(cache_dir, name)
                    if os.path.isfile(path):
                        files.append((os.path.getmtime(path), path))
            except OSError:
                continue

        best = None
        for _, path in sorted(files, reverse=True)[:80]:
            tail = self._read_tail(path, max_bytes=2 * 1024 * 1024)
            payload = self._json_from_cache_text(tail)
            if not isinstance(payload, dict):
                continue
            candidates = []
            for stream in payload.get("streams") or []:
                candidate = self._candidate_from_stream(stream)
                if candidate:
                    candidates.append(candidate)
            for meta in payload.get("metas") or []:
                candidate = self._candidate_from_meta(meta)
                if candidate:
                    candidates.append(candidate)
            for candidate in candidates:
                if not best or candidate["score"] > best["score"]:
                    best = candidate
            if best and best["score"] >= 8:
                break

        if not best:
            return {"active": False}
        return self._enhanced_base_state(
            best["metadata"],
            "stremio_enhanced_cache",
            "cache",
            imdb_id=self._extract_imdb_id((best.get("stream_url") or "") + " " + (best.get("filename") or "")),
            stream_url=best.get("stream_url"),
            filename=best.get("filename"),
            confidence={"identity": 0.5, "playback": 0.2, "timestamp": 0.0},
        )

    def _devtools_pages(self, port):
        try:
            response = requests.get(f"http://127.0.0.1:{port}/json", timeout=0.35)
            if response.status_code == 200:
                return response.json()
        except Exception:
            return []
        return []

    def _ws_recv_frame(self, sock):
        header = sock.recv(2)
        if len(header) < 2:
            return ""
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", sock.recv(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", sock.recv(8))[0]
        mask = header[1] & 0x80
        masking_key = sock.recv(4) if mask else b""
        payload = b""
        while len(payload) < length:
            payload += sock.recv(length - len(payload))
        if mask:
            payload = bytes(byte ^ masking_key[index % 4] for index, byte in enumerate(payload))
        return payload.decode("utf-8", errors="ignore")

    def _ws_send_text(self, sock, text):
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        if len(payload) < 126:
            header.append(0x80 | len(payload))
        elif len(payload) < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack(">H", len(payload)))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack(">Q", len(payload)))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        sock.sendall(bytes(header) + masked)

    def _cdp_evaluate(self, websocket_url, expression):
        parsed = urllib.parse.urlparse(websocket_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        with socket.create_connection((host, port), timeout=0.75) as sock:
            request = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            )
            sock.sendall(request.encode("ascii"))
            response = sock.recv(4096)
            if b"101" not in response.split(b"\r\n", 1)[0]:
                return None
            message = json.dumps({
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {"expression": expression, "returnByValue": True, "awaitPromise": False},
            })
            self._ws_send_text(sock, message)
            deadline = time.time() + 1.5
            while time.time() < deadline:
                frame = self._ws_recv_frame(sock)
                if not frame:
                    continue
                data = json.loads(frame)
                if data.get("id") == 1:
                    return data.get("result", {}).get("result", {}).get("value")
        return None

    def _get_enhanced_devtools_state(self) -> Dict[str, Any]:
        expression = """(() => {
          const video = document.querySelector('video');
          return {
            href: location.href,
            title: document.title,
            bodyText: document.body ? document.body.innerText : '',
            currentTime: video && Number.isFinite(video.currentTime) ? video.currentTime : null,
            duration: video && Number.isFinite(video.duration) ? video.duration : null,
            paused: video ? video.paused : null,
            ended: video ? video.ended : null,
            playbackRate: video ? video.playbackRate : null,
            videoSrc: video ? (video.currentSrc || video.src || null) : null
          };
        })()"""
        for port in self._devtools_ports:
            for page in self._devtools_pages(port):
                page_url = str(page.get("url") or "")
                page_title = str(page.get("title") or "")
                ws_url = page.get("webSocketDebuggerUrl")
                if not ws_url or ("strem" not in page_url.lower() and "strem" not in page_title.lower()):
                    continue
                result = self._cdp_evaluate(ws_url, expression)
                if not isinstance(result, dict):
                    continue
                has_video_state = (
                    result.get("currentTime") is not None
                    or result.get("duration") is not None
                    or result.get("paused") is not None
                    or bool(result.get("videoSrc"))
                )
                if not has_video_state:
                    continue
                title_hint = result.get("title") or page_title
                body_text = result.get("bodyText") or ""
                overlay_match = re.search(r'^(.+?\s[-–—]\s.+?\s\(\d+x\d+\))$', body_text, re.M)
                if overlay_match:
                    title_hint = overlay_match.group(1)
                metadata = self.parse_title(title_hint)
                if not metadata.get("title") and result.get("videoSrc"):
                    metadata = self.parse_media_hint(result.get("videoSrc"))
                paused = result.get("paused")
                is_playing = None if paused is None else not bool(paused)
                return self._enhanced_base_state(
                    metadata,
                    "stremio_enhanced_devtools",
                    "devtools",
                    window_title=title_hint,
                    position=self._coerce_ms(result.get("currentTime")),
                    duration=self._coerce_ms(result.get("duration")),
                    is_playing=is_playing,
                    playbackRate=result.get("playbackRate"),
                    stream_url=result.get("videoSrc"),
                    page_url=result.get("href") or page_url,
                    imdb_id=self._extract_imdb_id((result.get("href") or "") + " " + (result.get("videoSrc") or "")),
                    confidence={"identity": 0.95, "playback": 0.95, "timestamp": 0.95},
                )
        return {"active": False}

    def _get_enhanced_external_state(self) -> Dict[str, Any]:
        state = self._get_enhanced_devtools_state()
        if state.get("active"):
            return state
        if self._maybe_relaunch_enhanced_with_devtools():
            time.sleep(2)
            state = self._get_enhanced_devtools_state()
            if state.get("active"):
                return state
        state = self._get_enhanced_log_state()
        if state.get("active"):
            return state
        return self._get_enhanced_cache_state()

    def get_playback_stats(self) -> Dict[str, Any]:
        """Fetches playback data from the local streaming server (fallback)."""
        try:
            response = requests.get(self.stats_url, timeout=0.5)
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception:
            return {}

    def parse_title(self, title: str) -> Dict[str, Any]:
        """Parses the Stremio content title into structured metadata."""
        result = {
            "title": "",
            "season": None,
            "episode": None,
            "episode_title": "",
            "is_movie": True
        }
        
        # Clean title (strip trailing ' - Stremio' if present)
        clean = re.sub(r'\s*[-–—]\s*Stremio\s*$', '', title).strip()
        
        # Pattern: "Show Name - Episode Title (5x2)"
        paren_match = re.search(r'^(.+?)\s*[-–—]\s*(.+?)\s*\((\d+)x(\d+)\)\s*$', clean)
        if paren_match:
            result["title"] = paren_match.group(1).strip()
            result["episode_title"] = paren_match.group(2).strip()
            result["season"] = int(paren_match.group(3))
            result["episode"] = int(paren_match.group(4))
            result["is_movie"] = False
            return result

        # Pattern: "Show Name (5x2)"
        paren_match_simple = re.search(r'^(.+?)\s*\((\d+)x(\d+)\)\s*$', clean)
        if paren_match_simple:
            result["title"] = paren_match_simple.group(1).strip()
            result["season"] = int(paren_match_simple.group(2))
            result["episode"] = int(paren_match_simple.group(3))
            result["is_movie"] = False
            return result

        # Pattern: "Show Name - S01E01"
        se_match = re.search(r'^(.+?)\s*[-–—]\s*S(\d+)E(\d+)', clean, re.IGNORECASE)
        if se_match:
            result["title"] = se_match.group(1).strip()
            result["season"] = int(se_match.group(2))
            result["episode"] = int(se_match.group(3))
            result["is_movie"] = False
            return result

        result["title"] = clean
        result["is_movie"] = True
        return result

    def get_state(self) -> Dict[str, Any]:
        """Aggregates data from all sources to return the current playback state."""
        if not self.is_running():
            return {"active": False}

        if self._is_enhanced_process:
            enhanced_state = self._get_enhanced_external_state()
            if enhanced_state.get("active"):
                return enhanced_state
            
        # Try UIA first as it's the most reliable for v5
        state = self._get_uia_state()
        
        # Fallback/Supplemental info from stats.json
        stats = self.get_playback_stats()
        if stats:
            state["raw_stats"] = stats
            if not state.get("active") and "totalLength" in stats:
                state["active"] = True # Fallback activation if stats populated
                state["duration"] = stats["totalLength"]
                state["position"] = stats.get("p", 0)
        
        if state.get("active"):
            state["source"] = "stremio_desktop"
            # Map state to 'playing'/'paused' for the main loop
            state["state"] = "playing" if state.get("is_playing", True) else "paused"
            
        return state
