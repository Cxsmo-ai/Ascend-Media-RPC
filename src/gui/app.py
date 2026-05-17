import threading
import time
import sys
import os
import json
import logging
import re
import webbrowser
import urllib.parse
import hashlib
import asyncio
import subprocess
from io import BytesIO

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False

try:
    import webview
    HAS_WEBVIEW = True
except ImportError as e:
    webview = None
    HAS_WEBVIEW = False
    print(f"WARNING: 'pywebview' failed to import. Reason: {e}")
    print("Falling back to system browser.")

from src.core.config import load_config, save_config, get_config_path
from src.core.logger import log_table, log_once, IS_WINDOWS
from src.core.controller import StremioController
from src.core.discovery import ADBDiscovery
from src.core.tmdb import TMDBClient
from src.core.title_resolver import MediaTitleResolver
from src.core.top_posters import TopPostersClient
from src.core.erdb import ERDBClient
from src.core.nuvio import NuvioCoversClient
from src.core.skip_manager import SkipManager
from src.core.aniskip import AniskipClient
from src.core.mal_mapper import MalMapper
from src.core.trakt import TraktClient
from src.rpc.discord_client import DiscordRPC
from pypresence.types import ActivityType
from src.core.history import SkipHistory
from src.core.stats import StatsManager
from src.core.analytics import AnalyticsDB
from src.web.server import run_server
from src.core.audit_log import AuditLog
from src.core.rpc_history import RPCHistory
from src.core.config_watcher import ConfigWatcher
from src.core.plugin_system import PluginRegistry
from src.core.api_validator import APIKeyValidator
try:
    from src.core.integrations.stremio_desktop import StremioDesktopWatcher
except Exception:
    StremioDesktopWatcher = None
try:
    import requests
    from PIL import Image, ImageOps, ImageSequence
except Exception:
    requests = None
    Image = None
    ImageOps = None
    ImageSequence = None

# BRIGHT LOGO FALLBACKS (Guaranteed external URLs)
STREMIO_LOGO_URL = "https://app.strem.io/images/stremio.png"
WAKO_LOGO_URL = "https://wako.app/assets/img/logo.png"

# SINGULARITY LOGGING
logger = logging.getLogger("stremio-rpc")


def _fileditch_hosted_url(result) -> str | None:
    """Accept current FileDitch API responses and older mirrored shapes."""
    if not isinstance(result, dict) or not result.get("success"):
        return None

    hosted = result.get("url")
    if isinstance(hosted, str) and hosted.startswith("http"):
        return hosted

    files = result.get("files")
    if isinstance(files, list) and files:
        first = files[0] if isinstance(files[0], dict) else {}
        for key in ("url", "downloadUrl", "download_url"):
            hosted = first.get(key)
            if isinstance(hosted, str) and hosted.startswith("http"):
                return hosted

    return None


