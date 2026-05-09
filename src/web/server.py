
from flask import Flask, render_template, jsonify, request, send_file, abort, Response, make_response
import logging
import threading
import time
import sys
import os
import json
import re
import queue
import functools
import hashlib
from datetime import datetime
from collections import defaultdict
from typing import Optional

from src.core.config import get_config_path, validate_config, export_config, import_config, DEFAULT_CONFIG

# Disable Flask Banner
import flask.cli
flask.cli.show_server_banner = lambda *args, **kwargs: None

cli = logging.getLogger('werkzeug')
cli.setLevel(logging.ERROR)
logger = logging.getLogger("stremio-rpc")

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
gui_app = None # Reference to the main GUI App instance

# --- Rate Limiting ---
_rate_limit_store = defaultdict(list)
_rate_limit_lock = threading.Lock()


def _check_rate_limit(key: str, max_calls: int = 60, period: int = 60) -> bool:
    now = time.time()
    with _rate_limit_lock:
        calls = _rate_limit_store[key]
        _rate_limit_store[key] = [t for t in calls if now - t < period]
        if len(_rate_limit_store[key]) >= max_calls:
            return False
        _rate_limit_store[key].append(now)
        return True


def rate_limit(max_calls=60, period=60):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if gui_app and not gui_app.config.get("rate_limit_enabled", True):
                return f(*args, **kwargs)
            client_ip = request.remote_addr or "unknown"
            key = f"{client_ip}:{f.__name__}"
            if not _check_rate_limit(key, max_calls, period):
                return jsonify({"error": "Rate limit exceeded"}), 429
            return f(*args, **kwargs)
        return wrapper
    return decorator


# --- Dashboard Authentication ---
def require_auth(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not gui_app:
            return f(*args, **kwargs)
        if not gui_app.config.get("dashboard_auth_enabled", False):
            return f(*args, **kwargs)
        pin = gui_app.config.get("dashboard_auth_pin", "")
        if not pin:
            return f(*args, **kwargs)
        auth_header = request.headers.get("X-Dashboard-Pin", "")
        auth_cookie = request.cookies.get("dashboard_pin", "")
        if auth_header == pin or auth_cookie == pin:
            return f(*args, **kwargs)
        if request.path == "/" or request.path.startswith("/api/auth"):
            return f(*args, **kwargs)
        return jsonify({"error": "Authentication required"}), 401
    return wrapper


# --- SSE (Server-Sent Events) ---
_sse_clients = []
_sse_lock = threading.Lock()


def _broadcast_sse(event: str, data: dict):
    msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    with _sse_lock:
        dead = []
        for q in _sse_clients:
            try:
                q.put_nowait(msg)
            except Exception:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)
skip_config_keys = {
    "skip_mode",
    "skip_tmdb_id",
    "skip_mal_id",
    "skip_priority_order",
    "tidb_api_key",
    "remote_json_url",
}

import traceback


def _safe_text(value, default=""):
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "undefined", "nan"}:
        return default
    return text

def _save_wako_map_capture(report, label=None, controller=None):
    capture_dir = os.path.join(get_config_path(), "wako_mapper")
    xml_dir = os.path.join(capture_dir, "xml")
    json_dir = os.path.join(capture_dir, "json")
    image_dir = os.path.join(capture_dir, "images")
    error_dir = os.path.join(capture_dir, "errors")
    for folder in (capture_dir, xml_dir, json_dir, image_dir, error_dir):
        os.makedirs(folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = re.sub(r"[^A-Za-z0-9_-]+", "_", (label or report.get("classification") or "screen")).strip("_")
    safe_label = safe_label[:48] or "screen"
    xml_hash = report.get("xml_hash") or "nohash"
    base_name = f"{timestamp}_{safe_label}_{xml_hash}"

    raw_xml = report.get("raw_xml") or ""
    xml_path = os.path.join(xml_dir, f"{base_name}.xml")
    json_path = os.path.join(json_dir, f"{base_name}.json")
    image_path = os.path.join(image_dir, f"{base_name}.png")
    error_path = os.path.join(error_dir, f"{base_name}.txt")
    screenshot = {"ok": False, "path": image_path, "error": "controller unavailable"}

    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(raw_xml)

    if controller and hasattr(controller, "capture_screenshot"):
        screenshot = controller.capture_screenshot(image_path)

    adb_errors = []
    if report.get("error"):
        adb_errors.append(report.get("error"))
    for attempt in report.get("dump_attempts", []) or []:
        if attempt.get("error"):
            adb_errors.append(f"{attempt.get('name')}: {attempt.get('error')}")
    if screenshot.get("error"):
        adb_errors.append(f"screenshot: {screenshot.get('error')}")

    if raw_xml and screenshot.get("ok"):
        capture_quality = "full"
    elif raw_xml:
        capture_quality = "xml_only"
    elif screenshot.get("ok"):
        capture_quality = "screenshot_only"
    else:
        capture_quality = "diagnostics_only"

    if adb_errors:
        with open(error_path, "w", encoding="utf-8") as f:
            f.write("\n".join(adb_errors))
    else:
        error_path = ""

    report_for_file = dict(report)
    report_for_file["raw_xml_path"] = xml_path
    report_for_file["screenshot"] = screenshot
    report_for_file["adb_errors"] = adb_errors
    report_for_file["capture_quality"] = capture_quality
    report_for_file["error_path"] = error_path
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_for_file, f, indent=2)

    index_record = {
        "timestamp": timestamp,
        "label": label or "",
        "classification": report.get("classification"),
        "heist_allowed": report.get("heist_allowed"),
        "xml_hash": xml_hash,
        "xml_length": report.get("xml_length"),
        "focus": report.get("focus"),
        "json_path": json_path,
        "xml_path": xml_path,
        "image_path": image_path if screenshot.get("ok") else "",
        "screenshot_ok": screenshot.get("ok", False),
        "screenshot_error": screenshot.get("error", ""),
        "capture_quality": capture_quality,
        "error_path": error_path,
        "adb_errors": adb_errors,
        "player_markers": report.get("player_markers", []),
        "blocker_markers": report.get("blocker_markers", []),
    }
    index_path = os.path.join(capture_dir, "index.jsonl")
    with open(index_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(index_record) + "\n")

    return {
        "capture_dir": capture_dir,
        "xml_dir": xml_dir,
        "json_dir": json_dir,
        "image_dir": image_dir,
        "error_dir": error_dir,
        "json_path": json_path,
        "xml_path": xml_path,
        "image_path": image_path if screenshot.get("ok") else "",
        "screenshot": screenshot,
        "capture_quality": capture_quality,
        "error_path": error_path,
        "adb_errors": adb_errors,
        "index_path": index_path,
    }

def run_server(main_app_instance):
    global gui_app
    gui_app = main_app_instance
    port = int(os.environ.get("ASCEND_PORT", gui_app.config.get("dashboard_port", 5466)))
    try:
        use_https = gui_app.config.get("dashboard_https_enabled", False)
        ssl_ctx = None
        if use_https:
            cert = gui_app.config.get("dashboard_cert_path", "")
            key = gui_app.config.get("dashboard_key_path", "")
            if cert and key and os.path.exists(cert) and os.path.exists(key):
                ssl_ctx = (cert, key)
                logger.info(f"Dashboard HTTPS enabled with cert={cert}")
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, ssl_context=ssl_ctx)
    except Exception as e:
        print(f"Web Server Failed: {e}")
        traceback.print_exc()

