import json
import os
from typing import Dict

import sys

def get_config_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.getcwd()

CONFIG_FILE = os.path.join(get_config_path(), "config.json")

DEFAULT_CONFIG = {
    # ──────────────────────────────────────────────
    # ADB / Device Connection
    # ──────────────────────────────────────────────
    "adb_host": "",
    "adb_port": 5555,
    "adb_retry_count": 3,
    "adb_retry_delay": 1.0,
    "adb_command_dedup": True,
    "mdns_discovery_enabled": True,
    "stremio_desktop_enabled": False,
    "stremio_enhanced_auto_devtools": True,
    "stremio_enhanced_devtools_port": 9229,
    "stremio_enhanced_relaunch_cooldown": 90,
    "multi_device_enabled": False,
    "multi_device_list": [],

    # ──────────────────────────────────────────────
    # Metadata Providers (TMDB / MAL)
    # ──────────────────────────────────────────────
    "tmdb_api_key": "",
    "mal_client_id": "",
    "mal_metadata_enabled": True,
    "tmdb_rate_limit_enabled": True,
    "tmdb_rate_limit_calls": 40,
    "tmdb_rate_limit_period": 10,

    # ──────────────────────────────────────────────
    # Discord RPC
    # ──────────────────────────────────────────────
    "discord_client_id": "1451010126495617106",
    "discord_wako_client_id": "",
    "rpc_buttons_enabled": True,
    "rpc_streaming_mode": True,
    "rpc_custom_status": "",
    "rpc_time_display": "remaining",
    "rpc_large_image_mode": "episode",
    "rpc_small_icon_mode": "play_status",
    "rpc_rating_badges_enabled": False,
    "rpc_status_cycling_enabled": False,
    "rpc_status_effects_enabled": False,
    "rpc_branding": "on Stremio",
    "rpc_activity_type": "watching",
    "rpc_multi_activity_enabled": False,
    "rpc_update_all_discord_pipes": True,
    "rpc_dynamic_buttons": [],
    "rpc_cycling_messages": [],
    "rpc_cycling_interval": 30,
    "rpc_image_url_limit": 256,
    "rpc_history_enabled": True,
    "rpc_history_limit": 100,
    "rpc_multi_discord_enabled": False,
    "rpc_secondary_client_id": "",
    "show_device_name": True,
    "profanity_filter": False,

    # ──────────────────────────────────────────────
    # Skip Providers
    # ──────────────────────────────────────────────
    "skip_mode": "auto",
    "skip_tmdb_id": "",
    "skip_mal_id": "",
    "aniskip_enabled": False,
    "aniskip_fallback": True,
    "introdb_enabled": True,
    "tidb_enabled": False,
    "tidb_api_key": "",
    "remote_json_enabled": False,
    "remote_json_url": "https://busy-jacinta-shugi-c2885b2e.koyeb.app/download-db",
    "skipme_enabled": True,
    "videoskip_enabled": False,
    "notscare_major_enabled": False,
    "notscare_minor_enabled": False,
    "skipit_enabled": False,
    "skipit_token": "",
    "skipit_session_cookie": "",   # Clerk __client cookie value (long-lived)
    "skipit_session_id": "",       # Parsed from JWT (sid claim); auto-derived
    "skipit_frontend_api": "",     # e.g. clerk.getskipit.com (iss claim)
    "skip_priority_order": ["tidb", "remote_json", "introdb", "videoskip", "notscare_major", "notscare_minor", "skipit", "aniskip", "skipme"],
    "skip_cache_ttl": 3600,
    "skip_cache_max_size": 500,

    # ──────────────────────────────────────────────
    # Artwork & Covers
    # ──────────────────────────────────────────────
    "artwork_provider": "top_posters",
    "artwork_cache_enabled": True,
    "artwork_cache_size": 1024,
    "artwork_upload_enabled": False,
    "artwork_upload_command": "",
    "artwork_upload_timeout": 45,
    "artwork_fallback_chain": ["top_posters", "erdb", "tmdb", "nuvio"],
    # Top Posters
    "top_posters_enabled": False,
    "top_posters_api_key": "",
    "top_posters_base_url": "https://api.top-posters.com",
    "top_posters_badge_size": "medium",
    "top_posters_badge_position": "bottom-left",
    "top_posters_blur": False,
    "top_posters_style": "modern",
    "top_posters_season_mask_threshold": 32,
    # ERDB
    "erdb_token": "",
    "erdb_base_url": "https://easyratingsdb.com",
    "erdb_episode_id_mode": "realimdb",
    "erdb_validate_remote": False,
    "erdb_posters_enabled": True,
    "erdb_backdrops_enabled": True,
    "erdb_logos_enabled": True,
    "erdb_thumbnails_enabled": True,
    # Nuvio
    "nuvio_covers_enabled": False,
    "nuvio_covers_token": "",
    "nuvio_covers_email": "",
    "nuvio_covers_password": "",
    "nuvio_covers_base_url": "https://nuvioapp.space",
    "nuvio_covers_orientation": "all",

    # ──────────────────────────────────────────────
    # Wako Mode
    # ──────────────────────────────────────────────
    "wako_mode": False,
    "wako_player_only": False,
    "wako_stay_awake_on_pause": False,
    "wako_focus_lock": False,
    "wako_title_overrides": {},
    "wako_title_cache_enabled": True,
    "wako_focus_lock_whitelist": [],
    "wako_focus_lock_cooldown": 5,

    # ──────────────────────────────────────────────
    # API Integrations — Tracking
    # ──────────────────────────────────────────────
    "anilist_enabled": False,
    "anilist_access_token": "",
    "simkl_enabled": False,
    "simkl_client_id": "",
    "simkl_access_token": "",
    "kitsu_enabled": False,
    "kitsu_access_token": "",
    "letterboxd_enabled": False,
    "letterboxd_api_key": "",
    "letterboxd_api_secret": "",
    "lastfm_enabled": False,
    "lastfm_api_key": "",
    "lastfm_api_secret": "",
    "lastfm_session_key": "",
    "justwatch_enabled": False,
    "justwatch_country": "US",
    "opensubtitles_enabled": False,
    "opensubtitles_api_key": "",
    "opensubtitles_username": "",
    "opensubtitles_password": "",

    # ──────────────────────────────────────────────
    # API Integrations — Media Servers
    # ──────────────────────────────────────────────
    "plex_enabled": False,
    "plex_url": "",
    "plex_token": "",
    "jellyfin_enabled": False,
    "jellyfin_url": "",
    "jellyfin_api_key": "",
    "emby_enabled": False,
    "emby_url": "",
    "emby_api_key": "",

    # ──────────────────────────────────────────────
    # API Integrations — Journals
    # ──────────────────────────────────────────────
    "notion_enabled": False,
    "notion_api_key": "",
    "notion_database_id": "",
    "obsidian_enabled": False,
    "obsidian_vault_path": "",

    # ──────────────────────────────────────────────
    # Privacy & Security
    # ──────────────────────────────────────────────
    "privacy_mode": False,
    "privacy_hidden_text": "Watching something",
    "privacy_blacklist": [],
    "privacy_pause_analytics": True,
    "privacy_pause_trakt": True,
    "dashboard_auth_enabled": False,
    "dashboard_auth_pin": "",

    # ──────────────────────────────────────────────
    # Dashboard & Server
    # ──────────────────────────────────────────────
    "dashboard_port": 5466,
    "dashboard_public_base_url": "",
    "dashboard_ui_mode": "normal",
    "dashboard_https_enabled": False,
    "dashboard_cert_path": "",
    "dashboard_key_path": "",
    "update_interval": 2.0,
    "headless_mode": False,
    "onboarding_completed": False,

    # ──────────────────────────────────────────────
    # System & Advanced
    # ──────────────────────────────────────────────
    "playback_debug_enabled": False,
    "playback_logcat_enabled": False,
    "config_hot_reload": False,
    "config_schema_validation": True,
    "rate_limit_enabled": True,
    "rate_limit_default": "60/minute",
    "health_check_enabled": True,
    "api_key_validation_enabled": True,
    "audit_log_enabled": True,
    "audit_log_max_entries": 1000,
    "log_json_enabled": False,
    "log_level_overrides": {},

    # ──────────────────────────────────────────────
    # Theme & UI
    # ──────────────────────────────────────────────
    "theme_mode": "dark",
    "theme_accent_color": "#8a2be2",
    "theme_oled_black": False,

    # ──────────────────────────────────────────────
    # FanArt.tv
    # ──────────────────────────────────────────────
    "fanart_enabled": False,
    "fanart_api_key": "",

    # ──────────────────────────────────────────────
    # Trakt Social & Collection
    # ──────────────────────────────────────────────
    "trakt_collection_sync": False,
    "trakt_check_in_enabled": False,
    "trakt_social_enabled": False,
    "trakt_calendar_enabled": False,

    # ──────────────────────────────────────────────
    # Browser Push Notifications
    # ──────────────────────────────────────────────
    "push_notifications_enabled": False,

    # ──────────────────────────────────────────────
    # Skip Category Toggles
    # ──────────────────────────────────────────────
    "skip_cat_intro": True,
    "skip_cat_outro": True,
    "skip_cat_recap": True,
    "skip_cat_preview": True,
    "skip_cat_credits": True,
    "skip_cat_filler": True,
    "skip_cat_mature": True,
    "skip_cat_scare": True,

    # ──────────────────────────────────────────────
    # Device Health Monitoring
    # ──────────────────────────────────────────────
    "device_health_enabled": False,
    "device_health_interval": 30,

    # ──────────────────────────────────────────────
    # Artwork Quality
    # ──────────────────────────────────────────────
    "artwork_quality": "high",
    "artwork_max_width": 1000,
}