def _discord_direct_image_url(url: str) -> bool:
    if not requests or not url:
        return False

    try:
        resp = requests.get(
            url,
            timeout=(5, 12),
            stream=True,
            allow_redirects=True,
            headers={
                "User-Agent": "Discordbot/2.0",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
        )
        content_type = str(resp.headers.get("Content-Type") or "").lower()
        return resp.status_code == 200 and content_type.startswith("image/")
    except Exception as exc:
        logger.debug(f"Discord image URL probe failed: {exc}")
        return False

class AscendFormatter(logging.Formatter):
    """Custom formatter for beautiful, organized console output"""
    COLORS = {
        'DEBUG': Fore.LIGHTBLACK_EX if HAS_COLOR else '',
        'INFO': Fore.CYAN if HAS_COLOR else '',
        'WARNING': Fore.YELLOW if HAS_COLOR else '',
        'ERROR': Fore.RED if HAS_COLOR else '',
        'CRITICAL': Fore.RED + Style.BRIGHT if HAS_COLOR else '',
    }
    
    ICONS = {
        'ADB': '📡',
        'RPC': '🎮',
        'WAKO': '🎥',
        'SKIP': '⏩',
        'ART': '🖼️',
        'WEB': '🌐',
        'APP': '✨'
    }

    def format(self, record):
        level_color = self.COLORS.get(record.levelname, '')
        reset = Style.RESET_ALL if HAS_COLOR else ''
        
        msg = record.getMessage()
        icon = self.ICONS['APP']
        if 'ADB' in msg.upper() or 'CONNECTING TO' in msg.upper(): icon = self.ICONS['ADB']
        elif 'RPC' in msg.upper(): icon = self.ICONS['RPC']
        elif 'WAKO' in msg.upper() or 'HEIST' in msg.upper(): icon = self.ICONS['WAKO']
        elif 'SKIP' in msg.upper(): icon = self.ICONS['SKIP']
        elif 'POSTERS' in msg.upper() or 'ERDB' in msg.upper() or 'ARTWORK' in msg.upper(): icon = self.ICONS['ART']
        elif 'FLASK' in msg.upper() or 'SERVING' in msg.upper(): icon = self.ICONS['WEB']
        
        clean_msg = msg
        if record.name == 'stremio-rpc':
            clean_msg = clean_msg.replace('Wako Heist: ', '   ├─ ')
            if 'SUCCESS' in clean_msg.upper():
                clean_msg = clean_msg.replace('   ├─ ', '   └─ ')
                level_color = Fore.GREEN if HAS_COLOR else ''

        timestamp = self.formatTime(record, "%H:%M:%S")
        return f"{Fore.LIGHTBLACK_EX if HAS_COLOR else ''}[{timestamp}]{reset} {level_color}{icon} {clean_msg}{reset}"

class MemoryLogHandler(logging.Handler):
    def __init__(self, capacity=50):
        super().__init__()
        self.capacity = capacity
        self.buffer = []
        
    def emit(self, record):
        try:
            msg = self.format(record)
            if "Encoding detection:" in msg and "is most likely the one" in msg:
                return
            self.buffer.append(msg)
            if len(self.buffer) > self.capacity:
                self.buffer.pop(0)
        except Exception:
            self.handleError(record)

class App:
    def __init__(self):
        # --- INITIALIZE STATE VARS FIRST ---
        self._adb_connecting = False
        self.running = True
        self.stop_counter = 0
        self.is_screensaver = False
        self._next_adb_reconnect_at = 0
        self._adb_reconnect_delay = 5
        self._adb_offline_notified = False
        
        # --- CONFIG & STATE ---
        self.config = load_config()
        self.shared_state = {
            "connected": False,
            "device": "Disconnected",
            "title": "Ready to Play",
            "subtitle": "Waiting for device...",
            "progress": 0,
            "is_playing": False,
            "duration": 0,
            "position": 0,
            "image_url": None,
            "image_url_fallback": None,
            "dashboard_small_icon_url": None,
            "meta_imdb": None,
            "meta_season": None,
            "meta_episode": None,
            "skip_status_msg": "System Ready",
            "skip_status_color": "gray",
            "auto_skip": False,
            "next_skip": None,
            "app": None,
            "badge_size": "medium",
            "badge_position": "bottom-left",
            "blur": "false",
            "focus": "",
            "logs": [],
            "history": [],
            "api_status": {"discord": False, "trakt": False, "adb": False, "metadata": False}
        }
        
        self.history = SkipHistory()
        self.stats = StatsManager(self.config)
        
        self.log_handler = MemoryLogHandler()
        dashboard_formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S')
        self.log_handler.setFormatter(dashboard_formatter)
        logging.getLogger().addHandler(self.log_handler)
        self.shared_state["logs"] = self.log_handler.buffer
        
        # The advanced logger is already set up via import of src.core.logger
        self.print_banner()
        
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        logging.getLogger('asyncio').setLevel(logging.ERROR)
        logging.getLogger('adb.protocol').setLevel(logging.WARNING)
        
        
        # Initialize Backend Components
        self.controller = StremioController(self.config["adb_host"], self.config["adb_port"])
        self.controller.playback_logcat_enabled = bool(self.config.get("playback_logcat_enabled", False))
        self.tmdb_key = self.config.get("tmdb_api_key", "")
        self.tmdb = TMDBClient(self.tmdb_key)
        self.title_resolver = MediaTitleResolver()
        self.top_posters = TopPostersClient(self.config)
        self.erdb = ERDBClient(self.config)
        self.nuvio_covers = NuvioCoversClient(
            self.config.get("nuvio_covers_base_url", "https://nuvioapp.space"),
            self.config.get("nuvio_covers_token", ""),
            self.config.get("nuvio_covers_email", ""),
            self.config.get("nuvio_covers_password", ""),
            on_token_refresh=self._save_nuvio_token,
        )
        self.rpc = DiscordRPC(self.config.get("discord_client_id", "1451010126495617106"))
        self.rpc.update_all_pipes = bool(self.config.get("rpc_update_all_discord_pipes", True))
        self.stremio_desktop = StremioDesktopWatcher(self.config) if StremioDesktopWatcher else None
        
        self.mal_mapper = MalMapper(client_id=self.config.get("mal_client_id", ""))
        self.skip_manager = SkipManager(self.config)
        self.skip_manager.enabled = (self.config.get("skip_mode", "off") != "off")
        # Persist auto-refreshed SkipIt JWTs back to config so they survive restarts.
        def _on_skipit_token_refresh(new_token, status):
            try:
                self.config["skipit_token"] = new_token
                if status.get("session_id"):
                    self.config["skipit_session_id"] = status["session_id"]
                if status.get("frontend_api"):
                    self.config["skipit_frontend_api"] = status["frontend_api"]
                self.save_settings()
            except Exception as exc:
                logger.warning(f"SkipIt token persist failed: {exc}")
        self.skip_manager._skipit_on_token_refresh = _on_skipit_token_refresh
        
        self.trakt = TraktClient(
            client_id=self.config.get("trakt_client_id"),
            client_secret=self.config.get("trakt_client_secret"),
            access_token=self.config.get("trakt_access_token"),
            refresh_token=self.config.get("trakt_refresh_token"),
            on_token_refresh=self._save_trakt_tokens,
        )
        
        self.analytics = AnalyticsDB()

        # --- New Feature Modules ---
        self._start_time = time.time()
        self.audit_log = AuditLog()
        self.rpc_history = RPCHistory(
            limit=self.config.get("rpc_history_limit", 100),
        )
        self.plugin_registry = PluginRegistry()
        self._privacy_mode = self.config.get("privacy_mode", False)
        self._rpc_cycling_index = 0
        self._last_cycling_time = 0

        # Config hot-reload watcher
        self._config_watcher = None
        if self.config.get("config_hot_reload", False):
            self._config_watcher = ConfigWatcher(on_change=self._on_config_file_changed)
            self._config_watcher.start()

        # mDNS discovery
        self.discovery = ADBDiscovery(
            port=int(self.config.get("adb_port", 5555)),
            use_mdns=self.config.get("mdns_discovery_enabled", True),
        )
        self.discovery.start_mdns()

        # Initialize API integrations lazily
        self._integrations = {}
        self._last_integration_scrobble = 0
        self._current_session_id = -1
        self._current_session_key = None
        self.last_full_details = None
        self.last_image_url = None
        self.last_content_image_url = None
        self.last_season_image_url = None
        self.last_episode_image_url = None
        self.last_top_posters_show_url = None
        self.last_top_posters_season_url = None
        self.last_top_posters_episode_url = None
        self.last_erdb_show_url = None
        self.last_erdb_backdrop_url = None
        self.last_erdb_episode_url = None
        self.erdb_artwork_cache = {}
        self.last_artwork_key = None
        self.last_artwork_fallback_notice_key = None
        self.last_rpc_meta_key = None
        self.last_episode_title = None
        self.last_episode_details = None
        self.last_network_image_url = None
        self.last_network_name = None
        self.last_network_gif_url = None
        self.last_network_gif_name = None
        self.last_tmdb_url = None
        self.last_trailer_url = None
        self.last_imdb_id = None
        self.last_meta = None
        self.last_item = None
        self.rpc_timeline_key = None
        self.rpc_timeline_start_timestamp = None
        self.rpc_timeline_end_timestamp = None
        self.wako_cached_title = None
        self.wako_cached_season = None
        self.wako_cached_episode = None
        self.wako_cached_ep_title = None
        self.wako_cached_position = None
        self.wako_cached_duration = None
        self.wako_progress_anchor_time = None
        self.last_wako_missing_duration_log_key = None
        self.last_wako_missing_duration_log_time = 0
        self.last_heist_position = 0
        self.last_nudge_time = 0
        self.last_trakt_sync = 0
        self.rpc_artwork_upload_cache = {}
        self.rpc_artwork_upload_manifest_loaded = False
        self.running = True
        self.device_name = "Scanning..."
        self._adb_connecting = False
        
        
        # Start Threads
        self.connect_adb()
        threading.Thread(target=self._monitor_loop, daemon=True).start()
        threading.Thread(target=self._start_web_server, daemon=True).start()
        threading.Thread(target=self._init_integrations, daemon=True).start()
        
        self.start_gui()
    def print_banner(self):
        if not HAS_COLOR:
            print("=== ASCEND MEDIA RPC ===")
            return
            
        # Use formatted raw string for colors and backslashes
        banner = fr"""
{Fore.CYAN}{Style.BRIGHT}     /\                          | |  \/  |        | (_)     |  __ \|  __ \ / ____|
    /  \   ___  ___ ___ _ __   __| | \  / | ___  __| |_  __ _| |__) | |__) | |    
   / /\ \ / __|/ __/ _ \ '_ \ / _` | |\/| |/ _ \/ _` | |/ _` |  _  /|  ___/| |    
  / ____ \\__ \ (_|  __/ | | | (_| | |  | |  __/ (_| | | (_| | | \ \| |    | |____
 /_/    \_\___/\___/\___/_/ |_|\__,_|_|  |_|\___|\__,_|_|\__,_|_|  \_\_|     \_____|
                                                                           
{Fore.LIGHTBLACK_EX}   >> The Ultimate Discord Presence Engine | Build: Optimized Release{Style.RESET_ALL}
        """
        print(banner)
        # Print build identity so two builds running side-by-side are easy
        # to tell apart (helps when "different builds use the same dashboard").
        try:
            print(
                f"{Fore.LIGHTBLACK_EX}   Build path : {os.getcwd()}{Style.RESET_ALL}"
            )
            print(
                f"{Fore.LIGHTBLACK_EX}   Python     : {sys.executable}{Style.RESET_ALL}"
            )
            print(
                f"{Fore.LIGHTBLACK_EX}   PID        : {os.getpid()}{Style.RESET_ALL}"
            )
        except Exception:
            pass

    def connect_adb(self):
        if self.shared_state.get("connected"):
            return
        if self._adb_connecting:
            logger.info("ADB connect already in progress; skipping duplicate request.")
            return
        def _connect():
            self._adb_connecting = True
            try:
                logger.info(f"Connecting to ADB at {self.controller.host}:{self.controller.port}...")
                res = self.controller.connect()
                if res:
                    # Resolve proper device name instead of just IP
                    self.device_name = self.controller.get_device_name()
                    self.shared_state["device"] = self.device_name
                    self.shared_state["connected"] = True
                    self.shared_state["api_status"]["adb"] = True
                    self._adb_reconnect_delay = 5
                    self._next_adb_reconnect_at = 0
                    self._adb_offline_notified = False
                    logger.info(f"ADB connected: {self.device_name}")
                else:
                    self.shared_state["connected"] = False
                    self.shared_state["api_status"]["adb"] = False
                    error = getattr(self.controller, "last_connect_error", "") or "unknown error"
                    logger.warning(f"ADB connect failed: {error}")
            finally:
                self._adb_connecting = False
        threading.Thread(target=_connect, daemon=True).start()

    def _handle_adb_offline(self):
        self._update_api_status()
        self.shared_state.update({
            "connected": False,
            "is_playing": False,
            "title": "Device Offline",
            "subtitle": "Waiting for Android TV to wake or reconnect...",
            "progress": 0,
            "position": 0,
            "duration": 0,
            "next_skip": None,
        })
        if not self._adb_offline_notified:
            reason = getattr(self.controller, "last_disconnect_reason", "") or getattr(self.controller, "last_connect_error", "")
            logger.info(f"ADB offline; auto-reconnect enabled. {reason}".strip())
            self._adb_offline_notified = True
            if self.rpc.connected:
                self.rpc.clear()
        now = time.time()
        if now >= self._next_adb_reconnect_at and not self._adb_connecting:
            self.connect_adb()
            self._next_adb_reconnect_at = now + self._adb_reconnect_delay
            self._adb_reconnect_delay = min(self._adb_reconnect_delay * 2, 60)

    def _start_web_server(self):
        run_server(self)

    def start_gui(self):
        # Wait briefly for the web server thread to bind a port. If port
        # collision occurred, run_server() picks a free one and stores it
        # at self.dashboard_port / ASCEND_BOUND_PORT — open THAT one in
        # the browser, not the configured port.
        for _ in range(40):  # up to ~4 seconds
            if os.environ.get("ASCEND_BOUND_PORT") or getattr(self, "dashboard_port", None):
                break
            time.sleep(0.1)
        port = int(
            os.environ.get("ASCEND_BOUND_PORT")
            or getattr(self, "dashboard_port", None)
            or os.environ.get("ASCEND_PORT", self.config.get("dashboard_port", 5466))
        )
        url = f'http://127.0.0.1:{port}'
        gui_mode = os.environ.get("GUI_MODE", "browser").lower()
        headless = os.environ.get("HEADLESS", "").strip() == "1"
        if headless:
            logger.info(f"Running in headless mode. Dashboard at {url}")
            try:
                while self.running: time.sleep(1)
            except KeyboardInterrupt: self.running = False
        elif HAS_WEBVIEW and gui_mode == "app":
            webview.create_window('Stremio Ascend', url, width=1280, height=850, background_color='#000000')
            webview.start()
            self.running = False
        else:
            time.sleep(1.2)
            webbrowser.open(url)
            try:
                while self.running: time.sleep(1)
            except KeyboardInterrupt: self.running = False

    def _episode_label(self, status):
        season = status.get("season")
        episode = status.get("episode")
        if season is None or episode is None:
            return None
        try:
            label = f"S{int(season):02d}:E{int(episode):02d}"
        except (TypeError, ValueError):
            return None
        # Prioritize TMDB/Online name over Wako Heist name
        ep_title = status.get("episode_title") or status.get("ep_title")
        if ep_title:
            return f"{label} ({ep_title})"
        return label

    def _clean_title_for_rpc(self, title: str) -> str:
        """Aggressively strip redundant 'Watching', 'Wako:', or 'Stremio:' prefixes"""
        title = self._normalize_display_text(title)
        if not title:
            return ""
        # Remove everything before the actual title if it looks like a prefix
        while True:
            # Handle "Watching", "Watching:", "Wako:", "Stremio:" etc.
            new_title = re.sub(r'^(Watching|Wako|Stremio|Watching Wako|Watching Stremio)[:\s]+', '', title, flags=re.I).strip()
            if new_title == title: break
            title = new_title
        return title

    def _prepare_metadata_lookup(self, title, status, is_wako=False):
        clean_title = self._clean_title_for_rpc(title)
        if is_wako or not clean_title:
            return clean_title, None

        resolver = getattr(self, "title_resolver", None) or MediaTitleResolver()
        resolved = resolver.resolve(clean_title)
        if resolved.title:
            clean_title = resolved.title
        if resolved.season is not None and not status.get("season"):
            status["season"] = resolved.season
        if resolved.episode is not None and not status.get("episode"):
            status["episode"] = resolved.episode
        if resolved.episode_title and not status.get("episode_title") and not status.get("ep_title"):
            status["episode_title"] = resolved.episode_title
        return clean_title, resolved

    def _select_discord_client_id(self, is_wako=False):
        if is_wako and self.config.get("discord_wako_client_id"):
            return self.config.get("discord_wako_client_id")
        return self.config.get("discord_client_id", "")

    def _display_app_name(self, app_pkg):
        value = (app_pkg or "").strip()
        if "wako" in value.lower():
            return "Wako"
        return value

    def _normalize_device_name(self, device_name: str) -> str:
        value = (device_name or "").strip()
        upper_value = value.upper()
        if "NVIDIA" in upper_value and ("SHILED" in upper_value or "SHEILD" in upper_value or "SHIELD" in upper_value):
            return "NVIDIA SHIELD TV"
        return value

    def _is_wako_app(self, app_pkg, status=None):
        focus = (status or {}).get("focus", "") if isinstance(status, dict) else ""
        return (
            self.config.get("wako_mode", False)
            and ("wako" in (app_pkg or "").lower() or "app.wako" in focus)
        )

    def _is_local_stremio_app(self, app_pkg):
        value = (app_pkg or "").lower()
        return "stremio" in value and ("desktop" in value or "enhanced" in value)

    def _is_erdb_image_url(self, url: str) -> bool:
        if not url:
            return False
        config = getattr(self, "config", {}) or {}
        base_url = (config.get("erdbBaseUrl") or config.get("erdb_base_url") or ERDBClient.DEFAULT_BASE_URL).strip().rstrip("/")
        try:
            parsed_url = urllib.parse.urlsplit(url)
            parsed_base = urllib.parse.urlsplit(base_url)
            return parsed_url.netloc.lower() == parsed_base.netloc.lower()
        except Exception:
            return "easyratingsdb.com/" in url.lower()

    def get_erdb_discord_art_path(self, cache_key: str):
        record = self.erdb_artwork_cache.get(cache_key)
        if not record:
            return None
        return record.get("path")

    def _erdb_discord_asset_url(self, url: str):
        if not self._is_erdb_image_url(url):
            return url
        host = self.config.get("dashboard_public_base_url", "").strip().rstrip("/")
        if not host or host.startswith("http://127.0.0.1") or host.startswith("http://localhost"):
            proxied = self._wsrv_rpc_image(url, "contain")
            return proxied if len(proxied) <= 300 else url
        if not Image or not requests:
            proxied = self._wsrv_rpc_image(url, "contain")
            return proxied if len(proxied) <= 300 else url
        cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        cached = self.erdb_artwork_cache.get(cache_key)
        if not cached:
            cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "erdb_artwork_cache")
            os.makedirs(cache_dir, exist_ok=True)
            path = os.path.join(cache_dir, f"{cache_key}.png")
            if not os.path.exists(path):
                try:
                    response = requests.get(url, timeout=20)
                    response.raise_for_status()
                    image = Image.open(BytesIO(response.content)).convert("RGBA")
                    image.thumbnail((512, 512), Image.Resampling.LANCZOS)
                    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
                    canvas.alpha_composite(image, ((512 - image.width) // 2, (512 - image.height) // 2))
                    canvas.save(path, format="PNG", optimize=True)
                except Exception as exc:
                    logger.warning(f"ERDB Discord square artwork failed; using wsrv renderer URL. reason={exc.__class__.__name__}")
                    proxied = self._wsrv_rpc_image(url, "contain")
                    return proxied if len(proxied) <= 300 else url
            cached = {"path": path}
            self.erdb_artwork_cache[cache_key] = cached
        return f"{host}/api/artwork/erdb/discord/{cache_key}.png"

    def _rpc_image_url_limit(self) -> int:
        try:
            return int(self.config.get("rpc_image_url_limit", 256))
        except Exception:
            return 256

    def _is_top_posters_image_url(self, url: str) -> bool:
        if not url:
            return False

        try:
            parsed = urllib.parse.urlsplit(str(url).strip())
            host = parsed.netloc.lower()

            configured = (
                self.config.get("top_posters_base_url")
                or "https://api.top-posters.com"
            ).strip().rstrip("/")
            configured_host = urllib.parse.urlsplit(configured).netloc.lower()

            return host in {
                configured_host,
                "api.top-posters.com",
                "api.top-streaming.stream",
            }
        except Exception:
            lowered = str(url or "").lower()
            return (
                "api.top-posters.com/" in lowered
                or "api.top-streaming.stream/" in lowered
            )

    def _clean_top_posters_rpc_url(self, url: str) -> str:
        try:
            parsed = urllib.parse.urlsplit(str(url or "").strip())

            scheme = parsed.scheme or "https"
            netloc = parsed.netloc

            # Normalize old host to current official API host.
            if "top-streaming.stream" in netloc.lower():
                netloc = "api.top-posters.com"

            query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)

            remove_params = {
                "w", "h", "width", "height",
                "fit", "crop", "trim", "precrop",
                "bg", "cbg", "output", "v",

                # Critical: nested fallback makes URL huge.
                "fallback_url",
                "fallback",
            }

            cleaned_query = [
                (key, value)
                for key, value in query
                if key.lower() not in remove_params
            ]

            existing = {key.lower() for key, _ in cleaned_query}

            def add_if_missing(key, value):
                lk = key.lower()
                if lk not in existing and value not in (None, ""):
                    cleaned_query.append((key, str(value)))
                    existing.add(lk)

            lower_path = parsed.path.lower()

            if "/poster/" in lower_path:
                add_if_missing("style", self.config.get("top_posters_style") or "modern")

            if "/thumbnail/" in lower_path:
                add_if_missing("badge_size", self.config.get("top_posters_badge_size") or "medium")
                add_if_missing("badge_position", self.config.get("top_posters_badge_position") or "bottom-left")
                add_if_missing("blur", "true" if self.config.get("top_posters_blur") else "false")

            return urllib.parse.urlunsplit(
                (
                    scheme,
                    netloc,
                    parsed.path,
                    urllib.parse.urlencode(cleaned_query, doseq=True),
                    "",
                )
            )

        except Exception:
            return str(url or "").strip()

    def _rpc_artwork_cache_dir(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "rpc_artwork_cache",
        )
        os.makedirs(path, exist_ok=True)
        return path

    def _rpc_artwork_manifest_path(self):
        return os.path.join(self._rpc_artwork_cache_dir(), "manifest.json")

    def _load_rpc_artwork_manifest(self):
        if getattr(self, "rpc_artwork_upload_manifest_loaded", False):
            return

        self.rpc_artwork_upload_manifest_loaded = True
        path = self._rpc_artwork_manifest_path()

        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    self.rpc_artwork_upload_cache = json.load(f)
        except Exception:
            self.rpc_artwork_upload_cache = {}

    def _save_rpc_artwork_manifest(self):
        try:
            # Prune to last 2 items only as requested
            if len(self.rpc_artwork_upload_cache) > 2:
                keys = list(self.rpc_artwork_upload_cache.keys())
                old_keys = keys[:-2]
                new_cache = {k: self.rpc_artwork_upload_cache[k] for k in keys[-2:]}
                
                # Delete files for old keys
                cache_dir = self._rpc_artwork_cache_dir()
                for k in old_keys:
                    try:
                        path = self._rpc_artwork_cache_path(k)
                        if os.path.exists(path):
                            os.remove(path)
                    except Exception: pass
                
                self.rpc_artwork_upload_cache = new_cache

            with open(self._rpc_artwork_manifest_path(), "w", encoding="utf-8") as f:
                json.dump(self.rpc_artwork_upload_cache, f, indent=2)
        except Exception as exc:
            logger.debug(f"RPC artwork manifest save failed: {exc}")

    def _rpc_artwork_key(self, source_url: str, fit: str = "contain") -> str:
        clean = (
            self._clean_top_posters_rpc_url(source_url)
            if self._is_top_posters_image_url(source_url)
            else source_url
        )

        raw = "|".join(
            [
                str(clean or ""),
                str(fit or "contain"),
                str(self.config.get("artwork_cache_size", 1024)),
            ]
        )

        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def _rpc_artwork_cache_path(self, key: str) -> str:
        safe = "".join(
            ch for ch in str(key or "")
            if ch.isalnum() or ch in ("-", "_")
        )
        return os.path.join(self._rpc_artwork_cache_dir(), f"{safe}.png")

    def _public_dashboard_base_url(self):
        public_base = str(
            self.config.get("dashboard_public_base_url", "") or ""
        ).strip().rstrip("/")

        if not public_base:
            return None

        lowered = public_base.lower()

        if "localhost" in lowered or "127.0.0.1" in lowered:
            return None

        if not public_base.startswith(("http://", "https://")):
            return None

        return public_base

    def _rpc_cached_artwork_public_url(self, key: str):
        public_base = self._public_dashboard_base_url()
        if not public_base:
            return None

        url = f"{public_base}/i/{key}.png"
        return url if len(url) <= self._rpc_image_url_limit() else None

    def _rpc_cached_artwork_local_url(self, key: str):
        return f"/i/{key}.png"

    def _resize_artwork_to_square(self, source_url: str, output_path: str, fit: str = "contain") -> bool:
        try:
            # Some artwork hosts (e.g. api.top-posters.com behind certain CDNs) return
            # SSL "UNEXPECTED_EOF_WHILE_READING" when hit with the default urllib3
            # User-Agent. A browser-like UA + small retry loop reliably recovers.
            response = None
            last_err = None
            for attempt in range(3):
                try:
                    response = requests.get(
                        source_url,
                        timeout=(8, 20),
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/124.0.0.0 Safari/537.36"
                            ),
                            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                            "Accept-Encoding": "gzip, deflate, br",
                            "Connection": "keep-alive",
                        },
                    )
                    response.raise_for_status()
                    break
                except (requests.exceptions.SSLError,
                        requests.exceptions.ConnectionError,
                        requests.exceptions.ChunkedEncodingError) as exc:
                    last_err = exc
                    time.sleep(0.4 * (attempt + 1))
                    response = None
            if response is None:
                raise last_err or RuntimeError("artwork fetch failed after retries")

            content_type = response.headers.get("Content-Type", "").lower()
            if content_type and not content_type.startswith("image/"):
                raise ValueError(f"non-image content-type: {content_type}")

            size = int(self.config.get("artwork_cache_size", 1024) or 1024)
            size = max(256, min(size, 2048))

            img = Image.open(BytesIO(response.content)).convert("RGBA")

            if fit == "cover":
                ratio = max(size / img.width, size / img.height)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

                left = max(0, (img.width - size) // 2)
                top = max(0, (img.height - size) // 2)

                canvas = img.crop((left, top, left + size, top + size))
            else:
                img.thumbnail((size, size), Image.Resampling.LANCZOS)

                canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                canvas.alpha_composite(
                    img,
                    ((size - img.width) // 2, (size - img.height) // 2),
                )

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            canvas.save(output_path, format="PNG", optimize=True)

            return os.path.exists(output_path)

        except Exception as exc:
            logger.warning(
                f"RPC artwork cache render failed │ {exc.__class__.__name__}: {exc}"
            )
            return False

    def _upload_cached_rpc_artwork(self, key: str, path: str):
        """
        Optional upload fallback.

        Configure:
          artwork_upload_enabled: true
          artwork_upload_command: python upload_art.py "{file}"

        The command must print the final public image URL.
        """
        self._load_rpc_artwork_manifest()

        existing = self.rpc_artwork_upload_cache.get(key)
        if existing and isinstance(existing, str) and existing.startswith("http"):
            if len(existing) <= self._rpc_image_url_limit():
                return existing

        if not self.config.get("artwork_upload_enabled", False):
            return None

        command = str(self.config.get("artwork_upload_command", "") or "").strip()
        if not command:
            return None

        if not os.path.exists(path):
            return None

        try:
            timeout = int(self.config.get("artwork_upload_timeout", 45) or 45)

            cmd = (
                command
                .replace("{file}", path)
                .replace("{key}", key)
                .replace("{name}", f"{key}.png")
            )

            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            output = "\n".join(
                [
                    result.stdout or "",
                    result.stderr or "",
                ]
            )

            match = re.search(r"https?://[^\s\"'<>]+", output)
            if not match:
                logger.warning("RPC artwork upload command did not return a URL.")
                return None

            uploaded_url = match.group(0).strip()

            if len(uploaded_url) > self._rpc_image_url_limit():
                logger.warning(f"RPC artwork upload URL too long │ len={len(uploaded_url)}")
                return None

            self.rpc_artwork_upload_cache[key] = uploaded_url
            self._save_rpc_artwork_manifest()

            logger.info(
                f"🖼️ RPC artwork uploaded/cache mapped │ key={key} │ url_len={len(uploaded_url)}"
            )

            return uploaded_url

        except Exception as exc:
            logger.warning(f"RPC artwork upload failed │ {exc.__class__.__name__}: {exc}")
            return None

    def _lazy_cached_or_uploaded_rpc_artwork_url(
        self,
        source_url: str,
        fit: str = "contain",
        for_discord: bool = True,
        allow_download: bool = True,
    ):
        """
        No download unless needed.

        For Discord:
          1. Existing uploaded URL.
          2. Existing public dashboard cache URL.
          3. Download once only if allowed.
          4. Public dashboard URL.
          5. Optional uploader command.

        For dashboard:
          - Local /i/<key>.png route is allowed.
        """
        if not source_url:
            return None

        key = self._rpc_artwork_key(source_url, fit)
        path = self._rpc_artwork_cache_path(key)
        limit = self._rpc_image_url_limit()

        self._load_rpc_artwork_manifest()

        uploaded_url = self.rpc_artwork_upload_cache.get(key)
        if for_discord and uploaded_url and len(uploaded_url) <= limit:
            return uploaded_url

        if os.path.exists(path):
            if for_discord:
                public_url = self._rpc_cached_artwork_public_url(key)
                if public_url:
                    return public_url

                uploaded_url = self._upload_cached_rpc_artwork(key, path)
                if uploaded_url:
                    return uploaded_url

                return None

            return self._rpc_cached_artwork_local_url(key)

        if not allow_download or not self.config.get("artwork_cache_enabled", True):
            return None

        clean_source = (
            self._clean_top_posters_rpc_url(source_url)
            if self._is_top_posters_image_url(source_url)
            else source_url
        )

        ok = self._resize_artwork_to_square(clean_source, path, fit=fit)
        if not ok:
            return None

        if for_discord:
            public_url = self._rpc_cached_artwork_public_url(key)
            if public_url:
                logger.info(
                    f"🖼️ RPC artwork cached │ key={key} │ url_len={len(public_url)}"
                )
                return public_url

            return self._upload_cached_rpc_artwork(key, path)

        return self._rpc_cached_artwork_local_url(key)

    def _compact_wsrv_source(self, url: str) -> str:
        """
        Encode the source URL for wsrv.nl.

        Optimization:
        - Use base64 if it's shorter than percent-encoding (common for long URLs with query strings).
        - wsrv.nl supports 'url=base64:...'
        """
        import base64
        raw_url = str(url or "").strip()
        if not raw_url:
            return ""
            
        quoted = urllib.parse.quote(raw_url, safe=":/%")
        
        # Base64 encoding
        try:
            b64_val = base64.urlsafe_b64encode(raw_url.encode("utf-8")).decode("ascii").rstrip("=")
            b64_url = f"base64:{b64_val}"
            return b64_url if len(b64_url) < len(quoted) else quoted
        except Exception:
            return quoted


    def _wsrv_rpc_image(self, url: str, fit: str = "contain") -> str:
        """
        Discord-safe square image URL.

        For posters/thumbnails:
        - fit=contain prevents cutoff.
        - cbg=0000 gives the contain padding a transparent background (shorter than 00000000).
        - output=png keeps transparency.
        """
        fit = fit if fit in {"contain", "cover", "fill", "inside", "outside"} else "contain"
        safe_url = self._compact_wsrv_source(url)

        # Stable cache key: shortened to 6 chars to save URL space.
        cache_key = hashlib.sha1(str(url).encode("utf-8")).hexdigest()[:6]

        return (
            f"https://wsrv.nl/?url={safe_url}"
            f"&w=512&h=512"
            f"&fit={fit}"
            f"&cbg=0000"
            f"&output=png"
            f"&v={cache_key}"
        )

    def _upload_bytes_to_fileditch(self, cache_key: str, content: bytes, filename: str, mime_type: str) -> str | None:
        if not requests or not content:
            return None
        if not hasattr(self, "_0x0_cache"):
            self._0x0_cache = {}
            self._0x0_last_error = 0
        if cache_key in self._0x0_cache:
            return self._0x0_cache[cache_key]
        now = time.time()
        if now - self._0x0_last_error < 300:
            return None
        try:
            upload_resp = requests.post(
                f"https://new.fileditch.com/upload.php?filename={urllib.parse.quote(filename)}",
                files={"file": (filename, content, mime_type)},
                timeout=15.0,
            )
            if upload_resp.status_code == 200:
                hosted_url = _fileditch_hosted_url(upload_resp.json())
                if hosted_url and len(hosted_url) <= self._rpc_image_url_limit():
                    self._0x0_cache[cache_key] = hosted_url
                    logger.info(f"FileDitch GIF upload success: {hosted_url}")
                    return hosted_url
        except Exception as e:
            logger.warning(f"FileDitch GIF upload failed: {e}; trying Pixeldrain fallback...")
            try:
                upload_resp = requests.post(
                    "https://pixeldrain.com/api/file",
                    data={"anonymous": "true"},
                    files={"file": (filename, content, mime_type)},
                    timeout=15.0,
                )
                if upload_resp.status_code == 200 or upload_resp.status_code == 201:
                    result = upload_resp.json()
                    file_id = result.get("id") if isinstance(result, dict) else None
                    if isinstance(result, dict) and result.get("success") and isinstance(file_id, str) and file_id.strip():
                        hosted_url = f"https://pixeldrain.com/api/file/{file_id.strip()}"
                        self._0x0_cache[cache_key] = hosted_url
                        logger.info(f"Pixeldrain GIF upload success: {hosted_url}")
                        return hosted_url
            except Exception as pixeldrain_err:
                self._0x0_last_error = now
                logger.warning(f"Pixeldrain GIF upload also failed: {pixeldrain_err}; falling back to static network logo")
        return None

    def _center_crop_animated_gif_to_0x0(self, url: str, size: int = 256) -> str | None:
        if not requests or not Image or not ImageOps or not ImageSequence:
            return None
        cache_key = f"nuvio-gif-contain:{hashlib.sha1(url.encode('utf-8')).hexdigest()}"
        if hasattr(self, "_0x0_cache") and cache_key in self._0x0_cache:
            return self._0x0_cache[cache_key]
        try:
            headers = {}
            if "nuvioapp.space" in url or "supabase.co" in url:
                if hasattr(self, "nuvio_covers") and self.nuvio_covers:
                    headers = self.nuvio_covers._headers()
                    
            response = requests.get(url, headers=headers, timeout=8.0)
            if response.status_code != 200 or not response.content:
                return None

            source = Image.open(BytesIO(response.content))
            frames = []
            durations = []
            loop = source.info.get("loop", 0)

            # Pass 1: Find global bounding box of content (non-transparent pixels)
            total_bbox = None
            raw_frames = []
            for frame in ImageSequence.Iterator(source):
                frame_rgba = frame.convert("RGBA")
                raw_frames.append(frame_rgba)
                
                # Get bounding box of non-zero alpha pixels
                bbox = frame_rgba.getbbox()
                if bbox:
                    if total_bbox is None:
                        total_bbox = list(bbox)
                    else:
                        total_bbox[0] = min(total_bbox[0], bbox[0]) # Left
                        total_bbox[1] = min(total_bbox[1], bbox[1]) # Top
                        total_bbox[2] = max(total_bbox[2], bbox[2]) # Right
                        total_bbox[3] = max(total_bbox[3], bbox[3]) # Bottom
                
                if len(raw_frames) >= 120:
                    break

            # Add a tiny 2% margin to prevent the logo from touching the exact edge
            if total_bbox:
                w, h = total_bbox[2] - total_bbox[0], total_bbox[3] - total_bbox[1]
                margin_w, margin_h = int(w * 0.02), int(h * 0.02)
                total_bbox = (
                    max(0, total_bbox[0] - margin_w),
                    max(0, total_bbox[1] - margin_h),
                    min(source.width, total_bbox[2] + margin_w),
                    min(source.height, total_bbox[3] + margin_h)
                )

            # Pass 2: Crop to content and Fit to Square
            for frame_rgba in raw_frames:
                content = frame_rgba.crop(total_bbox) if total_bbox else frame_rgba
                contained = content.copy()
                contained.thumbnail((size, size), Image.Resampling.LANCZOS)
                cropped = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                x = (size - contained.width) // 2
                y = (size - contained.height) // 2
                cropped.alpha_composite(contained, (x, y))
                
                frames.append(cropped.convert("P", palette=Image.ADAPTIVE))
                durations.append(source.info.get("duration", 80))

            if not frames:
                return None

            output = BytesIO()
            frames[0].save(
                output,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=loop,
                disposal=2,
                optimize=True,
            )
            return self._upload_bytes_to_fileditch(cache_key, output.getvalue(), "network.gif", "image/gif")
        except Exception as e:
            logger.debug(f"Animated GIF crop failed for {url}: {e}")
            return None

    def _log_small_icon_debug(self, message: str):
        seen = getattr(self, "_small_icon_debug_seen", None)
        order = getattr(self, "_small_icon_debug_order", None)
        if seen is None or order is None:
            seen = set()
            order = []
            self._small_icon_debug_seen = seen
            self._small_icon_debug_order = order
        if message in seen:
            return
        seen.add(message)
        order.append(message)
        if len(order) > 80:
            old = order.pop(0)
            seen.discard(old)
        logger.info(f"RPC Small Icon DEBUG: {message}")

    def _log_nuvio_gif_debug(self, message: str):
        seen = getattr(self, "_nuvio_gif_debug_seen", None)
        order = getattr(self, "_nuvio_gif_debug_order", None)
        if seen is None or order is None:
            seen = set()
            order = []
            self._nuvio_gif_debug_seen = seen
            self._nuvio_gif_debug_order = order
        if message in seen:
            return
        seen.add(message)
        order.append(message)
        if len(order) > 80:
            old = order.pop(0)
            seen.discard(old)
        logger.info(f"Nuvio network GIF DEBUG: {message}")

    def _save_nuvio_token(self, token: str):
        if self.config.get("nuvio_covers_token") != token:
            self.config["nuvio_covers_token"] = token
            # We don't save to file here to avoid excessive writes, 
            # but we update the in-memory config which is saved on exit/change.
            # Actually, saving to file is safer.
            try:
                from src.core.config import save_config
                save_config(self.config)
                logger.info("Nuvio covers: Saved fresh token to config.json")
            except Exception as e:
                logger.error(f"Nuvio covers: Failed to save refreshed token: {e}")

    def _nuvio_network_search_names(self, network_name: str) -> list[str]:
        name = self._normalize_display_text(network_name)
        key = (name or "").casefold().replace("&", "and").strip()
        key = " ".join(key.replace("+", " plus ").split())
        aliases = {
            "paramount plus": ["Paramount +", "Paramount"],
            "cbs": ["CBS", "Paramount +", "Paramount"],
        }
        candidates = aliases.get(key, [name])
        unique = []
        for candidate in [*candidates, name]:
            candidate = self._normalize_display_text(candidate)
            if candidate and candidate not in unique:
                unique.append(candidate)
        return unique

    def _wsrv_small_rpc_image(self, url: str, animated: bool = False) -> str | None:
        if not url:
            return None
        url = str(url).strip()
        if not url.startswith("http"):
            return url

        safe_url = self._compact_wsrv_source(url)
        cache_key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:6]
        if animated:
            self._log_small_icon_debug(f"animated gif mode; skipping wsrv because wsrv is static-only src_len={len(url)}")
            cropped_url = self._center_crop_animated_gif_to_0x0(url, size=256)
            if cropped_url:
                self._log_small_icon_debug(f"using x0.at cropped animated gif len={len(cropped_url)}")
                return cropped_url
            
            # Privacy: Never leak Nuvio source URLs directly if they fail to crop
            if "nuvioapp.space" in url or "supabase.co" in url:
                self._log_small_icon_debug("animated Nuvio GIF crop failed; blocking direct URL exposure for privacy")
                return None
                
            if len(url) <= self._rpc_image_url_limit():
                self._log_small_icon_debug(f"using direct animated gif len={len(url)}")
                return url
            return None

        proxied = (
            f"https://wsrv.nl/?url={safe_url}"
            f"&w=256&h=256&fit=contain"
            f"&padding=10"
            f"&output=png"
            f"&v={cache_key}"
        )
        if len(proxied) <= self._rpc_image_url_limit():
            self._log_small_icon_debug(f"using wsrv static small icon len={len(proxied)} src={url[:120]}")
            return proxied
        self._log_small_icon_debug(f"wsrv static small icon too long len={len(proxied)} src={url[:120]}")
        return None

    def _nuvio_network_gif_url(self):
        if not self.config.get("nuvio_covers_enabled", False):
            return None
        network_name = self._normalize_display_text(self.last_network_name)
        if not network_name:
            return None
        search_names = self._nuvio_network_search_names(network_name)
        if search_names != [network_name]:
            self._log_nuvio_gif_debug(f"aliases network={network_name!r} searches={search_names!r}")

        if not hasattr(self, "nuvio_covers") or not self.nuvio_covers:
            self.nuvio_covers = NuvioCoversClient(
                self.config.get("nuvio_covers_base_url", "https://nuvioapp.space"),
                self.config.get("nuvio_covers_token", ""),
                self.config.get("nuvio_covers_email", ""),
                self.config.get("nuvio_covers_password", ""),
                on_token_refresh=self._save_nuvio_token,
            )

        orientation = self.config.get("nuvio_covers_orientation", "all")
        result = None
        search_name = search_names[0]
        for candidate in search_names:
            search_name = candidate
            result = self.nuvio_covers.find_popular_gif(candidate, orientation=orientation)
            if result:
                break
        if not result:
            self._log_nuvio_gif_debug(
                f"no popular GIF match network={network_name!r} searches={search_names!r}; falling back to network logo"
            )
            return None

        self.last_network_gif_url = result.get("image_url")
        self.last_network_gif_name = result.get("title") or network_name
        if self.last_network_gif_url:
            self._log_nuvio_gif_debug(
                f"selected network={network_name!r} search={search_name!r} title={self.last_network_gif_name!r} url_len={len(self.last_network_gif_url)}"
            )
        return self.last_network_gif_url

    def _upload_to_0x0(self, url: str) -> str | None:
        """Proxies an image URL through FileDitch (primary), Pixeldrain (secondary), or x0.at (fallback) for maximum speed and privacy."""
        if not hasattr(self, "_0x0_cache"):
            self._0x0_cache = {}
            self._0x0_failures = {}     # host -> {count, last_ts}
            self._0x0_last_error = 0    # legacy global; kept for compat

        if not url:
            return None
        if url in self._0x0_cache:
            return self._0x0_cache[url]

        # 1. Always attempt FileDitch first (Discord compatible)
        fileditch_url = self._upload_to_fileditch(url)
        if fileditch_url:
            self._0x0_cache[url] = fileditch_url
            return fileditch_url

        # 2. Attempt Pixeldrain second (Discord compatible fallback)
        pixeldrain_url = self._upload_to_pixeldrain(url)
        if pixeldrain_url:
            self._0x0_cache[url] = pixeldrain_url
            return pixeldrain_url

        # 3. Fall back to x0.at/0x0.st only if both FileDitch and Pixeldrain fail
        now = time.time()
        try:
            host = urllib.parse.urlsplit(url).netloc.lower()
        except Exception:
            host = "?"

        fail = self._0x0_failures.get(host, {"count": 0, "ts": 0})
        if fail["count"] >= 3 and (now - fail["ts"] < 300):
            return None
        if fail["count"] >= 3 and (now - fail["ts"] >= 300):
            fail = {"count": 0, "ts": 0}
            self._0x0_failures[host] = fail

        BROWSER_UA = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

        try:
            import requests

            img_resp = None
            for attempt in range(2):
                try:
                    img_resp = requests.get(
                        url,
                        timeout=(5, 12),
                        headers={
                            "User-Agent": BROWSER_UA,
                            "Accept": "image/*,*/*;q=0.8",
                        },
                    )
                    break
                except (requests.exceptions.SSLError,
                        requests.exceptions.ConnectionError):
                    if attempt == 1:
                        raise
                    time.sleep(0.5)

            if not img_resp or img_resp.status_code != 200:
                fail["count"] = fail["count"] + 1
                fail["ts"] = now
                self._0x0_failures[host] = fail
                return None

            content_type = img_resp.headers.get("Content-Type", "image/jpeg")
            ext = ".png" if "png" in content_type.lower() else ".jpg"
            filename = f"artwork{ext}"

            upload_resp = requests.post(
                "https://x0.at",
                files={"file": (filename, img_resp.content, content_type)},
                headers={"User-Agent": BROWSER_UA},
                timeout=(10, 20),
            )

            hosted_url = upload_resp.text.strip()
            if upload_resp.status_code == 200 and hosted_url.startswith("https://x0.at/"):
                self._0x0_cache[url] = hosted_url
                self._0x0_failures.pop(host, None)
                logger.debug(f"x0.at Fallback Upload: [SUCCESS] -> {hosted_url}")
                return hosted_url
        except Exception as e:
            fail["count"] = fail["count"] + 1
            fail["ts"] = now
            self._0x0_failures[host] = fail
            logger.debug(f"x0.at fallback upload failed: {e}")

        return None

    def _upload_to_fileditch(self, url: str) -> str | None:
        """Primary privacy proxy using FileDitch."""
        if not url:
            return None
            
        if not hasattr(self, "_fileditch_failures"):
            self._fileditch_failures = {"count": 0, "ts": 0}
            
        now = time.time()
        if self._fileditch_failures["count"] >= 3 and (now - self._fileditch_failures["ts"] < 300):
            return None

        try:
            import requests
            img_resp = requests.get(
                url,
                timeout=10,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept": "image/*,*/*;q=0.8",
                },
            )
            if img_resp.status_code != 200:
                return None

            content_type = img_resp.headers.get("Content-Type", "image/png")
            upload_resp = requests.post(
                "https://new.fileditch.com/upload.php?filename=artwork.png",
                files={"file": ("artwork.png", img_resp.content, content_type)},
                timeout=25
            )
            
            if upload_resp.status_code == 200:
                hosted_url = _fileditch_hosted_url(upload_resp.json())
                if hosted_url and len(hosted_url) <= self._rpc_image_url_limit():
                    if _discord_direct_image_url(hosted_url):
                        logger.debug(f"FileDitch Upload: [SUCCESS] -> {hosted_url}")
                        self._fileditch_failures = {"count": 0, "ts": 0}
                        return hosted_url
                    logger.debug(f"FileDitch Upload rejected: hosted URL is not a direct image -> {hosted_url}")
        except Exception as e:
            self._fileditch_failures["count"] += 1
            self._fileditch_failures["ts"] = now
            logger.debug(f"FileDitch Upload Failed: {e}")
            
        return None

    def _upload_to_pixeldrain(self, url: str) -> str | None:
        """Fallback privacy proxy using Pixeldrain."""
        if not url:
            return None
            
        try:
            import requests
            img_resp = requests.get(url, timeout=10)
            if img_resp.status_code != 200:
                return None
                
            content_type = img_resp.headers.get("Content-Type", "image/jpeg")
            ext = ".png" if "png" in content_type.lower() else ".jpg"
            filename = f"artwork{ext}"

            upload_resp = requests.post(
                "https://pixeldrain.com/api/file",
                data={"anonymous": "true"},
                files={"file": (filename, img_resp.content, content_type)},
                timeout=15
            )
            
            if upload_resp.status_code == 200 or upload_resp.status_code == 201:
                result = upload_resp.json()
                file_id = result.get("id") if isinstance(result, dict) else None
                if isinstance(result, dict) and result.get("success") and isinstance(file_id, str) and file_id.strip():
                    hosted_url = f"https://pixeldrain.com/api/file/{file_id.strip()}"
                    logger.debug(f"Pixeldrain Upload: [SUCCESS] -> {hosted_url}")
                    return hosted_url
        except Exception as e:
            logger.debug(f"Pixeldrain Upload Failed: {e}")
            
        return None

    def _upload_local_file_to_0x0(self, source_url: str, local_path: str,
                                  fit: str = "contain",
                                  allow_x0: bool = True) -> str | None:
        """Upload an *already cached* local image file to FileDitch (primary), Pixeldrain (secondary), or x0.at (fallback)."""
        if not requests or not local_path or not os.path.exists(local_path):
            return None
        if not hasattr(self, "_0x0_cache"):
            self._0x0_cache = {}
            self._0x0_failures = {}
            self._0x0_last_error = 0

        cache_key = f"local:{source_url}:{fit}"
        if cache_key in self._0x0_cache:
            return self._0x0_cache[cache_key]

        # 1. Try FileDitch (highly reliable and Discord compatible)
        hosted = self._upload_local_file_to_fileditch(source_url, local_path, fit=fit)
        if hosted:
            self._0x0_cache[cache_key] = hosted
            self._0x0_cache[source_url] = hosted
            return hosted

        # 2. Try Pixeldrain (highly reliable and Discord compatible fallback)
        hosted = self._upload_local_file_to_pixeldrain(source_url, local_path, fit=fit)
        if hosted:
            self._0x0_cache[cache_key] = hosted
            self._0x0_cache[source_url] = hosted
            return hosted

        if not allow_x0:
            return None

        # 3. Fall back to x0.at
        BROWSER_UA = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        try:
            with open(local_path, "rb") as f:
                data = f.read()
            if not data:
                return None
            resp = requests.post(
                "https://x0.at",
                files={"file": ("poster.png", data, "image/png")},
                headers={"User-Agent": BROWSER_UA},
                timeout=(5, 15),
            )
            hosted_fallback = resp.text.strip() if resp is not None else ""
            if resp.status_code == 200 and hosted_fallback.startswith("https://x0.at/"):
                self._0x0_cache[cache_key] = hosted_fallback
                self._0x0_cache[source_url] = hosted_fallback
                logger.info(f"x0.at fallback upload success: {hosted_fallback}")
                return hosted_fallback
        except Exception as e:
            logger.debug(f"x0.at fallback upload failed: {e}")
            
        return None

    def _upload_local_file_to_fileditch(self, source_url: str, local_path: str,
                                     fit: str = "contain") -> str | None:
        """Upload an *already cached* local image file to FileDitch."""
        if not requests or not local_path or not os.path.exists(local_path):
            return None
            
        cache_key = f"local-fileditch:{source_url}:{fit}"
        if hasattr(self, "_0x0_cache") and cache_key in self._0x0_cache:
            return self._0x0_cache[cache_key]

        try:
            with open(local_path, "rb") as f:
                data = f.read()
            if not data:
                return None
                
            resp = requests.post(
                "https://new.fileditch.com/upload.php?filename=artwork.png",
                files={"file": ("artwork.png", data, "image/png")},
                timeout=20
            )
            
            if resp.status_code == 200:
                hosted = _fileditch_hosted_url(resp.json())
                if hosted and len(hosted) <= self._rpc_image_url_limit():
                    if _discord_direct_image_url(hosted):
                        if not hasattr(self, "_0x0_cache"):
                            self._0x0_cache = {}
                        self._0x0_cache[cache_key] = hosted
                        self._0x0_cache[source_url] = hosted
                        logger.info(f"FileDitch upload success: {hosted}")
                        return hosted
                    logger.debug(f"FileDitch upload rejected: hosted URL is not a direct image -> {hosted}")
        except Exception as e:
            logger.debug(f"FileDitch upload failed: {e}")
            
        return None

    def _upload_local_file_to_pixeldrain(self, source_url: str, local_path: str,
                                     fit: str = "contain") -> str | None:
        """Upload an *already cached* local image file to Pixeldrain."""
        if not requests or not local_path or not os.path.exists(local_path):
            return None
            
        cache_key = f"local-pixeldrain:{source_url}:{fit}"
        if hasattr(self, "_0x0_cache") and cache_key in self._0x0_cache:
            return self._0x0_cache[cache_key]

        try:
            with open(local_path, "rb") as f:
                data = f.read()
            if not data:
                return None
                
            resp = requests.post(
                "https://pixeldrain.com/api/file",
                data={"anonymous": "true"},
                files={"file": ("artwork.png", data, "image/png")},
                timeout=15
            )
            
            if resp.status_code == 200 or resp.status_code == 201:
                result = resp.json()
                file_id = result.get("id") if isinstance(result, dict) else None
                if isinstance(result, dict) and result.get("success") and isinstance(file_id, str) and file_id.strip():
                    hosted = f"https://pixeldrain.com/api/file/{file_id.strip()}"
                    if not hasattr(self, "_0x0_cache"):
                        self._0x0_cache = {}
                    self._0x0_cache[cache_key] = hosted
                    self._0x0_cache[source_url] = hosted
                    logger.info(f"Pixeldrain upload success: {hosted}")
                    return hosted
        except Exception as e:
            logger.debug(f"Pixeldrain upload failed: {e}")
            
        return None


    def _proxy_rpc_image(self, url: str, fit: str = "contain", allow_download: bool = True) -> str | None:
        """
        Discord-safe large image helper.

        Rule:
        - Never fall back to direct Top Posters URLs (Discord crops them).
        - Use short Top Posters wsrv URL if possible.
        - Use local/uploaded cache if URL is too long.
        """
        if not url:
            return None

        url = str(url).strip()
        if not url.startswith("http"):
            return url

        lowered = url.lower()
        if "127.0.0.1" in lowered or "localhost" in lowered:
            return None

        is_top = self._is_top_posters_image_url(url)
        is_erdb = self._is_erdb_image_url(url)
        limit = self._rpc_image_url_limit()


        # 0. Privacy Sizing Pipeline: Download locally -> Pillow Resize -> x0.at
        # We bypass wsrv.nl entirely because passing tokenized Top Posters URLs
        # to a 3rd party image proxy leaks the API keys. Local processing is 100% private.
        if is_top or is_erdb:
            clean_source = (
                self._clean_top_posters_rpc_url(url)
                if is_top
                else url
            )

            # First populate the local cache via the lazy helper. We use
            # for_discord=False here so it returns the local /i/ path on
            # success, but the side effect we want is the on-disk PNG.
            self._lazy_cached_or_uploaded_rpc_artwork_url(
                clean_source,
                fit=fit,
                for_discord=False,
                allow_download=allow_download,
            )
            try:
                key = self._rpc_artwork_key(clean_source, fit)
                cache_path = self._rpc_artwork_cache_path(key)
            except Exception:
                cache_path = None

            if cache_path and os.path.exists(cache_path):
                hosted = self._upload_local_file_to_0x0(clean_source, cache_path, fit=fit, allow_x0=True)
                if hosted and len(hosted) <= limit:
                    resized_hosted = self._wsrv_rpc_image(hosted, fit="contain")
                    if len(resized_hosted) <= limit:
                        logger.debug(
                            f"Artwork Pipeline [Step 1]: Local Cache + hosted wsrv URL -> {resized_hosted}"
                        )
                        return resized_hosted

                    logger.debug(f"Artwork Pipeline [Step 1]: Local Cache + hosted URL -> {hosted}")
                    return hosted
            logger.debug("Artwork Pipeline [Step 1]: Local fallback failed.")

            # Public dashboard URL still preferred over wsrv if configured.
            cached_url = self._lazy_cached_or_uploaded_rpc_artwork_url(
                clean_source,
                fit=fit,
                for_discord=True,
                allow_download=False,
            )
            if cached_url:
                return cached_url

            # Last safe Top Posters fallback: direct source is only sent to
            # Discord, not a third-party proxy. This preserves artwork if all
            # token-hiding upload hosts fail.
            if is_top and len(clean_source) <= limit and _discord_direct_image_url(clean_source):
                return clean_source

            # Last Resort: If x0.at and Local fallbacks failed, we return None 
            # to trigger the static app icon fallback. We NEVER use wsrv.nl 
            # for Top Posters to guarantee your API token is never leaked.
            return None

        # 2. Generic wsrv Proxy
        proxied = self._wsrv_rpc_image(url, fit=fit)
        if len(proxied) <= limit:
            return proxied

        # 3. Lazy Cache / Upload
        cached_url = self._lazy_cached_or_uploaded_rpc_artwork_url(
            url,
            fit=fit,
            for_discord=True,
            allow_download=allow_download,
        )
        if cached_url:
            return cached_url

        # 4. Direct URL (Safest for TMDB/ERDB if not too long)
        if len(url) <= limit:
            if is_top:
                logger.debug("Artwork Pipeline [Step 4]: Proxy failed; using direct Top Posters URL as last resort.")
            return url

        return None

    def _log_rpc_artwork_choice(self, provider, label, fit, source_url, discord_url, priority):
        sig = f"{provider}|{label}|{fit}|{source_url}|{discord_url}"

        if getattr(self, "_last_rpc_artwork_table_sig", None) == sig:
            return

        self._last_rpc_artwork_table_sig = sig

        proxy_type = "None"
        if "fileditch" in str(discord_url):
            proxy_type = "FileDitch (Private)"
        elif "pixeldrain" in str(discord_url):
            proxy_type = "Pixeldrain (Private)"
        elif "0x0.st" in str(discord_url):
            proxy_type = "0x0.st (Private)"
        elif "x0.at" in str(discord_url):
            proxy_type = "x0.at (Private)"
        elif "wsrv.nl" in str(discord_url):
            proxy_type = "wsrv.nl (Public)"
        elif str(discord_url).startswith("/i/"):
            proxy_type = "Local Cache"

        log_table(
            "RPC Artwork",
            {
                "Provider": provider,
                "Choice": label,
                "Priority": priority,
                "Proxy": proxy_type,
                "Fit": fit,
                "Discord URL": discord_url if discord_url else "no",
                "Length": len(str(discord_url or "")),
                "Source": source_url,
            },
            icon="🖼️" if not IS_WINDOWS else "[IMG]",
        )

    def _best_rpc_image_url(self):
        """
        Discord large image priority:

        1. Selected provider/mode image.
        2. MAIN FALLBACK: TMDB resized images.
        3. Backup provider images.
        4. None.

        Never force stremio_logo, because a missing Discord app asset shows '?'.
        """
        if not self._normalize_display_text(self.shared_state.get("title")):
            return None

        matched_provider, selected_url, selected_fit = self._best_artwork_source_url()
        limit = self._rpc_image_url_limit()

        candidates = [
            # Fallback chain result first
            (matched_provider or "NONE", "chain result", selected_url, selected_fit, "fallback chain"),

            # Hardcoded safety net (Legacy)
            ("TMDB", "episode resized", self.last_episode_image_url, "contain", "safety net"),
            ("TMDB", "season resized", self.last_season_image_url, "contain", "safety net"),
            ("TMDB", "show resized", self.last_content_image_url, "contain", "safety net"),
        ]

        seen = set()

        for provider, label, img_url, fit, priority in candidates:
            if not img_url:
                continue

            img_url = str(img_url).strip()

            if img_url in seen:
                continue
            seen.add(img_url)

            if not img_url.startswith("http"):
                continue

            lowered = img_url.lower()
            if "127.0.0.1" in lowered or "localhost" in lowered:
                continue

            discord_url = self._proxy_rpc_image(img_url, fit=fit)

            if discord_url and discord_url.startswith("http") and len(discord_url) <= limit:
                self._log_rpc_artwork_choice(
                    provider=provider,
                    label=label,
                    fit=fit,
                    source_url=img_url,
                    discord_url=discord_url,
                    priority=priority,
                )
                return discord_url

        log_once(
            "rpc-artwork-none",
            ("🖼️" if not IS_WINDOWS else "[IMG]") + " RPC Artwork " + ("│" if not IS_WINDOWS else "|") + " no valid image URL found",
            seconds=30,
            level=logging.WARNING,
        )
        return None

    def _strip_rpc_image_params(self, url: str, names):
        parsed = urllib.parse.urlsplit(url)
        query = [
            (key, value)
            for key, value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            if key not in names
        ]
        return urllib.parse.urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urllib.parse.urlencode(query),
                parsed.fragment,
            )
        )

    def _artwork_provider(self):
        provider = self.config.get("artwork_provider", "legacy")
        return provider if provider in {"legacy", "top_posters", "erdb"} else "legacy"

    def _normalize_display_text(self, value):
        if value is None:
            return ""
        text = str(value).strip()
        if not text or text.lower() in {"null", "none", "undefined", "nan"}:
            return ""
        return text

    def _best_artwork_source_url(self):
        mode = self.config.get("rpc_large_image_mode", "episode")
        fit = "contain"
        chain = self.config.get("artwork_fallback_chain", ["top_posters", "erdb", "tmdb"])
        
        # Ensure 'tmdb' is always at the end if not present
        if "tmdb" not in chain:
            chain.append("tmdb")

        for provider in chain:
            img_url = None
            if provider == "top_posters":
                if mode == "episode":
                    img_url = self.last_top_posters_episode_url
                elif mode == "season":
                    img_url = self.last_top_posters_season_url
                else:
                    img_url = self.last_top_posters_show_url
                
                # Intelligent Fallback for Top Posters
                if not img_url:
                    img_url = self.last_top_posters_show_url or self.last_top_posters_season_url or self.last_top_posters_episode_url
                    
            elif provider == "erdb":
                if mode == "episode":
                    img_url = self.last_erdb_episode_url
                elif mode == "season":
                    img_url = self.last_erdb_backdrop_url
                else:
                    img_url = self.last_erdb_show_url
                    
                # Intelligent Fallback for ERDB
                if not img_url:
                    img_url = self.last_erdb_show_url or self.last_erdb_backdrop_url or self.last_erdb_episode_url
            
            elif provider == "tmdb":
                if mode == "episode":
                    img_url = self.last_episode_image_url or self.last_season_image_url or self.last_content_image_url
                elif mode == "season":
                    img_url = self.last_season_image_url or self.last_content_image_url
                else:
                    img_url = self.last_content_image_url
                    
            elif provider == "nuvio":
                img_url = self.last_network_image_url or getattr(self, "last_network_gif_url", None)
            
            if img_url:
                return (provider.upper(), img_url, fit)

        return (None, None, fit)

    def _best_dashboard_image_url(self):
        _provider, img_url, fit = self._best_artwork_source_url()
        if not img_url:
            return None
            
        # For dashboard, we allow the local /i/<key>.png route.
        # This keeps the UI snappy even if public URL isn't configured.
        cached = self._lazy_cached_or_uploaded_rpc_artwork_url(
            img_url,
            fit=fit,
            for_discord=False,
            allow_download=True,
        )
        if cached:
            return cached

        # Cache fetch failed (e.g. upstream api.top-posters.com SSL EOF).
        # Surface a raw TMDB/ERDB URL so the dashboard preview is never blank.
        for raw in (
            self.last_episode_image_url,
            self.last_season_image_url,
            self.last_content_image_url,
        ):
            if raw and isinstance(raw, str) and raw.startswith("http"):
                return raw
        return None

    def _dashboard_fallback_image_url(self):
        if not self._normalize_display_text(self.shared_state.get("title")):
            return None
        selected = self._best_artwork_source_url()[1]
        fallback = self.last_episode_image_url or self.last_season_image_url or self.last_content_image_url
        
        if not fallback or fallback == selected or not fallback.startswith("http"):
            return None
            
        return self._lazy_cached_or_uploaded_rpc_artwork_url(
            fallback, 
            fit="contain", 
            for_discord=False, 
            allow_download=True
        )


    def _player_label(self, title, app_pkg):
        title = self._clean_title_for_rpc(title)

        is_wako_active = self.config.get("wako_mode", False) and app_pkg == "Wako"
        custom_branding = self.config.get("rpc_branding", "on Stremio")
        branding = "on Wako" if is_wako_active else custom_branding

        return f"{title} ({branding})" if title else f"Content ({branding})"

    def _device_state_label(self, app_pkg):
        app_pkg = self._display_app_name(app_pkg)
        if self.config.get("show_device_name", True):
            device = getattr(self, "device_name", None) or self.shared_state.get("device") or "Android TV"
            return f"Watching on {device}"
        return f"Watching on {app_pkg or 'Android TV'}"

    def _app_icon_asset(self, app_pkg):
        app_pkg = self._display_app_name(app_pkg)
        app_name = (app_pkg or "").lower()
        if "wako" in app_name:
            return WAKO_LOGO_URL, "Wako"
        if "vlc" in app_name:
            return "vlc_logo", "VLC"
        if "stremio" in app_name:
            return STREMIO_LOGO_URL, "Stremio"
        return "device", getattr(self, "device_name", None) or "Android TV"

    def _small_rpc_art(self, state, app_pkg):
        mode = self.config.get("rpc_small_icon_mode", "play_status")
        if mode == "content_network_gif":
            gif_url = self._nuvio_network_gif_url()
            if gif_url:
                return gif_url, self.last_network_name or self.last_network_gif_name or "Network"
            if self.last_network_image_url:
                return self.last_network_image_url, self.last_network_name or "Network"
            return self._app_icon_asset(app_pkg)
        if mode == "content_network":
            if self.last_network_image_url:
                return self.last_network_image_url, self.last_network_name or "Network"
            return self._app_icon_asset(app_pkg)
        if mode == "stremio":
            return STREMIO_LOGO_URL, "Stremio"
        if mode == "wako":
            return WAKO_LOGO_URL, "Wako"
        if mode in ("device", "streaming_service"):
            return self._app_icon_asset(app_pkg)
        return ("play" if state == "playing" else "pause"), ("Playing" if state == "playing" else "Paused")

    def _rpc_buttons(self):
        if not self.config.get("rpc_buttons_enabled", True):
            return None
        buttons = []
        if self.last_tmdb_url:
            buttons.append({"label": "View on TMDB", "url": self.last_tmdb_url})
        if self.last_trailer_url:
            buttons.append({"label": "Watch Trailer", "url": self.last_trailer_url})
        return buttons[:2] or None

    def _reset_rpc_timeline(self):
        self.rpc_timeline_key = None
        self.rpc_timeline_start_timestamp = None
        self.rpc_timeline_end_timestamp = None

    def _status_has_valid_progress(self, status):
        try:
            return int(status.get("duration") or 0) > 0 and int(status.get("position") or 0) >= 0
        except (TypeError, ValueError):
            return False

    def _sync_wako_progress(self, position, duration=None, reset_timeline=False):
        try:
            position = max(0, int(position or 0))
        except (TypeError, ValueError):
            return
        try:
            duration = int(duration or 0)
        except (TypeError, ValueError):
            duration = 0

        if duration > 0:
            position = min(position, duration)
            self.wako_cached_duration = duration
        elif self.wako_cached_duration and position > self.wako_cached_duration:
            position = self.wako_cached_duration

        self.wako_cached_position = position
        self.wako_progress_anchor_time = time.time()
        if reset_timeline:
            self._reset_rpc_timeline()

    def _read_post_seek_status(self, fallback_position, fallback_duration=None, previous_position=None):
        fallback_position = int(fallback_position or 0)
        try:
            previous_position = int(previous_position or 0)
        except (TypeError, ValueError):
            previous_position = None

        best_duration = fallback_duration
        for attempt in range(3):
            try:
                status = self.controller.get_playback_status(wako_mode=self.config.get("wako_mode", False))
            except Exception:
                break
            if self._status_has_valid_progress(status):
                try:
                    position = int(status.get("position") or 0)
                    duration = int(status.get("duration") or 0)
                except (TypeError, ValueError):
                    position = None
                    duration = 0
                if duration:
                    best_duration = duration
                if position is not None:
                    near_seek_target = abs(position - fallback_position) <= 2500
                    moved_from_previous = previous_position is None or abs(position - previous_position) > 1500
                    if near_seek_target or moved_from_previous:
                        return position, best_duration
            if attempt < 2:
                time.sleep(0.12)
        return fallback_position, best_duration

    def _commit_seek_progress(self, landed_ms, duration=None, previous_position=None):
        try:
            landed_ms = max(0, int(landed_ms or 0))
        except (TypeError, ValueError):
            landed_ms = 0
        if duration is None:
            duration = self.shared_state.get("duration")
        landed_ms, duration = self._read_post_seek_status(landed_ms, duration, previous_position=previous_position)
        if self.config.get("wako_mode"):
            self._sync_wako_progress(landed_ms, duration, reset_timeline=True)
        else:
            self._reset_rpc_timeline()
        self.shared_state["position"] = landed_ms
        if duration:
            self.shared_state["duration"] = duration
            self.shared_state["progress"] = landed_ms / duration if duration else 0
        self._push_rpc_after_seek(landed_ms, duration)
        return landed_ms, duration

    def _analytics_session_key(self, title, status, app_pkg):
        return (
            self._normalize_display_text(title),
            self._display_app_name(app_pkg),
            self.last_imdb_id or "",
            status.get("season"),
            status.get("episode"),
        )

    def _end_current_analytics_session(self, final_position_ms=None):
        if self._current_session_id == -1:
            return
        try:
            if final_position_ms is None:
                final_position_ms = self.shared_state.get("position", 0)
            self.analytics.end_session(self._current_session_id, int(final_position_ms or 0))
        except Exception as e:
            logger.debug(f"Analytics: end session skipped: {e}")
        finally:
            self._current_session_id = -1
            self._current_session_key = None

    def _track_analytics_playback(self, title, subtitle, status, app_pkg, meta):
        state = status.get("state")
        position = int(status.get("position") or 0)
        if not title or state not in ("playing", "paused"):
            self._end_current_analytics_session(position)
            return

        key = self._analytics_session_key(title, status, app_pkg)
        if self._current_session_id != -1 and key == self._current_session_key:
            return

        self._end_current_analytics_session(position)
        try:
            media_type = meta.get("type", "movie") if meta else "movie"
            self._current_session_id = self.analytics.start_session(
                title,
                subtitle,
                self.last_imdb_id or "",
                media_type,
                self.shared_state.get("image_url") or self.last_image_url or "",
                self._display_app_name(app_pkg),
                int(status.get("duration") or 0),
            )
            self._current_session_key = key
        except Exception as e:
            logger.debug(f"Analytics: start session skipped: {e}")
            self._current_session_id = -1
            self._current_session_key = None

    def _push_rpc_after_seek(self, position, duration):
        clean_title = self._normalize_display_text(self.shared_state.get("title"))
        if not clean_title:
            return
        status = {
            "state": "playing" if self.shared_state.get("is_playing") else "paused",
            "position": int(position or 0),
            "duration": int(duration or 0),
            "season": self.shared_state.get("meta_season"),
            "episode": self.shared_state.get("meta_episode"),
            "_debug_reason": "seek",
        }
        app_pkg = self._display_app_name(self.shared_state.get("app"))
        try:
            self._update_rpc(clean_title, status, app_pkg, app_pkg == "Wako")
        except Exception as e:
            logger.debug(f"Post-seek RPC refresh skipped: {e}")

    def _should_log_wako_missing_duration(self, clean_title, status):
        key = (clean_title or "", status.get("season"), status.get("episode"))
        now = time.time()
        if key != self.last_wako_missing_duration_log_key or now - self.last_wako_missing_duration_log_time >= 60:
            self.last_wako_missing_duration_log_key = key
            self.last_wako_missing_duration_log_time = now
            return True
        return False

    def _debug_playback_timing(self, reason, status, rpc_payload=None):
        if not self.config.get("playback_debug_enabled", False):
            return
        now = time.time()
        if reason != "seek" and now - getattr(self, "_last_playback_debug_log", 0) < 1.0:
            return
        self._last_playback_debug_log = now
        timing = dict(status.get("timing_debug") or {})
        position = int(status.get("position") or self.shared_state.get("position") or 0)
        duration = int(status.get("duration") or self.shared_state.get("duration") or 0)
        dash_position = int(self.shared_state.get("position") or 0)
        dash_duration = int(self.shared_state.get("duration") or 0)
        rpc_payload = rpc_payload or {}
        debug = {
            "reason": reason,
            "state": status.get("state"),
            "source": status.get("timing_source") or timing.get("source"),
            "player_position": position,
            "player_duration": duration,
            "dashboard_position": dash_position,
            "dashboard_duration": dash_duration,
            "rpc_start": rpc_payload.get("start_timestamp"),
            "rpc_end": rpc_payload.get("end_timestamp"),
            "timing": timing,
        }
        self.shared_state["playback_debug"] = debug
        logger.info(
            f"TIMING {reason} state={debug['state']} source={debug['source']} "
            f"player={position}/{duration} dash={dash_position}/{dash_duration} "
            f"raw={timing.get('dumpsys_raw_position')} updated={timing.get('dumpsys_updated')} "
            f"logcat={timing.get('logcat_position')} age={timing.get('logcat_age_ms')}ms "
            f"rpc={debug['rpc_start']}->{debug['rpc_end']}"
        )

    def _enforce_authoritative_timing(self, status):
        timing = status.get("timing_debug") or {}
        duration = int(status.get("duration") or timing.get("duration") or 0)
        source = status.get("timing_source") or timing.get("source")
        authoritative = None

        if source == "logcat" and timing.get("logcat_position") is not None:
            authoritative = int(timing.get("logcat_position") or 0)
            if status.get("state") == "playing":
                authoritative += max(0, int(timing.get("logcat_age_ms") or 0))
        elif source == "dumpsys" and timing.get("dumpsys_projected_position") is not None:
            authoritative = int(timing.get("dumpsys_projected_position") or 0)

        if authoritative is None:
            return status
        if duration > 0:
            authoritative = min(authoritative, duration)
        status["position"] = max(0, authoritative)
        if duration > 0:
            status["duration"] = duration
        return status

    def _apply_wako_progress_cache(self, status, state):
        if self._status_has_valid_progress(status):
            self._sync_wako_progress(status.get("position"), status.get("duration"))
            return status

        if self.wako_cached_position is None or not self.wako_cached_duration:
            return status

        position = self.wako_cached_position
        if state == "playing" and self.wako_progress_anchor_time is not None:
            elapsed_ms = max(0, int((time.time() - self.wako_progress_anchor_time) * 1000))
            position += elapsed_ms
        status["position"] = min(position, self.wako_cached_duration)
        status["duration"] = self.wako_cached_duration
        return status

    def _rpc_timestamps(self, clean_title, status, app_pkg):
        app_pkg = self._display_app_name(app_pkg)
        state = status.get("state")
        if state not in ("playing", "paused"):
            return {}

        try:
            position = max(0, int(status.get("position") or 0))
            duration = int(status.get("duration") or 0)
        except (TypeError, ValueError):
            return {}

        # Use calc_time (the exact moment position was captured) for high-precision anchoring
        now = status.get("calc_time") or time.time()
        
        # MEDIA CHANGE DETECTION
        current_key = (
            clean_title or "",
            app_pkg or "",
            status.get("season"),
            status.get("episode"),
            duration,
        )
        if current_key != self.rpc_timeline_key:
            self.rpc_timeline_start_timestamp = None
            self.rpc_timeline_end_timestamp = None
            self.rpc_timeline_key = current_key

        if duration <= 0:
            # AGGRESSIVE FALLBACK: Try to get duration from TMDB cache or metadata
            meta = getattr(self, "last_meta", None)
            if meta and meta.get("id"):
                runtime_min = meta.get("runtime")
                if not runtime_min:
                    # Try to get from episode cache
                    if status.get("season") is not None and status.get("episode") is not None:
                        ep_details = self.tmdb.get_episode_details(meta["id"], int(status["season"]), int(status["episode"]))
                        if ep_details and ep_details.get("runtime_ms"):
                            duration = ep_details["runtime_ms"]
                elif runtime_min:
                    duration = int(runtime_min) * 60 * 1000
        
        if duration <= 0:
            if position > 0:
                # For unknown duration, we show elapsed time
                ideal_start = int(now - (position / 1000))
                # Apply drift protection even for unknown duration
                if self.rpc_timeline_start_timestamp is not None:
                    if abs(ideal_start - self.rpc_timeline_start_timestamp) > 2:
                         self.rpc_timeline_start_timestamp = ideal_start
                else:
                    self.rpc_timeline_start_timestamp = ideal_start
                
                return {"start_timestamp": self.rpc_timeline_start_timestamp}
            return {}

        position = min(position, duration)
        duration_seconds = max(1, (duration + 999) // 1000)
        
        # Calculate the ideal start timestamp based on current position
        ideal_start = int(now - (position / 1000))
        
        # DRIFT PROTECTION (2.0s aligned with controller seek detection)
        if self.rpc_timeline_start_timestamp is not None:
            drift = abs(ideal_start - self.rpc_timeline_start_timestamp)
            if drift > 2:
                # Significant drift detected (Seek) - Reset timeline
                self.rpc_timeline_start_timestamp = ideal_start
                self.rpc_timeline_end_timestamp = ideal_start + duration_seconds
            elif self.rpc_timeline_end_timestamp is None:
                # Duration was previously unknown, but now we have it - Promote to progress bar
                self.rpc_timeline_end_timestamp = self.rpc_timeline_start_timestamp + duration_seconds
        else:
            # First run - Initialize timeline
            self.rpc_timeline_start_timestamp = ideal_start
            self.rpc_timeline_end_timestamp = ideal_start + duration_seconds

        return {
            "start_timestamp": self.rpc_timeline_start_timestamp,
            "end_timestamp": self.rpc_timeline_end_timestamp,
        }

    def _local_top_posters_season_url(self, cache_key):
        """
        Public URL for the dashboard or Discord.
        """
        public_base = self._public_dashboard_base_url()
        if public_base:
            return f"{public_base}/api/artwork/top-posters/season/{cache_key}.jpg"
            
        # Internal fallback
        return f"/api/artwork/top-posters/season/{cache_key}.jpg"

    def _refresh_top_posters_artwork(self, mode, tv_id, media_type, season, episode):
        self.last_top_posters_show_url = None
        self.last_top_posters_season_url = None
        self.last_top_posters_episode_url = None
        top_posters = getattr(self, "top_posters", None)
        if not top_posters:
            return
        top_posters.update_config(self.config)
        if not self.config.get("top_posters_enabled", True):
            logger.debug("Top Posters disabled in config.")
            return
        if not top_posters.is_enabled():
            logger.debug("Top Posters client not enabled (missing API key).")
            return
        if not self.last_imdb_id and not tv_id:
            logger.debug("Top Posters skipped: no IMDb or TMDB ID available for this content.")
            return

        logger.debug(f"Refreshing Top Posters artwork for {self.last_imdb_id} (mode={mode})")

        show_url = top_posters.build_poster_url(tmdb_id=tv_id)
        if not self._top_posters_artwork_available(top_posters, show_url, "show"):
            show_url = top_posters.build_poster_url(imdb_id=self.last_imdb_id)
            
        if self._top_posters_artwork_available(top_posters, show_url, "show"):
            self.last_top_posters_show_url = show_url

        if mode == "episode" and media_type == "tv" and season is not None and episode is not None:
            logger.debug(f"Top Posters: Requesting episode thumbnail for imdb={self.last_imdb_id}, tmdb={tv_id}, S{season}E{episode}")
            episode_url = top_posters.build_thumbnail_url(imdb_id=None, season=int(season), episode=int(episode), tmdb_id=tv_id)
            if not self._top_posters_artwork_available(top_posters, episode_url, "episode"):
                episode_url = top_posters.build_thumbnail_url(imdb_id=self.last_imdb_id, season=int(season), episode=int(episode), tmdb_id=None)
            if self._top_posters_artwork_available(top_posters, episode_url, "episode"):
                self.last_top_posters_episode_url = episode_url
                logger.info(
                    "Top Posters episode artwork verified: "
                    f"S{int(season)}E{int(episode)} "
                    f"size={self.config.get('top_posters_badge_size', 'medium')} "
                    f"position={self.config.get('top_posters_badge_position', 'bottom-left')}"
                )
            return

        if mode == "season" and media_type == "tv" and tv_id and season is not None:
            generated = top_posters.generate_masked_season_poster(
                self.last_imdb_id,
                tv_id,
                int(season),
                top_poster_url=self.last_top_posters_show_url,
                show_poster_url=self.last_content_image_url,
                season_poster_url=self.last_season_image_url,
            )
            if generated:
                self.last_top_posters_season_url = self._local_top_posters_season_url(generated["cache_key"])
            elif self.last_top_posters_show_url:
                logger.warning("Top Posters season composite unavailable; falling back to remote poster/TMDB artwork.")

    def _top_posters_artwork_available(self, top_posters, url, label):
        if not url:
            return False
        validator = getattr(top_posters, "validate_artwork_url", None)
        if not callable(validator):
            return True
        if validator(url):
            return True
        reason = getattr(top_posters, "last_validation_error", None)
        if not isinstance(reason, str) or not reason:
            reason = "not an image response"
        logger.warning(
            f"Top Posters {label} artwork rejected ({reason}); "
            "falling back to TMDB. Check the API key, subscription tier, and episode rating availability."
        )
        return False

    def _refresh_erdb_artwork(self, mode, media_type, season, episode):
        self.last_erdb_show_url = None
        self.last_erdb_backdrop_url = None
        self.last_erdb_episode_url = None
        erdb = getattr(self, "erdb", None)
        if not erdb:
            return
        erdb.update_config(self.config)
        if not self.config.get("erdb_enabled", True) or not erdb.is_enabled() or not self.last_imdb_id:
            return

        logger.debug(f"Refreshing ERDB artwork for {self.last_imdb_id}")

        # Always fetch poster and backdrop for ERDB to ensure fallbacks are ready
        show_url = erdb.build_url("poster", self.last_imdb_id)
        if self._erdb_artwork_available(erdb, show_url, "poster"):
            self.last_erdb_show_url = show_url

        # Backdrop is often used as a fallback for 'season' mode in ERDB
        backdrop_url = erdb.build_url("backdrop", self.last_imdb_id)
        if self._erdb_artwork_available(erdb, backdrop_url, "backdrop"):
            self.last_erdb_backdrop_url = backdrop_url

        # Episode specific artwork (Thumbnail)
        if media_type == "tv" and season is not None and episode is not None:
            episode_url = erdb.build_episode_thumbnail_url(self.last_imdb_id, int(season), int(episode))
            if self._erdb_artwork_available(erdb, episode_url, "thumbnail"):
                self.last_erdb_episode_url = episode_url
                
                # Pro-Grade Detailed Log
                mode = self.config.get("erdb_episode_id_mode", "realimdb")
                p_on = "on" if self.config.get("erdb_posters_enabled", True) else "off"
                t_on = "on" if self.config.get("erdb_thumbnails_enabled", True) else "off"
                
                logger.debug(
                    f"ERDB episode artwork verified: S{int(season)}E{int(episode)} "
                    f"mode={mode} posters={p_on} thumbnails={t_on}"
                )

    def _erdb_artwork_available(self, erdb, url, label):
        if not url:
            return False
        validator = getattr(erdb, "validate_artwork_url", None)
        if not callable(validator):
            return True
        if validator(url):
            return True
        reason = getattr(erdb, "last_validation_error", None) or "not an image response"
        logger.warning(
            f"ERDB {label} artwork rejected ({reason}); "
            "falling back to legacy artwork. Check your ERDB Token and toggles."
        )
        return False

    def _refresh_rpc_artwork(self, status):
        meta = self.last_meta or {}
        self.last_content_image_url = meta.get("image_url") or self.last_content_image_url or self.last_image_url
        tv_id = meta.get("id")
        media_type = meta.get("type")
        season = status.get("season")
        episode = status.get("episode")
        mode = self.config.get("rpc_large_image_mode", "season")
        provider = self._artwork_provider()
        top_posters_key = (
            self.config.get("top_posters_enabled"),
            self.config.get("top_posters_api_key"),
            self.config.get("top_posters_base_url"),
            self.config.get("top_posters_badge_size"),
            self.config.get("top_posters_badge_position"),
            self.config.get("top_posters_blur"),
            self.config.get("top_posters_style"),
            self.config.get("top_posters_season_mask_threshold"),
        )
        erdb_key = (
            self.config.get("erdb_token"),
            self.config.get("erdb_base_url"),
            self.config.get("erdb_posters_enabled"),
            self.config.get("erdb_backdrops_enabled"),
            self.config.get("erdb_thumbnails_enabled"),
        )
        artwork_key = (mode, tv_id, self.last_imdb_id, season, episode, provider, top_posters_key, erdb_key)
        meta_key = (tv_id, media_type, self.config.get("rpc_buttons_enabled", True))

        if meta_key != self.last_rpc_meta_key:
            self.last_rpc_meta_key = meta_key
            self.last_network_image_url = None
            self.last_network_name = None
            self.last_network_gif_url = None
            self.last_network_gif_name = None
            self.last_tmdb_url = None
            self.last_trailer_url = None
            self.last_full_details = None

            if tv_id and media_type in ("tv", "movie"):
                self.last_tmdb_url = f"https://www.themoviedb.org/{media_type}/{tv_id}"
                full_details = self.tmdb.get_full_details(tv_id, media_type)
                if full_details:
                    self.last_full_details = full_details
                    self.last_network_image_url = full_details.get("network_logo")
                    self.last_network_name = full_details.get("network_name")
                    if not self.last_imdb_id:
                        self.last_imdb_id = full_details.get("imdb_id")
                if self.config.get("rpc_buttons_enabled", True):
                    self.last_trailer_url = self.tmdb.get_content_trailer(tv_id, media_type)

        if artwork_key != self.last_artwork_key:
            self.last_artwork_key = artwork_key
            self.last_episode_image_url = None
            self.last_season_image_url = None
            self.last_top_posters_show_url = None
            self.last_top_posters_season_url = None
            self.last_top_posters_episode_url = None
            self.last_erdb_show_url = None
            self.last_erdb_backdrop_url = None
            self.last_erdb_episode_url = None

            if tv_id:
                if media_type == "tv" and season is not None:
                    # ALWAYS fetch episode details if we have an episode number, to populate the title
                    if episode is not None:
                        episode_details = self.tmdb.get_episode_details(tv_id, int(season), int(episode))
                        if episode_details:
                            self.last_episode_details = episode_details
                            if mode == "episode":
                                self.last_episode_image_url = episode_details.get("image_url")
                            
                            if episode_details.get("name"):
                                self.last_episode_title = episode_details.get("name")
                                status["episode_title"] = self.last_episode_title
                                
                            runtime_ms = episode_details.get("runtime_ms")
                            if runtime_ms and int(status.get("duration") or 0) <= 0:
                                status["duration"] = runtime_ms
                                self._sync_wako_progress(status.get("position") or 0, runtime_ms)
                    else:
                        self.last_episode_title = None

                elif media_type == "movie":
                    # Fallback for movies without duration (e.g. Just Player)
                    if int(status.get("duration") or 0) <= 0:
                        full_details = self.tmdb.get_full_details(tv_id, "movie")
                        if full_details and full_details.get("runtime"):
                            runtime_ms = full_details["runtime"] * 60 * 1000
                            status["duration"] = runtime_ms
                            self._sync_wako_progress(status.get("position") or 0, runtime_ms)

                if media_type == "tv" and season is not None and mode in ("episode", "season"):
                    season_details = self.tmdb.get_season_details(tv_id, int(season))
                    if season_details:
                        self.last_season_image_url = season_details.get("image_url")
            elif media_type == "tv" and self.last_imdb_id and season is not None and episode is not None:
                episode_details = self.tmdb.get_cinemeta_episode_details(self.last_imdb_id, int(season), int(episode))
                if episode_details:
                    self.last_episode_details = episode_details
                    if mode == "episode":
                        self.last_episode_image_url = episode_details.get("image_url")
                    if episode_details.get("name"):
                        self.last_episode_title = episode_details.get("name")
                        status["episode_title"] = self.last_episode_title
                    runtime_ms = episode_details.get("runtime_ms")
                    if runtime_ms and int(status.get("duration") or 0) <= 0:
                        status["duration"] = runtime_ms
                        self._sync_wako_progress(status.get("position") or 0, runtime_ms)

            # Refresh all providers in the chain that are enabled
            chain = self.config.get("artwork_fallback_chain", ["top_posters", "erdb", "tmdb"])
            for p in chain:
                if p == "top_posters":
                    self._refresh_top_posters_artwork(mode, tv_id, media_type, season, episode)
                elif p == "erdb":
                    self._refresh_erdb_artwork(mode, media_type, season, episode)

        else:
            # Re-populate from cache if key hasn't changed
            if self.last_episode_title:
                status["episode_title"] = self.last_episode_title

        self.last_image_url = self._best_rpc_image_url()
        return self.last_image_url

    def _build_rpc_payload(self, clean_title, status, app_pkg):
        app_pkg = self._display_app_name(app_pkg)
        state = status.get("state", "stopped")
        position = int(status.get("position") or 0)
        duration = int(status.get("duration") or 0)
        episode_label = self._episode_label(status)
        
        # 1. Details: [Show Name] (on Stremio / on Wako)
        clean_title = self._clean_title_for_rpc(clean_title)
        
        # Expert Branding: Match Wako's look
        is_wako_active = self.config.get("wako_mode", False) and app_pkg == "Wako"
        custom_branding = self.config.get("rpc_branding", "on Stremio")
        branding = "(on Wako)" if is_wako_active else f"({custom_branding})"
        
        details = f"{clean_title} {branding}" if clean_title else f"Content {branding}"
        
        # 2. State: [Episode Label] or Status
        state_text = episode_label
        if not state_text:
            state_text = "Paused" if state == "paused" else "Connected"
            
        # 3. Small Image & Hover: [Action] on [Device]
        if self._is_local_stremio_app(app_pkg):
            import platform
            win_ver = platform.release()
            device_name = f"Windows {win_ver}" if win_ver in ("10", "11") else "PC"
        else:
            device_name = getattr(self, "device_name", None) or self.shared_state.get("device") or "Android TV"
            device_name = self._normalize_device_name(device_name)
        
        small_image, _ = self._small_rpc_art(state, app_pkg)
        action = "Paused on" if state == "paused" else "Watching on"
        small_text = f"{action} {device_name}"
        small_mode = self.config.get("rpc_small_icon_mode", "play_status")

        # STABLE PREMIUM: Standard Mode + Faked Watching Label
        # We use activity_type: None for 100% stability with custom proxied images.
        
        # 1. Restore Shielded Proxy for Uncropped Aspect Ratio
        large_image_url = self._best_rpc_image_url()
        
        # We strictly prioritize the network logo (e.g. Netflix, HBO) over the poster.
        # We use a slim 128x128 proxy with fit=contain for that perfect circle look.
        
        # Priority 1: Official Network Logo (e.g. HBO, Netflix) from metadata
        # Priority 2: Secondary fallback from shared state
        # Priority 3: Small app icon (Stremio/Wako logo)
        if small_mode == "content_network_gif":
            raw_small_url = small_image
        else:
            raw_small_url = getattr(self, "last_network_image_url", None) or self.shared_state.get("image_url_fallback")
        
        # Aggressive Poster Filter: If the URL is just a main poster (w780/original), block it for the small icon
        if not raw_small_url or any(x in str(raw_small_url) for x in ["t/p/w780", "t/p/original", "t/p/w500"]):
            raw_small_url = small_image
        
        # DEBUG: CLEAN UP PREVIOUS PROXY IF PRESENT (Prevent Double Proxy)
        if raw_small_url and "wsrv.nl" in str(raw_small_url) and "url=" in str(raw_small_url):
            try:
                raw_small_url = raw_small_url.split("url=")[1].split("&")[0]
                if raw_small_url.startswith("base64:"):
                    import base64
                    raw_small_url = base64.b64decode(raw_small_url.replace("base64:", "")).decode()
                else:
                    raw_small_url = urllib.parse.unquote(raw_small_url)
            except: pass
        
        if raw_small_url and str(raw_small_url).startswith("http") and STREMIO_LOGO_URL not in str(raw_small_url):
            direct_small_image = self._wsrv_small_rpc_image(
                raw_small_url,
                animated=small_mode == "content_network_gif" and str(raw_small_url).lower().split("?")[0].endswith(".gif"),
            )
            if not direct_small_image:
                self._log_small_icon_debug(
                    f"proxy failed mode={small_mode} raw_len={len(str(raw_small_url))} "
                    f"network={self.last_network_name!r}; falling back to app asset"
                )
                direct_small_image = STREMIO_LOGO_URL
        else:
            if raw_small_url and raw_small_url != STREMIO_LOGO_URL:
                direct_small_image = raw_small_url
            else:
                self._log_small_icon_debug(
                    f"no http small image mode={small_mode} raw={raw_small_url!r} "
                    f"network_url={self.last_network_image_url!r} fallback={self.shared_state.get('image_url_fallback')!r}"
                )
                direct_small_image = STREMIO_LOGO_URL

        self._log_small_icon_debug(
            f"final mode={small_mode} raw_len={len(str(raw_small_url or ''))} "
            f"final={direct_small_image if direct_small_image == STREMIO_LOGO_URL else str(direct_small_image)[:180]} "
            f"final_len={len(str(direct_small_image or ''))}"
        )

        # 3. Use clean details only.
        # Discord's activity_type provides the "Watching" label.
        display_details = re.sub(
            r'^\s*(?:watching|playing|paused)\s+',
            '',
            details,
            flags=re.I
        ).strip()

        payload = {
            "details": display_details,
            "state": state_text,
            "image_url": large_image_url,
            "large_text": self._player_label(clean_title, app_pkg),
            "small_image": direct_small_image,
            "small_text": small_text,
            "activity_type": ActivityType.WATCHING, 
        }
        buttons = self._rpc_buttons()
        if buttons:
            payload["buttons"] = buttons

        payload.update(self._rpc_timestamps(clean_title, status, app_pkg))
        return payload

    def _update_rpc(self, clean_title, status, app_pkg, is_wako):
        app_pkg = self._display_app_name(app_pkg)
        client_id = self._select_discord_client_id(is_wako=is_wako)
        if not client_id:
            return
        if self.rpc.client_id != client_id:
            self.rpc.reconnect_with_id(client_id)
        elif not self.rpc.connected:
            self.rpc.connect()
        if (
            is_wako
            and status.get("state") == "playing"
            and int(status.get("duration") or 0) <= 0
            and self._should_log_wako_missing_duration(clean_title, status)
        ):
            logger.debug("RPC: Wako playing without duration; Discord progress bar is unavailable until progress is detected.")
        self._enforce_authoritative_timing(status)
        payload = self._build_rpc_payload(clean_title, status, app_pkg)
        self._debug_playback_timing(status.get("_debug_reason", "rpc"), status, payload)
        self.rpc.update(**payload)

    def _reset_wako_cache(self):
        self.wako_cached_title = None
        self.wako_cached_season = None
        self.wako_cached_episode = None
        self.wako_cached_ep_title = None
        self.wako_cached_position = None
        self.wako_cached_duration = None
        self.wako_progress_anchor_time = None
        self.last_heist_position = 0

    def _apply_cached_wako_metadata(self, status):
        if not self.wako_cached_title:
            return None
        status["season"] = self.wako_cached_season
        status["episode"] = self.wako_cached_episode
        if self.wako_cached_ep_title:
            status["ep_title"] = self.wako_cached_ep_title
        self._apply_wako_progress_cache(status, status.get("state", "playing"))
        return self.wako_cached_title

    def _wako_cache_looks_stale_for_next_episode(self, status, state):
        if not self.wako_cached_title or state not in ("playing", "paused"):
            return False
        if self.wako_cached_position is None or not self.wako_cached_duration:
            return False
        if not self._status_has_valid_progress(status):
            return False

        try:
            current_position = int(status.get("position") or 0)
            current_duration = int(status.get("duration") or 0)
            cached_position = int(self.wako_cached_position or 0)
            cached_duration = int(self.wako_cached_duration or 0)
        except (TypeError, ValueError):
            return False

        if cached_duration <= 0:
            return False
        if state == "playing" and self.wako_progress_anchor_time is not None:
            cached_position += max(0, int((time.time() - self.wako_progress_anchor_time) * 1000))
        cached_position = min(cached_position, cached_duration)

        near_previous_end = cached_position >= max(int(cached_duration * 0.70), cached_duration - 10 * 60 * 1000)
        near_new_start = current_position <= min(10 * 60 * 1000, max(90 * 1000, int((current_duration or cached_duration) * 0.25)))
        big_reset = cached_position - current_position >= 8 * 60 * 1000
        duration_changed = current_duration > 0 and abs(current_duration - cached_duration) >= 60 * 1000
        return near_previous_end and near_new_start and (big_reset or duration_changed)

    def _apply_wako_heist(self, status, title, state, app_pkg, position):
        if not self.config.get("wako_mode", False):
            return title, status, state

        focus = status.get("focus", "")
        app_pkg = self._display_app_name(app_pkg)
        is_wako_focus = app_pkg == "Wako" or "app.wako" in focus
        if not is_wako_focus or state == "stopped":
            return title, status, state

        if self._wako_cache_looks_stale_for_next_episode(status, state):
            logger.info(
                "Wako Heist DEBUG: cached episode looks stale after playback reset; "
                f"cached=S{self.wako_cached_season}E{self.wako_cached_episode} "
                f"cached_pos={self.wako_cached_position}/{self.wako_cached_duration} "
                f"player_pos={status.get('position')}/{status.get('duration')}; forcing fresh heist"
            )
            self._reset_wako_cache()

        self._apply_wako_progress_cache(status, state)
        cached_title = self._apply_cached_wako_metadata(status)
        
        if cached_title:
            # If we have a cached title, we must check if it's a "generic" one (like 'Wako')
            # If it is generic, we fall through to allow the heist to try and find a real title.
            generic_cached = str(cached_title).strip().lower() in {"wako", "app.wako"}
            
            if not generic_cached:
                # If stay-awake is on and we are paused, return the cache without further ADB poking.
                # This is the "Safe Zone" that prevents accidental back-outs during long pauses.
                if state == "paused" and self.config.get("wako_stay_awake_on_pause", False):
                    return cached_title, status, "paused"
                
                return cached_title, status, "playing" if state in ("playing", "paused") else state

        # No cache? We MUST grab metadata even if paused.
        generic_title = not title or str(title).strip().lower() in {"wako", "app.wako"}
        if state != "playing" and not generic_title:
            return title, status, state

        lite_started = time.monotonic()
        lite = self.controller.execute_wako_lite_heist()
        lite_ms = int((time.monotonic() - lite_started) * 1000)
        player_detected = lite.get("state") == "playing_detected"
        
        # If the local API says we are playing/paused but controls aren't visible, we must wake it!
        can_wake_hidden_player = state in ("playing", "paused")
        if not player_detected and not can_wake_hidden_player:
            return title, status, state

        reason = "hidden_player_shell" if can_wake_hidden_player and not player_detected else "player_ui"
        logger.info(
            f"Wako Heist DEBUG: trigger state={state} title={title} reason={reason} "
            f"lite_ms={lite_ms} player_detected={player_detected} "
            f"lite_xml_len={len(lite.get('xml_data') or '')}"
        )
        full_started = time.monotonic()
        full_heist = self.controller.execute_wako_heist(
            needs_wake=True, # Always permit waking if Attempt 1 fails
            xml_data=lite.get("xml_data") if player_detected else None
        )
        full_ms = int((time.monotonic() - full_started) * 1000)
        if not full_heist.get("title"):
            logger.info(f"Wako Heist DEBUG: app_result empty full_ms={full_ms}")
            return title, status, state
        logger.info(f"Wako Heist DEBUG: app_result success full_ms={full_ms} title={full_heist.get('title')} s={full_heist.get('season')} e={full_heist.get('episode')}")

        self.wako_cached_title = full_heist["title"]
        self.wako_cached_season = full_heist.get("season")
        self.wako_cached_episode = full_heist.get("episode")
        self.wako_cached_ep_title = full_heist.get("ep_title")
        self.last_heist_position = position
        status["season"] = self.wako_cached_season
        status["episode"] = self.wako_cached_episode
        if self.wako_cached_ep_title:
            status["ep_title"] = self.wako_cached_ep_title
        # AGGRESSIVE WAKO DURATION LOCK: Always prefer UI Heist duration if available
        heist_pos = full_heist.get("position")
        heist_dur = full_heist.get("duration")
        
        if heist_pos is not None:
            status["position"] = heist_pos
        if heist_dur is not None and int(heist_dur) > 0:
            status["duration"] = heist_dur
        self._apply_wako_progress_cache(status, "playing")
        return self.wako_cached_title, status, "playing"

    def _update_api_status(self):
        self.shared_state["api_status"] = {
            "discord": bool(getattr(self.rpc, "connected", False)),
            "trakt": bool(getattr(self.trakt, "access_token", None)),
            "adb": bool(getattr(self.controller, "connected", False)),
            "metadata": bool(self.tmdb_key or self.config.get("mal_client_id")),
        }

    def _handle_stopped_state(self):
        if self.config.get("wako_mode", False):
            self._reset_wako_cache()
        if self.rpc.connected:
            self.rpc.clear()
        self.shared_state.update({
            "title": "Ready to Play",
            "subtitle": "Waiting for media...",
            "progress": 0,
            "is_playing": False,
            "position": 0,
            "duration": 0,
            "image_url": None,
            "image_url_fallback": None,
            "next_skip": None,
            "app": None,
            "focus": "",
            "connected": True,
            "device": self.device_name,
        })
        self.last_item = None
        self._reset_rpc_timeline()

    def _monitor_sleep_time(self, state):
        if state == "paused":
            return 2.0
        if state == "playing":
            return 1.0
        return 2.0

    def _monitor_loop(self):
        while self.running:
            try:
                if not self.controller.connected and not self.config.get("stremio_desktop_enabled", False):
                    self._handle_adb_offline()
                    time.sleep(5)
                    continue

                # 0.5 STAY AWAKE NUDGE (Pre-emptive Anti-Idle)
                # Must fire BEFORE screensaver guard — once screensaver activates, guard freezes everything.
                # Only nudge when last known state was paused (avoid pausing playing video).
                is_wako_active = self.config.get("wako_mode", False) and "app.wako" in self.shared_state.get("focus", "").lower()
                
                if (self.config.get("wako_stay_awake_on_pause", False)
                        and self.controller.connected
                        and not self.shared_state.get("is_playing", False)):
                    now = time.time()
                    if now - self.last_nudge_time > 60:  # Every 60s to beat most screensaver timeouts
                        self.last_nudge_time = now
                        try:
                            self.controller.send_key(224)  # KEYCODE_WAKEUP — resets idle timer, no media side-effects
                            logger.debug("Wako Stay Awake: Sent WAKEUP nudge to reset OS idle timer.")
                        except Exception:
                            pass

                # 0.6 STAY FOCUS (Focus Lock)
                # If Wako is supposed to be active but focus is lost, bring it back.
                if (self.config.get("wako_focus_lock", False) 
                        and self.controller.connected 
                        and self.shared_state.get("is_playing", False)
                        and not is_wako_active):
                    now = time.time()
                    if now - getattr(self, "last_focus_lock_time", 0) > 10: # Don't spam, 10s cooldown
                        self.last_focus_lock_time = now
                        logger.info("Wako Focus Lock: Focus lost while playing! Re-launching Wako...")
                        try:
                            self.controller.device.shell("monkey -p app.wako -c android.intent.category.LAUNCHER 1")
                        except: pass

                # 1. SCREENSAVER GUARD
                if self.controller.is_screensaver_active():
                    if not self.is_screensaver:
                        print("INFO: Screensaver Detected - Freezing RPC logic.")
                        self.is_screensaver = True
                        self.rpc.close()
                        self.shared_state["is_playing"] = False
                        self.shared_state["title"] = "Screensaver Active"
                    time.sleep(5)
                    continue
                else:
                    self.is_screensaver = False

                # 2. GET STATUS
                desktop_status = {"active": False}
                _desktop_enabled = self.config.get("stremio_desktop_enabled", False)
                _desktop_watcher = self.stremio_desktop
                if _desktop_enabled and _desktop_watcher:
                    try:
                        desktop_status = _desktop_watcher.get_state()
                        if not getattr(self, '_desktop_debug_logged', False):
                            logger.info(f"Stremio Desktop: enabled={_desktop_enabled} watcher={_desktop_watcher is not None} state={desktop_status}")
                            self._desktop_debug_logged = True
                        if desktop_status.get("active"):
                            logger.info(f"Stremio Desktop ACTIVE: {desktop_status.get('title')} S{desktop_status.get('season')}E{desktop_status.get('episode')} - {desktop_status.get('episode_title')}")
                    except Exception as e:
                        logger.warning(f"Stremio Desktop watcher error: {e}")
                elif _desktop_enabled and not _desktop_watcher:
                    if not getattr(self, '_desktop_missing_logged', False):
                        logger.warning("Stremio Desktop Mode is ON but watcher failed to initialize (missing psutil/pygetwindow?)")
                        self._desktop_missing_logged = True
                
                is_wako = False
                if desktop_status.get("active"):
                    status = desktop_status
                    # Ensure compatibility with existing loop fields
                    # status["state"] is already set to "playing" or "paused" by get_state()
                    status["focus"] = status.get("focus") or "Stremio"
                    status["app"] = status.get("app") or "Stremio Desktop"
                else:
                    # Fallback to ADB
                    if not self.controller.connected:
                        self._handle_adb_offline()
                        time.sleep(2)
                        continue
                    
                    is_wako = self.config.get("wako_mode", False)
                    status = self.controller.get_playback_status(wako_mode=is_wako)
                
                title = self._normalize_display_text(status.get("title"))
                state = status.get("state", "stopped")
                position = status.get("position", 0)
                duration = status.get("duration", 0)
                app_pkg = self._display_app_name(status.get("app"))
                self.shared_state["app"] = app_pkg
                self.shared_state["focus"] = status.get("focus", "")

                # 3. STOP DEBOUNCE (SINGULARITY HARDENING)
                if state == "stopped":
                    self.stop_counter += 1
                    if self.stop_counter < 3:
                        self._update_api_status()
                        time.sleep(2)
                        continue
                    self._handle_stopped_state()
                    self.stop_counter = 0
                    self._update_api_status()
                    time.sleep(2)
                    continue
                else:
                    self.stop_counter = 0

                # 4. WAKO HEIST (player-only with cache)
                title, status, state = self._apply_wako_heist(status, title, state, app_pkg, position)
                self._enforce_authoritative_timing(status)
                title = self._normalize_display_text(title)
                app_pkg = self._display_app_name(app_pkg)
                position = int(status.get("position") or 0)
                duration = int(status.get("duration") or 0)

                # 5. METADATA & RPC UPDATE
                if title:
                    clean_title, resolved_title = self._prepare_metadata_lookup(title, status, is_wako=is_wako)
                    meta = self.last_meta
                    if clean_title and clean_title != self.last_item:
                        # New Item - Refresh Metadata
                        self.last_item = clean_title
                        self.last_imdb_id = None
                        self.last_image_url = None
                        self.last_content_image_url = None
                        self.last_season_image_url = None
                        self.last_episode_image_url = None
                        self.last_top_posters_show_url = None
                        self.last_top_posters_season_url = None
                        self.last_top_posters_episode_url = None
                        self.last_artwork_key = None
                        self.last_rpc_meta_key = None
                        self.last_network_image_url = None
                        self.last_network_name = None
                        self.last_network_gif_url = None
                        self.last_network_gif_name = None
                        self.last_tmdb_url = None
                        self.last_trailer_url = None
                        self.last_episode_details = None
                        self._reset_rpc_timeline()
                        meta = None
                        # Only search TMDB if it's not our placeholder
                        if "[" not in clean_title:
                            media_type_hint = getattr(resolved_title, "media_type_hint", None)
                            year_hint = getattr(resolved_title, "year", None)
                            meta = self.tmdb.search_content(clean_title, media_type_hint=media_type_hint, year=year_hint)
                            self.last_meta = meta
                        if meta:
                            self.last_content_image_url = meta.get("image_url")
                            self.last_image_url = self.last_content_image_url
                            self.last_imdb_id = meta.get("imdb_id")
                        
                        # Fetch Skips
                        if self.last_imdb_id:
                            is_movie = (meta.get("type") == "movie")
                            self.skip_manager.get_skip_times(
                                self.last_imdb_id, 
                                status.get("season", 0), 
                                status.get("episode", 0),
                                title=clean_title,
                                is_movie=is_movie
                            )
                    
                    # Periodic Trakt Scrobble (Every 15 mins or significant progress)
                    now = time.time()
                    if state == "playing" and (now - self.last_trakt_sync > 900):
                        if self.last_imdb_id:
                            m_type = meta.get("type") if 'meta' in locals() else "movie"
                            # Trakt API uses 'episode' for TV shows
                            trakt_type = "episode" if m_type == "tv" else m_type
                            media_data = {trakt_type: {"ids": {"imdb": self.last_imdb_id}}}
                            self.trakt.scrobble("start", media_data, progress=(position/duration*100) if duration else 0)
                        self.last_trakt_sync = now

                    # Update Shared State
                    self._refresh_rpc_artwork(status)
                    position = int(status.get("position") or 0)
                    duration = int(status.get("duration") or 0)
                    subtitle = self._episode_label(status) or ("Playing" if state == "playing" else "Paused")
                    # Hardened Duration Fallback for Dashboard (if not already set by metadata lookup)
                    if int(duration or 0) <= 0 and self.last_imdb_id:
                        # Re-check metadata if duration is still 0
                        if meta and meta.get("runtime"):
                            duration = meta.get("runtime") * 60 * 1000
                        elif hasattr(self, "last_episode_details") and self.last_episode_details.get("runtime_ms"):
                            duration = self.last_episode_details.get("runtime_ms")
                    if duration and int(duration) > 0:
                        status["duration"] = int(duration)

                    self.shared_state["title"] = clean_title
                    self.shared_state["subtitle"] = subtitle
                    self.shared_state["is_playing"] = (state == "playing")
                    self.shared_state["position"] = position
                    self.shared_state["duration"] = duration
                    self.shared_state["progress"] = position / duration if (duration and duration > 0) else 0
                    self.shared_state["image_url"] = self._best_dashboard_image_url()
                    self.shared_state["image_url_fallback"] = self._dashboard_fallback_image_url()
                    raw_small_image, _ = self._small_rpc_art(state, app_pkg)
                    small_animated = str(raw_small_image).lower().split("?")[0].endswith(".gif")
                    if raw_small_image and str(raw_small_image).startswith("http"):
                        self.shared_state["dashboard_small_icon_url"] = self._wsrv_small_rpc_image(raw_small_image, animated=small_animated)
                    elif raw_small_image in (STREMIO_LOGO_URL, WAKO_LOGO_URL, "vlc_logo", "device", "play", "pause"):
                        self.shared_state["dashboard_small_icon_url"] = "/static/logo.png"
                    else:
                        self.shared_state["dashboard_small_icon_url"] = None
                    self.shared_state["meta_imdb"] = self.last_imdb_id
                    self.shared_state["meta_season"] = status.get("season")
                    self.shared_state["meta_episode"] = status.get("episode")
                    self._track_analytics_playback(clean_title, subtitle, status, app_pkg, meta if 'meta' in locals() else None)
                    
                    # 6. AUTO SKIP (SINGULARITY GRADE)
                    if state == "playing" and self.skip_manager.enabled and self.last_imdb_id:
                        is_movie = (meta.get("type") == "movie") if 'meta' in locals() else False
                        skip_times = self.skip_manager.get_skip_times(
                            self.last_imdb_id, 
                            status.get("season", 0), 
                            status.get("episode", 0),
                            title=clean_title,
                            is_movie=is_movie
                        )
                        if skip_times:
                            skip_res = self.skip_manager.should_skip(position, skip_times)
                            if skip_res:
                                target_ms, skip_type = skip_res

                                if self.config.get("skip_mode") == "manual":
                                    # Segment metadata for UI button
                                    label = "Skip Intro"
                                    for s in skip_times:
                                        if s['start'] <= position/1000.0 < s['end']:
                                            label = s['label']
                                            break
                                    self.shared_state["next_skip"] = {"target": target_ms, "label": label, "type": skip_type}
                                else:
                                    # AUTO MODE - Perform immediate skip
                                    print(f"INFO: Auto-Skipping {skip_type} -> Seeking to {target_ms}ms")
                                    saved_ms = max(0, int(target_ms or 0) - int(position or 0))
                                    try:
                                        from src.web.server import _broadcast_sse
                                        _broadcast_sse("skip", {"type": skip_type, "target_ms": target_ms, "position": position})
                                    except Exception:
                                        pass
                                    landed_ms = self.controller.seek_to(target_ms, current_ms=position)
                                    if landed_ms is None:
                                        landed_ms = target_ms
                                    landed_ms, duration = self._commit_seek_progress(landed_ms, duration, previous_position=position)
                                    status["position"] = landed_ms
                                    if duration:
                                        status["duration"] = duration
                                    position = landed_ms
                                    self.stats.increment("skips")
                                    self.analytics.add_skip_with_provider(saved_ms, "auto", skip_type)
                            else:
                                self.shared_state["next_skip"] = None
                        else:
                            self.shared_state["next_skip"] = None
                    else:
                        self.shared_state["next_skip"] = None
                else:
                    subtitle = "Playing" if state == "playing" else "Paused" if state == "paused" else "Idle"
                    self.shared_state.update({
                        "title": "",
                        "subtitle": subtitle,
                        "is_playing": (state == "playing"),
                        "position": position,
                        "duration": duration,
                        "progress": position / duration if duration else 0,
                        "image_url": "",
                        "image_url_fallback": "",
                        "next_skip": None,
                        "meta_imdb": "",
                        "meta_season": None,
                        "meta_episode": None,
                    })
                    self.last_item = None
                    self.last_imdb_id = None
                    self.last_image_url = None
                    self.last_content_image_url = None
                    self.last_season_image_url = None
                    self.last_episode_image_url = None
                    self.last_top_posters_show_url = None
                    self.last_top_posters_season_url = None
                    self.last_top_posters_episode_url = None
                    self.last_artwork_key = None
                    self.last_rpc_meta_key = None
                    self.last_network_image_url = None
                    self.last_network_name = None
                    self.last_network_gif_url = None
                    self.last_network_gif_name = None
                    self.last_tmdb_url = None
                    self.last_trailer_url = None
                    self.last_episode_details = None
                    self.last_meta = None
                    self._end_current_analytics_session(position)
                    self._reset_rpc_timeline()
                    if self.rpc.connected:
                        self.rpc.clear()

                # Update Discord
                if title:
                    self._update_rpc(clean_title, status, app_pkg, is_wako)
                    # Auto-scrobble to integrations
                    if self._integrations:
                        self._scrobble_integrations(clean_title, meta if 'meta' in dir() else None, status, state)
                else:
                    self._update_api_status()
                    time.sleep(2)
                    continue

                self._update_api_status()
                # SSE broadcast playback state
                try:
                    from src.web.server import _broadcast_sse
                    _broadcast_sse("playback", {
                        "title": self.shared_state.get("title", ""),
                        "is_playing": self.shared_state.get("is_playing", False),
                        "progress": self.shared_state.get("progress", 0),
                        "position": self.shared_state.get("position", 0),
                        "duration": self.shared_state.get("duration", 0),
                    })
                except Exception:
                    pass
                time.sleep(self._monitor_sleep_time(state))
            except Exception as e:
                import traceback
                print(f"Monitor Loop Error: {e}")
                traceback.print_exc()
                time.sleep(5)

    def perform_manual_skip(self):
        skip = self.shared_state.get("next_skip")
        if not skip: return

        target_ms = skip["target"]
        current_ms = self.shared_state.get("position", 0)

        if self.config.get("wako_mode"):
            # Wako Seeks: 15s intervals
            print(f"INFO: Manual Skip (Wako) -> Stepping to {target_ms}ms")
            # The controller.seek_to in wako mode already handles incremental seeks if we want it to,
            # but let's be explicit here or ensure controller.seek_to is robust.
            landed_ms = self.controller.seek_to(target_ms, current_ms=current_ms)
            if landed_ms is None:
                landed_ms = target_ms
            self._commit_seek_progress(landed_ms, self.shared_state.get("duration"), previous_position=current_ms)
        else:
            print(f"INFO: Manual Skip -> Direct Seek to {target_ms}ms")
            landed_ms = self.controller.seek_to(target_ms, current_ms=current_ms)
            if landed_ms is None:
                landed_ms = target_ms
            self._commit_seek_progress(landed_ms, self.shared_state.get("duration"), previous_position=current_ms)

        self.stats.increment("skips")
        self.analytics.add_skip_with_provider(max(0, int(target_ms or 0) - int(current_ms or 0)), "manual", skip.get("type", "skip"))
        self.shared_state["next_skip"] = None

    def _save_trakt_tokens(self, access_token, refresh_token):
        self.config["trakt_access_token"] = access_token
        self.config["trakt_refresh_token"] = refresh_token
        self.save_settings()
        logger.info("Trakt: Tokens saved after refresh")

    def _on_config_file_changed(self, new_config):
        old_config = self.config.copy()
        self.config.update(new_config)
        changed_keys = [k for k in new_config if new_config.get(k) != old_config.get(k)]
        if changed_keys:
            logger.info(f"Config hot-reload: {len(changed_keys)} keys changed")
            if self.audit_log:
                self.audit_log.log("config", {"action": "hot_reload", "changed_keys": changed_keys})


    def _scrobble_integrations(self, title, meta, status, state):
        """Auto-scrobble to all enabled integrations during playback."""
        if not title or state != "playing":
            return
        now = time.time()
        if now - getattr(self, '_last_integration_scrobble', 0) < 300:
            return
        self._last_integration_scrobble = now

        media_type = meta.get("type", "movie") if meta else "movie"
        season = status.get("season", 0)
        episode = status.get("episode", 0)
        position = int(status.get("position", 0))
        duration = int(status.get("duration", 0))
        progress = (position / duration * 100) if duration > 0 else 0
        image_url = self.shared_state.get("image_url", "")

        for name, client in self._integrations.items():
            try:
                if name == "anilist" and hasattr(client, 'update_progress'):
                    anime = client.search_anime(title)
                    if anime and anime.get("id"):
                        ep = int(episode) if episode else 1
                        client.update_progress(anime["id"], ep)
                        logger.debug(f"Integration: AniList progress updated for {title}")

                elif name == "simkl" and hasattr(client, 'scrobble'):
                    media_data = {}
                    if media_type == "movie":
                        media_data["movie"] = {"title": title}
                    else:
                        media_data["show"] = {"title": title}
                        if season and episode:
                            media_data["episode"] = {"season": int(season), "number": int(episode)}
                    client.scrobble(media_data, progress)
                    logger.debug(f"Integration: Simkl scrobbled {title}")

                elif name == "kitsu" and hasattr(client, 'search_anime'):
                    anime = client.search_anime(title)
                    if anime and anime.get("id"):
                        ep = int(episode) if episode else 1
                        client.update_progress(str(anime["id"]), ep)
                        logger.debug(f"Integration: Kitsu progress updated for {title}")

                elif name == "lastfm" and hasattr(client, 'update_now_playing'):
                    client.update_now_playing(artist="Soundtrack", track=title)
                    if progress > 50:
                        client.scrobble(artist="Soundtrack", track=title)
                    logger.debug(f"Integration: Last.fm now playing {title}")

                elif name == "letterboxd" and hasattr(client, 'search_film'):
                    if media_type == "movie" and progress > 80:
                        client.search_film(title)
                        logger.debug(f"Integration: Letterboxd searched {title}")

                elif name == "notion" and hasattr(client, 'create_entry'):
                    if progress > 80:
                        client.create_entry(
                            title=title, media_type=media_type,
                            season=int(season) if season else 0,
                            episode=int(episode) if episode else 0,
                            image_url=image_url
                        )
                        logger.debug(f"Integration: Notion entry for {title}")

                elif name == "obsidian" and hasattr(client, 'create_entry'):
                    if progress > 80:
                        client.create_entry(
                            title=title, media_type=media_type,
                            season=int(season) if season else 0,
                            episode=int(episode) if episode else 0,
                            image_url=image_url
                        )
                        logger.debug(f"Integration: Obsidian entry for {title}")

            except Exception as e:
                logger.error(f"Integration {name} scrobble error: {e}")

        # Trakt collection sync
        if self.config.get("trakt_collection_sync") and self.last_imdb_id and progress > 80:
            try:
                m_type = meta.get("type") if meta else "movie"
                trakt_type = "episode" if m_type == "tv" else "movie"
                media_data = {trakt_type: {"ids": {"imdb": self.last_imdb_id}}}
                self.trakt.add_to_collection(media_data)
                logger.debug(f"Trakt: Added {title} to collection")
            except Exception as e:
                logger.error(f"Trakt collection sync error: {e}")

    def _init_integrations(self):
        """Initialize enabled API integrations in background."""
        try:
            if self.config.get("anilist_enabled") and self.config.get("anilist_access_token"):
                from src.core.integrations.anilist import AniListClient
                self._integrations["anilist"] = AniListClient(
                    access_token=self.config["anilist_access_token"]
                )
                logger.info("Integration: AniList initialized")

            if self.config.get("simkl_enabled") and self.config.get("simkl_client_id"):
                from src.core.integrations.simkl import SimklClient
                self._integrations["simkl"] = SimklClient(
                    client_id=self.config["simkl_client_id"],
                    access_token=self.config.get("simkl_access_token", ""),
                )
                logger.info("Integration: Simkl initialized")

            if self.config.get("kitsu_enabled") and self.config.get("kitsu_access_token"):
                from src.core.integrations.kitsu import KitsuClient
                self._integrations["kitsu"] = KitsuClient(
                    access_token=self.config["kitsu_access_token"]
                )
                logger.info("Integration: Kitsu initialized")

            if self.config.get("lastfm_enabled") and self.config.get("lastfm_api_key"):
                from src.core.integrations.lastfm import LastFMClient
                self._integrations["lastfm"] = LastFMClient(
                    api_key=self.config["lastfm_api_key"],
                    api_secret=self.config.get("lastfm_api_secret", ""),
                    session_key=self.config.get("lastfm_session_key", ""),
                )
                logger.info("Integration: Last.fm initialized")

            if self.config.get("plex_enabled") and self.config.get("plex_url"):
                from src.core.integrations.media_server import PlexClient
                self._integrations["plex"] = PlexClient(
                    url=self.config["plex_url"],
                    token=self.config.get("plex_token", ""),
                )
                logger.info("Integration: Plex initialized")

            if self.config.get("jellyfin_enabled") and self.config.get("jellyfin_url"):
                from src.core.integrations.media_server import JellyfinClient
                self._integrations["jellyfin"] = JellyfinClient(
                    url=self.config["jellyfin_url"],
                    api_key=self.config.get("jellyfin_api_key", ""),
                )
                logger.info("Integration: Jellyfin initialized")

            if self.config.get("notion_enabled") and self.config.get("notion_api_key"):
                from src.core.integrations.notion_obsidian import NotionWatchLog
                self._integrations["notion"] = NotionWatchLog(
                    api_key=self.config["notion_api_key"],
                    database_id=self.config.get("notion_database_id", ""),
                )
                logger.info("Integration: Notion initialized")

            if self.config.get("obsidian_enabled") and self.config.get("obsidian_vault_path"):
                from src.core.integrations.notion_obsidian import ObsidianWatchLog
                self._integrations["obsidian"] = ObsidianWatchLog(
                    vault_path=self.config["obsidian_vault_path"]
                )
                logger.info("Integration: Obsidian initialized")

            if self.config.get("emby_enabled") and self.config.get("emby_url"):
                from src.core.integrations.media_server import JellyfinClient
                self._integrations["emby"] = JellyfinClient(
                    url=self.config["emby_url"],
                    api_key=self.config.get("emby_api_key", ""),
                    server_type="emby",
                )
                logger.info("Integration: Emby initialized")

            if self.config.get("fanart_enabled") and self.config.get("fanart_api_key"):
                from src.core.integrations.fanart import FanArtClient
                self._integrations["fanart"] = FanArtClient(
                    api_key=self.config["fanart_api_key"]
                )
                logger.info("Integration: FanArt.tv initialized")

            if self.config.get("opensubtitles_enabled") and self.config.get("opensubtitles_api_key"):
                from src.core.integrations.opensubtitles import OpenSubtitlesClient
                self._integrations["opensubtitles"] = OpenSubtitlesClient(
                    api_key=self.config["opensubtitles_api_key"],
                    username=self.config.get("opensubtitles_username", ""),
                    password=self.config.get("opensubtitles_password", ""),
                )
                logger.info("Integration: OpenSubtitles initialized")

            if self.config.get("justwatch_enabled"):
                from src.core.integrations.justwatch import JustWatchClient
                self._integrations["justwatch"] = JustWatchClient(
                    country=self.config.get("justwatch_country", "US")
                )
                logger.info("Integration: JustWatch initialized")

            if self.config.get("letterboxd_enabled") and self.config.get("letterboxd_api_key"):
                from src.core.integrations.letterboxd import LetterboxdClient
                self._integrations["letterboxd"] = LetterboxdClient(
                    api_key=self.config["letterboxd_api_key"],
                    api_secret=self.config.get("letterboxd_api_secret", ""),
                )
                logger.info("Integration: Letterboxd initialized")

        except Exception as e:
            logger.error(f"Integration init error: {e}")

    def _apply_privacy_mode(self, title, subtitle):
        """Apply privacy mode to hide media details."""
        if not self._privacy_mode:
            return title, subtitle
        blacklist = self.config.get("privacy_blacklist", [])
        if blacklist and title not in blacklist:
            return title, subtitle
        hidden_text = self.config.get("privacy_hidden_text", "Watching something")
        return hidden_text, ""

    def _get_cycling_status(self):
        """Get the current cycling status message."""
        messages = self.config.get("rpc_cycling_messages", [])
        if not messages:
            return None
        interval = self.config.get("rpc_cycling_interval", 30)
        now = time.time()
        if now - self._last_cycling_time >= interval:
            self._rpc_cycling_index = (self._rpc_cycling_index + 1) % len(messages)
            self._last_cycling_time = now
        return messages[self._rpc_cycling_index]

    def _get_dynamic_buttons(self, imdb_id=None, tmdb_id=None):
        """Generate dynamic RPC buttons based on config."""
        buttons = self.config.get("rpc_dynamic_buttons", [])
        if not buttons:
            return None
        result = []
        for btn in buttons[:2]:  # Discord max 2 buttons
            label = btn.get("label", "")
            url = btn.get("url", "")
            if imdb_id:
                url = url.replace("{imdb_id}", imdb_id)
            if tmdb_id:
                url = url.replace("{tmdb_id}", str(tmdb_id))
            if label and url:
                result.append({"label": label[:32], "url": url})
        return result if result else None

    def save_settings(self): save_config(self.config)
    def update_config(self, k, v):
        self.config[k] = v
        self.save_settings()
        if k in ("adb_host", "adb_port"):
            self.controller.host = self.config.get("adb_host", "")
            self.controller.port = int(self.config.get("adb_port", 5555) or 5555)
        if k == "playback_logcat_enabled":
            self.controller.playback_logcat_enabled = bool(v)
            if v:
                self.controller.start_playback_logcat_watcher()
            else:
                self.controller.stop_playback_logcat_watcher()
        # Direct push to managers
        if k == "skip_priority_order": self.skip_manager.skip_priority_order = v
        if k == "notscare_major_enabled": self.skip_manager.notscare_major_enabled = v
        if k == "notscare_minor_enabled": self.skip_manager.notscare_minor_enabled = v
        if k == "tmdb_api_key": self.tmdb.api_key = v
        if (k == "artwork_provider" or k.startswith("top_posters_")) and hasattr(self, "top_posters"):
            self.top_posters.update_config(self.config)
            self.last_artwork_key = None
        if (k == "artwork_provider" or k.startswith("erdb_")) and hasattr(self, "erdb"):
            self.erdb.update_config(self.config)
            self.last_artwork_key = None
        if k.startswith("nuvio_covers_") and hasattr(self, "nuvio_covers"):
            self.nuvio_covers = NuvioCoversClient(
                self.config.get("nuvio_covers_base_url", "https://nuvioapp.space"),
                self.config.get("nuvio_covers_token", ""),
                self.config.get("nuvio_covers_email", ""),
                self.config.get("nuvio_covers_password", ""),
                on_token_refresh=self._save_nuvio_token,
            )
            self.last_network_gif_url = None
            self.last_network_gif_name = None

    # --- Commands ---
    def play_pause(self): self.controller.play_pause()
    def stop_playback(self): self.controller.stop()
    def next_track(self): self.controller.next_track()
    def prev_track(self): self.controller.prev_track()
    def seek_to(self, ms):
        current = int(self.shared_state.get("position", 0) or 0)
        landed_ms = self.controller.seek_to(ms, current_ms=current)
        if landed_ms is None:
            landed_ms = ms
        self._commit_seek_progress(landed_ms, self.shared_state.get("duration"), previous_position=current)

    def seek_forward(self):
        current = int(self.shared_state.get("position", 0) or 0)
        target = current + 30000
        landed_ms = self.controller.seek_to(target, current_ms=current)
        if landed_ms is None:
            landed_ms = target
        self._commit_seek_progress(landed_ms, self.shared_state.get("duration"), previous_position=current)

    def seek_backward(self):
        current = int(self.shared_state.get("position", 0) or 0)
        target = max(0, current - 30000)
        landed_ms = self.controller.seek_to(target, current_ms=current)
        if landed_ms is None:
            landed_ms = target
        self._commit_seek_progress(landed_ms, self.shared_state.get("duration"), previous_position=current)

    def toggle_skip(self):
        self.skip_manager.enabled = not self.skip_manager.enabled
        self.config["skip_mode"] = "auto" if self.skip_manager.enabled else "off"
        self.shared_state["auto_skip"] = self.skip_manager.enabled
        if not self.skip_manager.enabled:
            self.shared_state["next_skip"] = None
        self.save_settings()

    def restart_app(self):
        try:
            if self.controller.device and self.controller.connected:
                self.controller.device.shell("am force-stop com.stremio.one")
                time.sleep(0.5)
                self.controller.device.shell("monkey -p com.stremio.one 1")
        except Exception as e:
            logger.error(f"Restart app failed: {e}")

    def scan_network(self):
        def _scan():
            try:
                results = asyncio.run(ADBDiscovery(self.config.get("adb_port", 5555)).scan_network())
                self.shared_state["scan_results"] = results
            except Exception as e:
                logger.error(f"Network scan failed: {e}")
                self.shared_state["scan_results"] = []
        threading.Thread(target=_scan, daemon=True).start()