@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/api/state")
def get_state():
    if not gui_app: return jsonify({"error": "No App"}), 500
    
    try:
        # Read from thread-safe dict (shared_state) which app.py updates
        s = gui_app.shared_state
        return jsonify({
            # Base State
            "connected": s.get("connected", False),
            "device": _safe_text(s.get("device"), "Disconnected"),
            "title": _safe_text(s.get("title"), "Ready"),
            "subtitle": _safe_text(s.get("subtitle"), ""),
            "progress": s.get("progress", 0),
            "position": s.get("position", 0),  # Position in ms
            "duration": s.get("duration", 0),  # Duration in ms
            "image_url": _safe_text(s.get("image_url"), ""),
            "image_url_fallback": _safe_text(s.get("image_url_fallback"), ""),
            "next_skip": s.get("next_skip") or "",
            "app": _safe_text(s.get("app"), ""),
            "focus": _safe_text(s.get("focus"), ""),
            "playback_debug": s.get("playback_debug") or {},
            
            # Additional State for UI Logic
            "is_playing": s.get("is_playing", False),
            "auto_skip": gui_app.skip_manager.enabled, 
            "meta_imdb": _safe_text(s.get("meta_imdb"), ""),
            "meta_season": s.get("meta_season") if s.get("meta_season") is not None else "",
            "meta_episode": s.get("meta_episode") if s.get("meta_episode") is not None else "",
            
            # Current Configuration (for populating Settings inputs)
            "config": {
                "adb_host": gui_app.config.get("adb_host", ""),
                "dashboard_ui_mode": gui_app.config.get("dashboard_ui_mode", "normal"),
                "playback_debug_enabled": gui_app.config.get("playback_debug_enabled", False),
                "tmdb_key": gui_app.config.get("tmdb_api_key", ""),
                "mal_id": gui_app.config.get("mal_client_id", ""),
                "mal_metadata_enabled": gui_app.config.get("mal_metadata_enabled", True),
                "trakt_id": gui_app.config.get("trakt_client_id", ""),
                "trakt_secret": gui_app.config.get("trakt_client_secret", ""),
                "discord_id": gui_app.config.get("discord_client_id", ""),
                "discord_wako_id": gui_app.config.get("discord_wako_client_id", ""),
                "show_device": gui_app.config.get("show_device_name", True),
                "profanity": gui_app.config.get("profanity_filter", False),
                "aniskip_enabled": gui_app.config.get("aniskip_enabled", True),
                "aniskip_smart": gui_app.config.get("aniskip_smart", False),
                "skip_mode": gui_app.config.get("skip_mode", "auto"),
                # Skip Sources Config
                "skip_tmdb_id": gui_app.config.get("skip_tmdb_id", ""),
                "skip_mal_id": gui_app.config.get("skip_mal_id", ""),
                "introdb_enabled": gui_app.config.get("introdb_enabled", True),
                "aniskip_fallback": gui_app.config.get("aniskip_fallback", True),
                "tidb_enabled": gui_app.config.get("tidb_enabled", False),
                "tidb_api_key": gui_app.config.get("tidb_api_key", ""),
                "remote_json_enabled": gui_app.config.get("remote_json_enabled", False),
                "remote_json_url": gui_app.config.get("remote_json_url", ""),
                "videoskip_enabled": gui_app.config.get("videoskip_enabled", False),
                "notscare_major_enabled": gui_app.config.get("notscare_major_enabled", False),
                "notscare_minor_enabled": gui_app.config.get("notscare_minor_enabled", False),
                "skipme_enabled": gui_app.config.get("skipme_enabled", True),
                "skip_priority_order": gui_app.config.get("skip_priority_order", ["tidb", "introdb", "remote_json", "videoskip", "notscare_major", "notscare_minor", "aniskip", "skipme"]),
                "wako_mode": gui_app.config.get("wako_mode", False),
                "wako_player_only": gui_app.config.get("wako_player_only", False),
                "wako_stay_awake_on_pause": gui_app.config.get("wako_stay_awake_on_pause", False),
                "wako_focus_lock": gui_app.config.get("wako_focus_lock", False),
                # RPC Enhancements
                "rpc_buttons": gui_app.config.get("rpc_buttons_enabled", True),
                "rpc_streaming": gui_app.config.get("rpc_streaming_mode", True),
                "rpc_status": gui_app.config.get("rpc_custom_status", ""),
                "rpc_time": gui_app.config.get("rpc_time_display", "remaining"),
                "rpc_rating_badges": gui_app.config.get("rpc_rating_badges_enabled", False),
                "rpc_status_cycling": gui_app.config.get("rpc_status_cycling_enabled", False),
                "rpc_status_effects": gui_app.config.get("rpc_status_effects_enabled", False),
                "rpc_small_icon": gui_app.config.get("rpc_small_icon_mode", "play_status"),
                "rpc_large_image": gui_app.config.get("rpc_large_image_mode", "season"),
                "artwork_provider": gui_app.config.get("artwork_provider", "legacy"),
                "top_posters_enabled": gui_app.config.get("top_posters_enabled", False),
                "top_posters_api_key": gui_app.config.get("top_posters_api_key", ""),
                "top_posters_base_url": gui_app.config.get("top_posters_base_url", "https://api.top-streaming.stream"),
                "top_posters_badge_size": gui_app.config.get("top_posters_badge_size", "medium"),
                "top_posters_badge_position": gui_app.config.get("top_posters_badge_position", "top-right"),
                "top_posters_blur": gui_app.config.get("top_posters_blur", False),
                "top_posters_style": gui_app.config.get("top_posters_style", "modern"),
                "top_posters_season_mask_threshold": gui_app.config.get("top_posters_season_mask_threshold", 32),
                "erdb_token": gui_app.config.get("erdbToken") or gui_app.config.get("erdb_token", ""),
                "erdbToken": gui_app.config.get("erdbToken") or gui_app.config.get("erdb_token", ""),
                "erdb_base_url": gui_app.config.get("erdbBaseUrl") or gui_app.config.get("erdb_base_url", "https://easyratingsdb.com"),
                "erdbBaseUrl": gui_app.config.get("erdbBaseUrl") or gui_app.config.get("erdb_base_url", "https://easyratingsdb.com"),
                "erdb_episode_id_mode": gui_app.config.get("erdb_episode_id_mode", "realimdb"),
                "erdb_validate_remote": gui_app.config.get("erdb_validate_remote", False),
                "erdb_posters_enabled": gui_app.config.get("erdb_posters_enabled", True),
                "erdb_backdrops_enabled": gui_app.config.get("erdb_backdrops_enabled", True),
                "erdb_logos_enabled": gui_app.config.get("erdb_logos_enabled", True),
                "erdb_thumbnails_enabled": gui_app.config.get("erdb_thumbnails_enabled", True),
                "nuvio_covers_enabled": gui_app.config.get("nuvio_covers_enabled", False),
                "nuvio_covers_email": gui_app.config.get("nuvio_covers_email", ""),
                "nuvio_covers_password_saved": bool(gui_app.config.get("nuvio_covers_password", "")),
                "nuvio_covers_token": "",
                "nuvio_covers_token_saved": bool(gui_app.config.get("nuvio_covers_token", "")),
                "nuvio_covers_base_url": gui_app.config.get("nuvio_covers_base_url", "https://nuvioapp.space"),
                "nuvio_covers_orientation": gui_app.config.get("nuvio_covers_orientation", "all"),
                # Privacy & Security
                "privacy_mode": gui_app.config.get("privacy_mode", False),
                "privacy_hidden_text": gui_app.config.get("privacy_hidden_text", "Watching something"),
                "dashboard_auth_enabled": gui_app.config.get("dashboard_auth_enabled", False),
                # mDNS Discovery
                "mdns_discovery_enabled": gui_app.config.get("mdns_discovery_enabled", True),
                # New API Integrations
                "anilist_enabled": gui_app.config.get("anilist_enabled", False),
                "anilist_access_token": gui_app.config.get("anilist_access_token", ""),
                "simkl_enabled": gui_app.config.get("simkl_enabled", False),
                "simkl_client_id": gui_app.config.get("simkl_client_id", ""),
                "simkl_access_token": gui_app.config.get("simkl_access_token", ""),
                "kitsu_enabled": gui_app.config.get("kitsu_enabled", False),
                "kitsu_access_token": gui_app.config.get("kitsu_access_token", ""),
                "letterboxd_enabled": gui_app.config.get("letterboxd_enabled", False),
                "letterboxd_api_key": gui_app.config.get("letterboxd_api_key", ""),
                "letterboxd_api_secret": gui_app.config.get("letterboxd_api_secret", ""),
                "lastfm_enabled": gui_app.config.get("lastfm_enabled", False),
                "lastfm_api_key": gui_app.config.get("lastfm_api_key", ""),
                "lastfm_api_secret": gui_app.config.get("lastfm_api_secret", ""),
                "justwatch_enabled": gui_app.config.get("justwatch_enabled", False),
                "justwatch_country": gui_app.config.get("justwatch_country", "US"),
                "opensubtitles_enabled": gui_app.config.get("opensubtitles_enabled", False),
                "opensubtitles_api_key": gui_app.config.get("opensubtitles_api_key", ""),
                "opensubtitles_username": gui_app.config.get("opensubtitles_username", ""),
                "plex_enabled": gui_app.config.get("plex_enabled", False),
                "plex_url": gui_app.config.get("plex_url", ""),
                "plex_token": gui_app.config.get("plex_token", ""),
                "jellyfin_enabled": gui_app.config.get("jellyfin_enabled", False),
                "jellyfin_url": gui_app.config.get("jellyfin_url", ""),
                "jellyfin_api_key": gui_app.config.get("jellyfin_api_key", ""),
                "emby_enabled": gui_app.config.get("emby_enabled", False),
                "emby_url": gui_app.config.get("emby_url", ""),
                "emby_api_key": gui_app.config.get("emby_api_key", ""),
                "notion_enabled": gui_app.config.get("notion_enabled", False),
                "notion_api_key": gui_app.config.get("notion_api_key", ""),
                "notion_database_id": gui_app.config.get("notion_database_id", ""),
                "obsidian_enabled": gui_app.config.get("obsidian_enabled", False),
                "obsidian_vault_path": gui_app.config.get("obsidian_vault_path", ""),
                # FanArt.tv
                "fanart_enabled": gui_app.config.get("fanart_enabled", False),
                "fanart_api_key": gui_app.config.get("fanart_api_key", ""),
                # Device Health
                "device_health_enabled": gui_app.config.get("device_health_enabled", False),
                # Push Notifications
                "push_notifications_enabled": gui_app.config.get("push_notifications_enabled", False),
                # Trakt Social
                "trakt_collection_sync": gui_app.config.get("trakt_collection_sync", False),
                "trakt_social_enabled": gui_app.config.get("trakt_social_enabled", False),
                # Theme
                "theme_mode": gui_app.config.get("theme_mode", "dark"),
                "theme_accent_color": gui_app.config.get("theme_accent_color", "#8a2be2"),
                "theme_oled_black": gui_app.config.get("theme_oled_black", False),
                # Skip Category Toggles
                "skip_cat_intro": gui_app.config.get("skip_cat_intro", True),
                "skip_cat_outro": gui_app.config.get("skip_cat_outro", True),
                "skip_cat_recap": gui_app.config.get("skip_cat_recap", True),
                "skip_cat_preview": gui_app.config.get("skip_cat_preview", True),
                "skip_cat_credits": gui_app.config.get("skip_cat_credits", True),
                "skip_cat_filler": gui_app.config.get("skip_cat_filler", True),
                "skip_cat_mature": gui_app.config.get("skip_cat_mature", True),
                "skip_cat_scare": gui_app.config.get("skip_cat_scare", True),
                # Artwork Fallback Chain
                "artwork_fallback_chain": gui_app.config.get("artwork_fallback_chain", ["tmdb", "fanart", "tvdb"]),
            },
            
            # Stats (Live from StatsManager)
            "stats": {
                "skips": gui_app.stats.get("skips", 0),
                "saved": gui_app.stats.get("saved", 0),
                "syncs": gui_app.stats.get("trakt", 0)
            },

            # Skipped Catalog
            "history": gui_app.history.get_all(),

            # Debug / Metadata
            "skip_status": {
                "msg": s.get("skip_status_msg", ""),
                "color": s.get("skip_status_color", "gray")
            },
            
            # API Status for Badges
            "api_status": s.get("api_status", {
                "discord": False, 
                "trakt": False, 
                "adb": False, 
                "metadata": False
            }),
            
            # Application Logs
            "logs": s.get("logs", []),
            
            # ADB Scan Results
            "scan_results": s.get("scan_results", [])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/command/manual_skip', methods=['POST'])
def manual_skip():
    if not gui_app: return jsonify({"error": "No App"}), 500
    gui_app.perform_manual_skip()
    return jsonify({"status": "ok"})

@app.route('/api/test/skip_pipeline', methods=['POST'])
def test_skip():
    if not gui_app: return jsonify({"error": "No App"}), 500
    data = request.json
    title = data.get("title")
    s = int(data.get("season", 0))
    e = int(data.get("episode", 0))
    is_movie = data.get("is_movie", False)
    
    print(f"SANDBOX: Testing '{title}' | S:{s} E:{e} | Movie: {is_movie}")
    
    # Get TMDB metadata first for better matching
    meta = gui_app.tmdb.search_content(title)
    imdb_id = meta.get("imdb_id") if meta else None
    tmdb_id = meta.get("id") if meta else None
    
    if meta:
        print(f"SANDBOX: TMDB Match Found -> IMDB: {imdb_id}")
    else:
        print(f"SANDBOX: No TMDB match found for '{title}'")
    
    res = gui_app.skip_manager.get_skip_times(
        imdb_id, s, e, tmdb_id=tmdb_id, title=title, is_movie=is_movie, year=meta.get("year") if meta else None
    )
    
    count = len(res) if res else 0
    print(f"SANDBOX: Found {count} skip segments.")
    return jsonify({"results": res or []})

@app.route("/api/wako/map", methods=["GET", "POST"])
def map_wako_ui():
    if not gui_app:
        return jsonify({"error": "No App"}), 500
    try:
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            label = data.get("label")
        else:
            label = request.args.get("label")
            
        report = gui_app.controller.map_wako_ui()
        if label:
            report["label"] = label
        capture = _save_wako_map_capture(report, label, gui_app.controller)
        report["capture"] = capture
        gui_app.shared_state["last_wako_map"] = report
        logger.info(
            "Wako Mapper: "
            f"classified={report.get('classification')} "
            f"heist_allowed={report.get('heist_allowed')} "
            f"markers={report.get('player_markers', [])} "
            f"blockers={report.get('blocker_markers', [])}"
        )
        response_report = dict(report)
        response_report.pop("raw_xml", None)
        return jsonify(response_report)
    except Exception as e:
        return jsonify({"error": str(e), "heist_allowed": False}), 500

@app.route("/api/settings", methods=["POST"])
def update_settings():
    if not gui_app: return jsonify({"error": "No App"}), 500
    try:
        data = request.json
        action = data.get("action")
        
        if action == "connect":
            # Just config update + connect logic
            if "adb_host" in data: 
                gui_app.update_config("adb_host", data["adb_host"])
                gui_app.connect_adb()
                
        elif action == "update":
            # Generic update for any key provided
            for key, val in data.items():
                if key == "action": continue
                
                # Map frontend keys to backend config keys
                config_key = key
                if key == "tmdb": config_key = "tmdb_api_key"
                if key == "mal": config_key = "mal_client_id"
                if key == "trakt": config_key = "trakt_client_id"
                if key == "trakt_secret": config_key = "trakt_client_secret"
                if key == "discord": config_key = "discord_client_id"
                if key == "discord_wako": config_key = "discord_wako_client_id"
                if key == "skip_tmdb": config_key = "skip_tmdb_id"
                if key == "skip_mal": config_key = "skip_mal_id"
                # RPC config mappings
                if key == "rpc_rating_badges": config_key = "rpc_rating_badges_enabled"
                if key == "rpc_status_cycling": config_key = "rpc_status_cycling_enabled"
                if key == "rpc_status_effects": config_key = "rpc_status_effects_enabled"
                if key == "rpc_buttons": config_key = "rpc_buttons_enabled"
                if key == "rpc_small_icon": config_key = "rpc_small_icon_mode"
                if key == "rpc_large_image": config_key = "rpc_large_image_mode"

                # Update Config - accept any key that exists in config or DEFAULT_CONFIG
                if config_key in gui_app.config or config_key in DEFAULT_CONFIG or key in skip_config_keys:
                    gui_app.config[config_key] = val
                    
                # Live Updates for skip manager
                if key == "aniskip_smart": gui_app.skip_manager.smart_mode = val
                if key == "aniskip_enabled": gui_app.skip_manager.enabled = val
                if key == "introdb_enabled": gui_app.skip_manager.introdb_enabled = val
                if key == "aniskip_fallback": gui_app.skip_manager.aniskip_fallback = val
                if key == "tidb_enabled": gui_app.skip_manager.tidb_enabled = val
                if key == "remote_json_enabled": gui_app.skip_manager.remote_json_enabled = val
                if key == "videoskip_enabled": gui_app.skip_manager.videoskip_enabled = val
                if key == "notscare_major_enabled": gui_app.skip_manager.notscare_major_enabled = val
                if key == "notscare_minor_enabled": gui_app.skip_manager.notscare_minor_enabled = val
                if key == "skipme_enabled": gui_app.skip_manager.skipme_enabled = val
                if key == "skip_priority_order": gui_app.skip_manager.skip_priority_order = val
                if key == "skip_tmdb_id": gui_app.skip_manager.manual_tmdb_id = val
                if key == "skip_mal_id": gui_app.skip_manager.manual_mal_id = val
                if key == "skip_mode":
                     gui_app.skip_manager.enabled = (val != "off")
                if (config_key == "artwork_provider" or config_key.startswith("top_posters_")) and hasattr(gui_app, "top_posters"):
                     gui_app.top_posters.update_config(gui_app.config)
                     gui_app.last_artwork_key = None
                if (config_key == "artwork_provider" or config_key.startswith("erdb_") or config_key.startswith("erdbT") or config_key.startswith("erdbB")) and hasattr(gui_app, "erdb"):
                     gui_app.erdb.update_config(gui_app.config)
                     gui_app.last_artwork_key = None
                if config_key.startswith("nuvio_covers_") and hasattr(gui_app, "nuvio_covers"):
                     from src.core.nuvio import NuvioCoversClient
                     gui_app.nuvio_covers = NuvioCoversClient(
                         gui_app.config.get("nuvio_covers_base_url", "https://nuvioapp.space"),
                         gui_app.config.get("nuvio_covers_token", ""),
                         gui_app.config.get("nuvio_covers_email", ""),
                         gui_app.config.get("nuvio_covers_password", ""),
                         on_token_refresh=gui_app._save_nuvio_token,
                     )
                     gui_app.last_network_gif_url = None
                     gui_app.last_network_gif_name = None
            
            gui_app.save_settings()
            
            # Trigger updates for specific items
            if "tmdb_api_key" in gui_app.config:
                gui_app.tmdb_key = gui_app.config["tmdb_api_key"]
            
            # Live refresh Trakt client credentials
            if gui_app.config.get("trakt_client_id"):
                gui_app.trakt.client_id = gui_app.config["trakt_client_id"]
                gui_app.trakt.headers["trakt-api-key"] = gui_app.config["trakt_client_id"]
            if gui_app.config.get("trakt_client_secret"):
                gui_app.trakt.client_secret = gui_app.config["trakt_client_secret"]
                
            # Live refresh Discord Client ID based on wako mode
            if "discord_client_id" in data or "discord_wako" in data or "wako_mode" in data:
                # App logic determines which ID to use in the update loop, but we can force clear it or just let the app handle it.
                pass
                
        _broadcast_sse("config_update", {"keys": list(data.keys())})
        return jsonify({"status": "ok"})
    except Exception as e:
         return jsonify({"error": str(e)}), 500

@app.route("/api/artwork/top-posters/season/<cache_key>.jpg")
def top_posters_season_artwork(cache_key):
    if not gui_app or not hasattr(gui_app, "top_posters"):
        abort(404)
    path = gui_app.top_posters.get_cached_artwork_path(cache_key)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="image/jpeg", max_age=86400)

@app.route("/api/artwork/erdb/discord/<cache_key>.png")
def erdb_discord_artwork(cache_key):
    if not gui_app or not hasattr(gui_app, "get_erdb_discord_art_path"):
        abort(404)
    path = gui_app.get_erdb_discord_art_path(cache_key)
    if not path or not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="image/png", max_age=86400)