def _env_value(*names: str):
    for name in names:
        value = os.environ.get(name)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _coerce_env_value(value: str, default):
    if isinstance(default, bool):
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int) and not isinstance(default, bool):
        return int(value)
    if isinstance(default, float):
        return float(value)
    return value


def _apply_env_overrides(config: Dict) -> Dict:
    """Let containers and CI configure runtime settings without rewriting config.json."""
    env_map = {
        "adb_host": ("ASCEND_ADB_HOST", "ADB_HOST"),
        "adb_port": ("ASCEND_ADB_PORT", "ADB_PORT"),
        "dashboard_port": ("ASCEND_PORT", "DASHBOARD_PORT"),
        "dashboard_public_base_url": ("ASCEND_PUBLIC_BASE_URL", "DASHBOARD_PUBLIC_BASE_URL"),
        "discord_client_id": ("DISCORD_CLIENT_ID",),
        "discord_wako_client_id": ("DISCORD_WAKO_CLIENT_ID",),
        "tmdb_api_key": ("TMDB_API_KEY",),
        "top_posters_api_key": ("TOP_POSTERS_API_KEY",),
        "top_posters_base_url": ("TOP_POSTERS_BASE_URL",),
        "erdb_token": ("ERDB_TOKEN",),
        "erdb_base_url": ("ERDB_BASE_URL",),
        "nuvio_covers_token": ("NUVIO_COVERS_TOKEN",),
        "nuvio_covers_email": ("NUVIO_COVERS_EMAIL",),
        "nuvio_covers_password": ("NUVIO_COVERS_PASSWORD",),
        "nuvio_covers_base_url": ("NUVIO_COVERS_BASE_URL",),
    }
    for key, env_names in env_map.items():
        value = _env_value(*env_names)
        if value is None:
            continue
        try:
            config[key] = _coerce_env_value(value, DEFAULT_CONFIG.get(key, ""))
        except (TypeError, ValueError):
            continue
    return config