@app.route("/i/<cache_key>.png")
def rpc_cached_artwork(cache_key):
    if not gui_app or not hasattr(gui_app, "_rpc_artwork_cache_path"):
        abort(404)

    safe_key = "".join(
        ch for ch in str(cache_key or "")
        if ch.isalnum() or ch in ("-", "_")
    )

    path = gui_app._rpc_artwork_cache_path(safe_key)

    if not path or not os.path.exists(path):
        abort(404)

    return send_file(path, mimetype="image/png", max_age=86400)

@app.route("/api/command", methods=["POST"])
def send_command():
    if not gui_app: return jsonify({"error": "No App"}), 500
    
    cmd = request.json.get("command")
    
    if cmd == "play_pause": gui_app.play_pause()
    elif cmd == "stop": gui_app.stop_playback()
    elif cmd == "next": gui_app.next_track()
    elif cmd == "prev": gui_app.prev_track()
    elif cmd == "seek_fwd": gui_app.seek_forward()
    elif cmd == "seek_back": gui_app.seek_backward()
    elif cmd == "toggle_skip": gui_app.toggle_skip()
    elif cmd == "seek_to":
        target = request.json.get("target")
        if target is not None: gui_app.seek_to(int(target))
    elif cmd == "restart": gui_app.restart_app()
    elif cmd == "start_rpc": gui_app.rpc.connect() # simplified
    elif cmd == "stop_rpc": gui_app.rpc.close()
    elif cmd == "scan_network": gui_app.scan_network()
    elif cmd == "trakt_auth":
        return jsonify(gui_app.start_trakt_auth())
    
    # Open URL command for "Link Handling"
    elif cmd == "open_url":
        url = request.json.get("url")
        if url:
            import webbrowser
            webbrowser.open(url)
            
    return jsonify({"status": "ok"})

@app.route("/api/trakt/lists")
def get_trakt_lists():
    if not gui_app: return jsonify({"error": "No App"}), 500
    lists = gui_app.trakt.get_user_lists()
    return jsonify(lists)

@app.route("/api/trakt/list_items")
def get_trakt_list_items():
    if not gui_app: return jsonify({"error": "No App"}), 500
    list_id = request.args.get('id')
    user = request.args.get('user', 'me')
    
    if not list_id: return jsonify([])
    
    items = gui_app.trakt.get_list_items(list_id, user)
    return jsonify(items)

@app.route('/api/remote/<string:key>', methods=['POST'])
def remote_control(key):
    if not gui_app: return jsonify({"error": "No App"}), 500
    
    key_map = {
        "up": 19,
        "down": 20,
        "left": 21,
        "right": 22,
        "center": 23, # DPAD_CENTER
        "back": 4,    # KEYCODE_BACK
        "home": 3,
        "menu": 82,
        "vol_up": 24,
        "vol_down": 25,
        "mute": 164
    }
    
    if key in key_map:
        gui_app.controller.send_key(key_map[key])
        return jsonify({"status": "ok"})
    return jsonify({"error": "invalid key"}), 400

@app.route("/api/launch", methods=["POST"])
def launch_content():
    if not gui_app: return jsonify({"error": "No App"}), 500
    
    data = request.json
    ctype = data.get("type") # movie, show
    cid = data.get("id") # tt1234567
    season = data.get("season")
    episode = data.get("episode")
    
    if not cid: return jsonify({"error": "No ID"}), 400
    
    # Construct Deep Link
    url = ""
    if ctype == "movie":
        url = f"stremio://detail/movie/{cid}"
    elif ctype == "show" or ctype == "series":
        if season is not None and episode is not None:
            # Episode Format: series/ttID/ttID:S:E
            url = f"stremio://detail/series/{cid}/{cid}:{season}:{episode}"
        else:
            url = f"stremio://detail/series/{cid}"
            
    if url:
        success = gui_app.controller.launch_deep_link(url)
        return jsonify({"success": success})
        
    return jsonify({"error": "Invalid Content Type"}), 400