def load_config() -> Dict:
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG) # Save it immediately so user sees it
        return _apply_env_overrides(DEFAULT_CONFIG.copy())
    try:
        with open(CONFIG_FILE, 'r') as f:
            file_config = json.load(f)
            # Merge: Use default for missing keys
            config = DEFAULT_CONFIG.copy()
            config.update(file_config)
            
            # --- MIGRATION: Sanitize Skip Priority Order ---
            s_order = config.get("skip_priority_order", [])
            new_order = []
            for item in s_order:
                if item == "introhater": continue
                if item == "jumpscare": item = "notscare_major" # Legacy fallback
                if item == "jumpscare_major": item = "notscare_major"
                if item == "jumpscare_minor": item = "notscare_minor"
                if item not in new_order:
                    new_order.append(item)
            
            # Ensure all default providers are present if missing
            for item in DEFAULT_CONFIG["skip_priority_order"]:
                if item not in new_order:
                    new_order.append(item)
            
            config["skip_priority_order"] = new_order
            
            # Migrate toggles
            if "jumpscare_major_enabled" in file_config:
                config["notscare_major_enabled"] = file_config["jumpscare_major_enabled"]
            if "jumpscare_minor_enabled" in file_config:
                config["notscare_minor_enabled"] = file_config["jumpscare_minor_enabled"]
                
            # --- MIGRATION: Normalize old Top Posters host ---
            if "top-streaming.stream" in str(config.get("top_posters_base_url", "")):
                config["top_posters_base_url"] = "https://api.top-posters.com"

            return _apply_env_overrides(config)
    except:
        return _apply_env_overrides(DEFAULT_CONFIG.copy())