# --- Analytics API ---
@app.route("/api/analytics/stats")
@require_auth
def get_analytics_stats():
    if not gui_app: return jsonify({"error": "No App"}), 500
    return jsonify(gui_app.analytics.get_total_stats())

@app.route("/api/analytics/daily")
@require_auth
def get_analytics_daily():
    if not gui_app: return jsonify({"error": "No App"}), 500
    days = request.args.get("days", 7, type=int)
    return jsonify(gui_app.analytics.get_daily_stats(days))

@app.route("/api/analytics/sessions")
@require_auth
def get_analytics_sessions():
    if not gui_app: return jsonify({"error": "No App"}), 500
    limit = request.args.get("limit", 50, type=int)
    return jsonify(gui_app.analytics.get_recent_sessions(limit))

@app.route("/api/analytics/advanced")
@require_auth
def get_analytics_advanced():
    if not gui_app: return jsonify({"error": "No App"}), 500
    return jsonify(gui_app.analytics.get_advanced_stats())

@app.route("/api/analytics/search")
@require_auth
def search_analytics():
    if not gui_app: return jsonify({"error": "No App"}), 500
    q = request.args.get("q", "")
    limit = request.args.get("limit", 50, type=int)
    return jsonify(gui_app.analytics.search_history(q, limit))


# --- Health Check ---
@app.route("/api/health")
def health_check():
    if not gui_app:
        return jsonify({"status": "starting"}), 503
    s = gui_app.shared_state
    return jsonify({
        "status": "ok",
        "uptime": int(time.time() - getattr(gui_app, '_start_time', time.time())),
        "adb_connected": s.get("connected", False),
        "discord_connected": getattr(gui_app.rpc, 'connected', False),
        "device": _safe_text(s.get("device"), "Disconnected"),
        "is_playing": s.get("is_playing", False),
    })


# --- Authentication ---
@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    if not gui_app: return jsonify({"error": "No App"}), 500
    if not gui_app.config.get("dashboard_auth_enabled", False):
        return jsonify({"status": "ok", "message": "Auth not enabled"})
    data = request.json or {}
    pin = data.get("pin", "")
    if pin == gui_app.config.get("dashboard_auth_pin", ""):
        resp = make_response(jsonify({"status": "ok"}))
        resp.set_cookie("dashboard_pin", pin, max_age=86400, httponly=True)
        if hasattr(gui_app, 'audit_log'):
            gui_app.audit_log.log("auth", {"action": "login_success", "ip": request.remote_addr})
        return resp
    if hasattr(gui_app, 'audit_log'):
        gui_app.audit_log.log("auth", {"action": "login_failed", "ip": request.remote_addr})
    return jsonify({"error": "Invalid PIN"}), 401

@app.route("/api/auth/status")
def auth_status():
    if not gui_app: return jsonify({"enabled": False})
    enabled = gui_app.config.get("dashboard_auth_enabled", False)
    pin = gui_app.config.get("dashboard_auth_pin", "")
    if not enabled or not pin:
        return jsonify({"enabled": False, "authenticated": True})
    auth_cookie = request.cookies.get("dashboard_pin", "")
    return jsonify({"enabled": True, "authenticated": auth_cookie == pin})


# --- SSE Endpoint ---
@app.route("/api/events")
def sse_stream():
    def generate():
        q = queue.Queue(maxsize=50)
        with _sse_lock:
            _sse_clients.append(q)
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield msg
                except queue.Empty:
                    yield ":\n\n"  # keepalive
        except GeneratorExit:
            pass
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- Config Import/Export ---
@app.route("/api/config/export")
@require_auth
def config_export():
    if not gui_app: return jsonify({"error": "No App"}), 500
    return jsonify({"config": json.loads(export_config(gui_app.config))})

@app.route("/api/config/import", methods=["POST"])
@require_auth
def config_import():
    if not gui_app: return jsonify({"error": "No App"}), 500
    data = request.json or {}
    config_json = data.get("config")
    if not config_json:
        return jsonify({"error": "No config data"}), 400
    try:
        merged = import_config(json.dumps(config_json), gui_app.config)
        warnings = validate_config(merged)
        gui_app.config.update(merged)
        gui_app.save_settings()
        if hasattr(gui_app, 'audit_log'):
            gui_app.audit_log.log("config", {"action": "import", "keys": len(config_json)})
        return jsonify({"status": "ok", "warnings": warnings})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/config/validate", methods=["POST"])
@require_auth
def config_validate():
    if not gui_app: return jsonify({"error": "No App"}), 500
    warnings = validate_config(gui_app.config)
    return jsonify({"valid": len(warnings) == 0, "warnings": warnings})

@app.route("/api/config/schema")
def config_schema():
    schema = {}
    for key, default_val in DEFAULT_CONFIG.items():
        schema[key] = {
            "type": type(default_val).__name__,
            "default": default_val,
        }
    return jsonify(schema)


# --- Audit Log ---
@app.route("/api/audit")
@require_auth
def get_audit_log():
    if not gui_app: return jsonify({"error": "No App"}), 500
    if not hasattr(gui_app, 'audit_log'):
        return jsonify([])
    limit = request.args.get("limit", 100, type=int)
    category = request.args.get("category", None)
    entries = gui_app.audit_log.get_entries(limit=limit, event_type=category)
    return jsonify(entries)


# --- RPC History ---
@app.route("/api/rpc/history")
@require_auth
def get_rpc_history():
    if not gui_app: return jsonify({"error": "No App"}), 500
    if not hasattr(gui_app, 'rpc_history'):
        return jsonify([])
    return jsonify(gui_app.rpc_history.get_all())


# --- Skip Cache Stats ---
@app.route("/api/skip/cache")
@require_auth
def get_skip_cache_stats():
    if not gui_app: return jsonify({"error": "No App"}), 500
    return jsonify(gui_app.skip_manager.get_cache_stats())

@app.route("/api/skip/cache/clear", methods=["POST"])
@require_auth
def clear_skip_cache():
    if not gui_app: return jsonify({"error": "No App"}), 500
    gui_app.skip_manager.clear_cache()
    return jsonify({"status": "ok"})


# --- API Key Validation ---
@app.route("/api/validate/keys", methods=["POST"])
@require_auth
@rate_limit(max_calls=5, period=60)
def validate_api_keys():
    if not gui_app: return jsonify({"error": "No App"}), 500
    from src.core.api_validator import APIKeyValidator
    results = APIKeyValidator.validate_all(gui_app.config)
    return jsonify(results)


# --- Plugin System ---
@app.route("/api/plugins")
@require_auth
def list_plugins():
    if not gui_app: return jsonify({"error": "No App"}), 500
    if not hasattr(gui_app, 'plugin_registry'):
        return jsonify({"metadata": [], "skip": [], "scrobble": [], "artwork": []})
    return jsonify(gui_app.plugin_registry.list_providers())


# --- Integration Status ---
@app.route("/api/integrations/status")
@require_auth
def integration_status():
    if not gui_app: return jsonify({"error": "No App"}), 500
    status = {}
    integration_names = [
        "anilist", "letterboxd", "justwatch", "opensubtitles",
        "simkl", "kitsu", "lastfm", "plex", "jellyfin", "emby",
        "notion", "obsidian"
    ]
    for name in integration_names:
        status[name] = {
            "enabled": gui_app.config.get(f"{name}_enabled", False),
            "configured": bool(gui_app.config.get(f"{name}_api_key", "") or
                              gui_app.config.get(f"{name}_access_token", "") or
                              gui_app.config.get(f"{name}_url", "")),
        }
    return jsonify(status)


# --- OpenAPI / Swagger Docs ---
@app.route("/api/docs")
def api_docs():
    docs = {
        "openapi": "3.0.0",
        "info": {
            "title": "Ascend Media RPC API",
            "version": "2.0.0",
            "description": "API for Ascend Media RPC Dashboard"
        },
        "paths": {}
    }
    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static':
            continue
        methods = [m for m in rule.methods if m in ('GET', 'POST', 'PUT', 'DELETE')]
        path = str(rule)
        docs["paths"][path] = {}
        for method in methods:
            docs["paths"][path][method.lower()] = {
                "summary": rule.endpoint.replace("_", " ").title(),
                "responses": {"200": {"description": "Success"}}
            }
    return jsonify(docs)


# --- Multi-Device ---
@app.route("/api/devices")
@require_auth
def list_devices():
    if not gui_app: return jsonify({"error": "No App"}), 500
    devices = gui_app.config.get("multi_device_list", [])
    current = {
        "host": gui_app.config.get("adb_host", ""),
        "port": gui_app.config.get("adb_port", 5555),
        "connected": gui_app.shared_state.get("connected", False),
        "name": _safe_text(gui_app.shared_state.get("device"), "Unknown"),
    }
    mdns_devices = []
    if hasattr(gui_app, 'discovery') and gui_app.discovery:
        mdns_devices = gui_app.discovery.get_mdns_devices()
    return jsonify({
        "current": current,
        "saved": devices,
        "discovered": mdns_devices,
    })

@app.route("/api/devices/switch", methods=["POST"])
@require_auth
def switch_device():
    if not gui_app: return jsonify({"error": "No App"}), 500
    data = request.json or {}
    host = data.get("host", "")
    port = data.get("port", 5555)
    if not host:
        return jsonify({"error": "No host specified"}), 400
    gui_app.update_config("adb_host", host)
    gui_app.update_config("adb_port", int(port))
    gui_app.connect_adb()
    return jsonify({"status": "ok", "host": host, "port": port})


# --- Onboarding ---
@app.route("/api/onboarding/status")
def onboarding_status():
    if not gui_app: return jsonify({"completed": True})
    return jsonify({
        "completed": gui_app.config.get("onboarding_completed", False),
        "steps": {
            "adb_configured": bool(gui_app.config.get("adb_host", "")),
            "discord_configured": bool(gui_app.config.get("discord_client_id", "")),
            "tmdb_configured": bool(gui_app.config.get("tmdb_api_key", "")),
        }
    })

@app.route("/api/onboarding/complete", methods=["POST"])
def onboarding_complete():
    if not gui_app: return jsonify({"error": "No App"}), 500
    gui_app.update_config("onboarding_completed", True)
    return jsonify({"status": "ok"})


# --- Trakt Social & Collection ---
@app.route("/api/trakt/collection")
@require_auth
def get_trakt_collection():
    if not gui_app: return jsonify({"error": "No App"}), 500
    media_type = request.args.get("type", "movies")
    return jsonify(gui_app.trakt.get_collection(media_type))

@app.route("/api/trakt/collection/add", methods=["POST"])
@require_auth
def add_to_trakt_collection():
    if not gui_app: return jsonify({"error": "No App"}), 500
    data = request.json or {}
    success = gui_app.trakt.add_to_collection(data)
    return jsonify({"status": "ok" if success else "failed"})

@app.route("/api/trakt/checkin", methods=["POST"])
@require_auth
def trakt_checkin():
    if not gui_app: return jsonify({"error": "No App"}), 500
    data = request.json or {}
    message = data.pop("message", "")
    success = gui_app.trakt.check_in(data, message)
    return jsonify({"status": "ok" if success else "failed"})