def save_config(config: Dict):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)


def validate_config(config: Dict) -> list:
    """Validate config values and return list of warnings."""
    warnings = []
    if config.get("adb_port") and not isinstance(config["adb_port"], int):
        warnings.append("adb_port must be an integer")
    if config.get("update_interval") and config["update_interval"] < 0.5:
        warnings.append("update_interval should be >= 0.5 seconds")
    if config.get("dashboard_port") and not (1024 <= config["dashboard_port"] <= 65535):
        warnings.append("dashboard_port must be between 1024 and 65535")
    if config.get("skip_cache_ttl") and config["skip_cache_ttl"] < 0:
        warnings.append("skip_cache_ttl must be non-negative")
    if config.get("skip_cache_max_size") and config["skip_cache_max_size"] < 1:
        warnings.append("skip_cache_max_size must be at least 1")
    if config.get("rpc_cycling_interval") and config["rpc_cycling_interval"] < 5:
        warnings.append("rpc_cycling_interval should be >= 5 seconds")
    unknown_keys = set(config.keys()) - set(DEFAULT_CONFIG.keys())
    if unknown_keys:
        warnings.append(f"Unknown config keys: {', '.join(sorted(unknown_keys))}")
    return warnings


def export_config(config: Dict) -> str:
    """Export config as JSON string (excluding sensitive keys)."""
    sensitive_keys = {
        "trakt_access_token", "trakt_refresh_token",
        "nuvio_covers_password", "nuvio_covers_token",
        "opensubtitles_password", "lastfm_session_key",
        "anilist_access_token", "simkl_access_token",
        "kitsu_access_token", "plex_token",
        "notion_api_key", "dashboard_auth_pin",
    }
    safe = {k: v for k, v in config.items() if k not in sensitive_keys}
    return json.dumps(safe, indent=4)


def import_config(json_str: str, current_config: Dict) -> Dict:
    """Import config from JSON string, merging with current config."""
    imported = json.loads(json_str)
    merged = current_config.copy()
    for k, v in imported.items():
        if k in DEFAULT_CONFIG:
            merged[k] = v
    return merged