@app.route("/api/trakt/friends")
@require_auth
def trakt_friends_watching():
    if not gui_app: return jsonify({"error": "No App"}), 500
    return jsonify(gui_app.trakt.get_friends_watching())

@app.route("/api/trakt/calendar")
@require_auth
def trakt_calendar():
    if not gui_app: return jsonify({"error": "No App"}), 500
    days = request.args.get("days", 14, type=int)
    return jsonify(gui_app.trakt.get_calendar(days))

@app.route("/api/trakt/recommendations")
@require_auth
def trakt_recommendations():
    if not gui_app: return jsonify({"error": "No App"}), 500
    media_type = request.args.get("type", "movies")
    return jsonify(gui_app.trakt.get_recommendations(media_type))

@app.route("/api/trakt/rate", methods=["POST"])
@require_auth
def trakt_rate():
    if not gui_app: return jsonify({"error": "No App"}), 500
    data = request.json or {}
    rating = data.pop("rating", 0)
    success = gui_app.trakt.rate_media(data, rating)
    return jsonify({"status": "ok" if success else "failed"})

@app.route("/api/trakt/stats")
@require_auth
def trakt_stats():
    if not gui_app: return jsonify({"error": "No App"}), 500
    return jsonify(gui_app.trakt.get_stats())


# --- Skip Analytics ---
@app.route("/api/analytics/skip/providers")
@require_auth
def skip_provider_stats():
    if not gui_app: return jsonify({"error": "No App"}), 500
    return jsonify(gui_app.analytics.get_skip_provider_stats())

@app.route("/api/analytics/skip/categories")
@require_auth
def skip_category_stats():
    if not gui_app: return jsonify({"error": "No App"}), 500
    return jsonify(gui_app.analytics.get_skip_category_stats())

@app.route("/api/analytics/weekly")
@require_auth
def weekly_report():
    if not gui_app: return jsonify({"error": "No App"}), 500
    return jsonify(gui_app.analytics.get_weekly_report())

@app.route("/api/analytics/monthly")
@require_auth
def monthly_report():
    if not gui_app: return jsonify({"error": "No App"}), 500
    return jsonify(gui_app.analytics.get_monthly_report())


# --- Watch History Filters ---
@app.route("/api/analytics/history/filtered")
@require_auth
def filtered_history():
    if not gui_app: return jsonify({"error": "No App"}), 500
    status = request.args.get("status", "all")
    limit = request.args.get("limit", 50, type=int)
    return jsonify(gui_app.analytics.get_filtered_history(status, limit))

@app.route("/api/analytics/history/grouped")
@require_auth
def grouped_history():
    if not gui_app: return jsonify({"error": "No App"}), 500
    limit = request.args.get("limit", 20, type=int)
    return jsonify(gui_app.analytics.get_grouped_by_show(limit))


# --- Stats Card ---
@app.route("/api/stats/card")
@require_auth
def generate_stats_card():
    if not gui_app: return jsonify({"error": "No App"}), 500
    from src.core.stats_card_generator import StatsCardGenerator
    stats = gui_app.analytics.get_advanced_stats()
    gen = StatsCardGenerator()
    png_bytes = gen.generate(stats)
    if not png_bytes:
        return jsonify({"error": "Pillow not installed"}), 500
    return Response(png_bytes, mimetype="image/png",
                    headers={"Content-Disposition": "attachment; filename=ascend-stats.png"})


# --- Device Health ---
@app.route("/api/device/health")
@require_auth
def device_health():
    if not gui_app: return jsonify({"error": "No App"}), 500
    if not gui_app.controller.connected:
        return jsonify({"connected": False})
    try:
        device = gui_app.controller.device
        battery_raw = device.shell("dumpsys battery")
        battery = {}
        for line in battery_raw.split("\n"):
            if "level" in line.lower():
                try: battery["level"] = int(line.split(":")[1].strip())
                except: pass
            if "status" in line.lower():
                try: battery["status"] = line.split(":")[1].strip()
                except: pass
            if "temperature" in line.lower():
                try: battery["temperature"] = int(line.split(":")[1].strip()) / 10.0
                except: pass

        cpu_raw = device.shell("cat /proc/loadavg")
        cpu_parts = cpu_raw.strip().split()
        cpu = {"load_1m": cpu_parts[0], "load_5m": cpu_parts[1], "load_15m": cpu_parts[2]} if len(cpu_parts) >= 3 else {}

        mem_raw = device.shell("cat /proc/meminfo")
        mem = {}
        for line in mem_raw.split("\n"):
            if "MemTotal" in line:
                try: mem["total_kb"] = int(line.split(":")[1].strip().split()[0])
                except: pass
            if "MemAvailable" in line:
                try: mem["available_kb"] = int(line.split(":")[1].strip().split()[0])
                except: pass

        storage_raw = device.shell("df /data")
        storage = {}
        lines = storage_raw.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 4:
                storage = {"total": parts[1], "used": parts[2], "available": parts[3]}

        uptime_raw = device.shell("cat /proc/uptime")
        uptime_secs = float(uptime_raw.strip().split()[0]) if uptime_raw.strip() else 0

        return jsonify({
            "connected": True,
            "battery": battery,
            "cpu": cpu,
            "memory": mem,
            "storage": storage,
            "uptime_seconds": int(uptime_secs),
        })
    except Exception as e:
        return jsonify({"connected": True, "error": str(e)})


# --- ADB Wi-Fi Pairing ---
@app.route("/api/adb/pair", methods=["POST"])
@require_auth
def adb_wifi_pair():
    if not gui_app: return jsonify({"error": "No App"}), 500
    data = request.json or {}
    host = data.get("host", "")
    port = data.get("port", 5555)
    pairing_code = data.get("code", "")
    if not host:
        return jsonify({"error": "No host specified"}), 400
    try:
        import subprocess
        if pairing_code:
            result = subprocess.run(
                ["adb", "pair", f"{host}:{port}", pairing_code],
                capture_output=True, text=True, timeout=15
            )
        else:
            result = subprocess.run(
                ["adb", "connect", f"{host}:{port}"],
                capture_output=True, text=True, timeout=15
            )
        output = result.stdout + result.stderr
        success = "connected" in output.lower() or "paired" in output.lower()
        if success:
            _broadcast_sse("device_paired", {"host": host, "port": port})
        return jsonify({"status": "ok" if success else "failed", "output": output.strip()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Remote Control Extended ---
@app.route("/api/remote/text", methods=["POST"])
@require_auth
def remote_text_input():
    """Send text input to device (keyboard relay)."""
    if not gui_app: return jsonify({"error": "No App"}), 500
    data = request.json or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text"}), 400
    try:
        escaped = text.replace(" ", "%s").replace("'", "\'")
        gui_app.controller.device.shell(f"input text '{escaped}'")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/remote/launch", methods=["POST"])
@require_auth
def remote_launch_app():
    """Launch an app on the device."""
    if not gui_app: return jsonify({"error": "No App"}), 500
    data = request.json or {}
    package = data.get("package", "")
    if not package:
        return jsonify({"error": "No package"}), 400
    try:
        gui_app.controller.device.shell(f"monkey -p {package} -c android.intent.category.LAUNCHER 1")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/remote/apps")
@require_auth
def remote_list_apps():
    """List installed apps on the device."""
    if not gui_app: return jsonify({"error": "No App"}), 500
    if not gui_app.controller.connected:
        return jsonify([])
    try:
        raw = gui_app.controller.device.shell("pm list packages -3")
        apps = [line.replace("package:", "").strip() for line in raw.split("\n") if line.strip()]
        return jsonify(sorted(apps))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Structured Logging ---
@app.route("/api/logs")
@require_auth
def get_logs():
    """Get application logs."""
    if not gui_app: return jsonify({"error": "No App"}), 500
    limit = request.args.get("limit", 200, type=int)
    if hasattr(gui_app, '_memory_log_handler'):
        logs = list(gui_app._memory_log_handler.buffer)[-limit:]
        return jsonify([{
            "timestamp": getattr(r, 'created', 0),
            "level": getattr(r, 'levelname', 'INFO'),
            "message": getattr(r, 'getMessage', lambda: str(r))(),
            "module": getattr(r, 'module', ''),
        } for r in logs])
    return jsonify([])

@app.route("/api/logs/export")
@require_auth
def export_logs():
    """Export logs as JSON file."""
    if not gui_app: return jsonify({"error": "No App"}), 500
    if hasattr(gui_app, '_memory_log_handler'):
        logs = list(gui_app._memory_log_handler.buffer)
        log_data = [{
            "timestamp": getattr(r, 'created', 0),
            "level": getattr(r, 'levelname', 'INFO'),
            "message": getattr(r, 'getMessage', lambda: str(r))(),
            "module": getattr(r, 'module', ''),
        } for r in logs]
        return jsonify(log_data)
    return jsonify([])


# --- Onboarding Wizard (multi-step) ---
@app.route("/api/onboarding/steps")
def onboarding_steps():
    if not gui_app: return jsonify({"error": "No App"}), 500
    return jsonify({
        "completed": gui_app.config.get("onboarding_completed", False),
        "steps": [
            {
                "id": "device",
                "title": "Connect Your Device",
                "description": "Find and connect to your Android device via ADB",
                "completed": bool(gui_app.config.get("adb_host", "")),
                "fields": [
                    {"key": "adb_host", "label": "Device IP", "type": "text", "value": gui_app.config.get("adb_host", "")},
                    {"key": "adb_port", "label": "ADB Port", "type": "number", "value": gui_app.config.get("adb_port", 5555)},
                ]
            },
            {
                "id": "discord",
                "title": "Discord Rich Presence",
                "description": "Set up your Discord Client ID for RPC",
                "completed": bool(gui_app.config.get("discord_client_id", "")),
                "fields": [
                    {"key": "discord_client_id", "label": "Discord Client ID", "type": "text", "value": gui_app.config.get("discord_client_id", "")},
                ]
            },
            {
                "id": "tmdb",
                "title": "TMDB Metadata",
                "description": "Add your TMDB API key for movie/show metadata and artwork",
                "completed": bool(gui_app.config.get("tmdb_api_key", "")),
                "fields": [
                    {"key": "tmdb_api_key", "label": "TMDB API Key", "type": "text", "value": gui_app.config.get("tmdb_api_key", "")},
                ]
            },
            {
                "id": "artwork",
                "title": "Artwork Provider",
                "description": "Choose your preferred artwork source",
                "completed": True,
                "fields": [
                    {"key": "artwork_provider", "label": "Provider", "type": "select",
                     "options": ["top_posters", "erdb", "tmdb", "nuvio"],
                     "value": gui_app.config.get("artwork_provider", "top_posters")},
                ]
            },
            {
                "id": "skip",
                "title": "Skip Providers",
                "description": "Choose which skip segment providers to enable",
                "completed": gui_app.config.get("skip_mode", "off") != "off",
                "fields": [
                    {"key": "skip_mode", "label": "Skip Mode", "type": "select",
                     "options": ["off", "auto", "manual"],
                     "value": gui_app.config.get("skip_mode", "auto")},
                ]
            },
            {
                "id": "trakt",
                "title": "Trakt Integration",
                "description": "Connect Trakt for scrobbling and watch history",
                "completed": bool(gui_app.config.get("trakt_client_id", "")),
                "optional": True,
                "fields": [
                    {"key": "trakt_client_id", "label": "Trakt Client ID", "type": "text", "value": gui_app.config.get("trakt_client_id", "")},
                    {"key": "trakt_client_secret", "label": "Trakt Client Secret", "type": "password", "value": gui_app.config.get("trakt_client_secret", "")},
                ]
            },
        ]
    })

@app.route("/api/onboarding/save-step", methods=["POST"])
def onboarding_save_step():
    if not gui_app: return jsonify({"error": "No App"}), 500
    data = request.json or {}
    step_id = data.get("step_id", "")
    fields = data.get("fields", {})
    for key, value in fields.items():
        gui_app.update_config(key, value)
    _broadcast_sse("onboarding_step", {"step": step_id, "status": "saved"})
    return jsonify({"status": "ok", "step": step_id})


# --- FanArt.tv ---
@app.route("/api/fanart/<media_type>/<tmdb_id>")
@require_auth
def fanart_images(media_type, tmdb_id):
    if not gui_app: return jsonify({"error": "No App"}), 500
    if not gui_app.config.get("fanart_api_key"):
        return jsonify({"error": "FanArt API key not configured"}), 400
    from src.core.integrations.fanart import FanArtClient
    client = FanArtClient(api_key=gui_app.config["fanart_api_key"])
    if media_type == "movie":
        data = client.get_movie_images(tmdb_id)
    else:
        data = client.get_show_images(tmdb_id)
    return jsonify(data or {})


# --- Artwork Fallback Chain ---
@app.route("/api/artwork/chain", methods=["GET"])
@require_auth
def get_artwork_chain():
    if not gui_app: return jsonify({"error": "No App"}), 500
    return jsonify({
        "chain": gui_app.config.get("artwork_fallback_chain", ["top_posters", "erdb", "tmdb", "nuvio"]),
        "available": ["top_posters", "erdb", "tmdb", "nuvio", "fanart"]
    })

@app.route("/api/artwork/chain", methods=["POST"])
@require_auth
def set_artwork_chain():
    if not gui_app: return jsonify({"error": "No App"}), 500
    data = request.json or {}
    chain = data.get("chain", [])
    gui_app.update_config("artwork_fallback_chain", chain)
    _broadcast_sse("config_update", {"keys": ["artwork_fallback_chain"]})
    return jsonify({"status": "ok"})


# --- Theme ---
@app.route("/api/theme", methods=["GET"])
def get_theme():
    if not gui_app: return jsonify({"mode": "dark", "accent": "#8a2be2", "oled": False})
    return jsonify({
        "mode": gui_app.config.get("theme_mode", "dark"),
        "accent": gui_app.config.get("theme_accent_color", "#8a2be2"),
        "oled": gui_app.config.get("theme_oled_black", False),
    })

@app.route("/api/theme", methods=["POST"])
def set_theme():
    if not gui_app: return jsonify({"error": "No App"}), 500
    data = request.json or {}
    if "mode" in data:
        gui_app.update_config("theme_mode", data["mode"])
    if "accent" in data:
        gui_app.update_config("theme_accent_color", data["accent"])
    if "oled" in data:
        gui_app.update_config("theme_oled_black", data["oled"])
    _broadcast_sse("theme_change", data)
    return jsonify({"status": "ok"})

