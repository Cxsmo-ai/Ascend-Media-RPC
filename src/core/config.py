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
    "adb_host": "",
    "adb_port": 5555,
    "tmdb_api_key": "",
    "discord_client_id": "1451010126495617106",
    "discord_wako_client_id": "",
    "dashboard_port": 5466,
    "dashboard_public_base_url": "",
    "dashboard_ui_mode": "normal",
    "update_interval": 2.0,
    "playback_debug_enabled": False,
    "playback_logcat_enabled": False,
    "aniskip_enabled": False,
    "mal_client_id": "",
    "mal_metadata_enabled": True,
    # Skip Provider Defaults
    "skip_tmdb_id": "",          # Manual TMDB ID for IntroDB
    "skip_mal_id": "",           # Manual MAL ID for AniSkip
    "introdb_enabled": True,
    "aniskip_fallback": True,
    "tidb_enabled": False,
    "tidb_api_key": "",
    "remote_json_enabled": False,
    "remote_json_url": "https://busy-jacinta-shugi-c2885b2e.koyeb.app/download-db",
    "skipme_enabled": True,
    "videoskip_enabled": False,
    "notscare_major_enabled": False,
    "notscare_minor_enabled": False,
    "skip_priority_order": ["tidb", "remote_json", "introdb", "videoskip", "notscare_major", "notscare_minor", "aniskip", "skipme"],
    "wako_mode": False,           # Wako Telemetry Mode (UI scraping via uiautomator)
    "wako_player_only": False,
    "wako_stay_awake_on_pause": False,
    "wako_focus_lock": False,
    # Phase 3: Smart Home Lighting
    "smart_home_enabled": False,
    "smart_home_provider": "webhook",  # "webhook", "hue", "homeassistant"
    "smart_home_play_url": "",
    "smart_home_pause_url": "",
    "hue_bridge_ip": "",
    "hue_api_key": "",
    "hue_group_id": "0",
    "hue_dim_brightness": 25,
    "ha_url": "",
    "ha_token": "",
    "ha_entity": "light.living_room",
    "ha_dim_brightness": 25,
    # Phase 4: Watch Party
    "watch_party_enabled": False,
    "watch_party_mode": "off",
    "watch_party_port": 5467,
    "watch_party_host_ip": "",
    # RPC Enhancements
    "rpc_buttons_enabled": True,
    "rpc_streaming_mode": True,
    "rpc_custom_status": "",
    "rpc_time_display": "remaining", # "remaining" or "elapsed"
    "rpc_large_image_mode": "episode", # "show", "season", "episode"
    "rpc_rating_badges_enabled": False,
    "rpc_status_cycling_enabled": False,
    "rpc_status_effects_enabled": False,
    "rpc_small_icon_mode": "play_status", # "play_status", "stremio", "wako", "device", "streaming_service", "content_network", "content_network_gif"
    "nuvio_covers_enabled": False,
    "nuvio_covers_token": "",
    "nuvio_covers_email": "",
    "nuvio_covers_password": "",
    "nuvio_covers_base_url": "https://nuvioapp.space",
    "nuvio_covers_orientation": "all",
    "artwork_provider": "top_posters", # "legacy", "top_posters", "erdb"
    "rpc_image_url_limit": 256,
    "artwork_cache_enabled": True,
    "artwork_cache_size": 1024,
    "artwork_upload_enabled": False,
    "artwork_upload_command": "",
    "artwork_upload_timeout": 45,
    # Top Posters artwork
    "top_posters_enabled": False,
    "top_posters_api_key": "",
    "top_posters_base_url": "https://api.top-posters.com",
    "top_posters_badge_size": "medium",
    "top_posters_badge_position": "bottom-left",
    "top_posters_blur": False,
    "top_posters_style": "modern",
    "top_posters_season_mask_threshold": 32,
    # ERDB artwork
    "erdb_token": "",
    "erdb_base_url": "https://easyratingsdb.com",
    "erdb_episode_id_mode": "realimdb",
    "erdb_validate_remote": False,
    "erdb_posters_enabled": True,
    "erdb_backdrops_enabled": True,
    "erdb_logos_enabled": True,
    "erdb_thumbnails_enabled": True,
    "rpc_branding": "on Stremio",
    # Privacy Mode
    "privacy_mode": False,
    "privacy_hidden_text": "Watching something",
    "privacy_blacklist": [],
    "privacy_pause_analytics": True,
    "privacy_pause_trakt": True,
    # Dashboard Authentication
    "dashboard_auth_enabled": False,
    "dashboard_auth_pin": "",
    # Multi-Activity RPC
    "rpc_activity_type": "watching",
    "rpc_multi_activity_enabled": False,
    # Dynamic Button URLs
    "rpc_dynamic_buttons": [],
    # Status Cycling
    "rpc_cycling_messages": [],
    "rpc_cycling_interval": 30,
    # RPC History
    "rpc_history_enabled": True,
    "rpc_history_limit": 100,
    # Multi-Discord Account
    "rpc_multi_discord_enabled": False,
    "rpc_secondary_client_id": "",
    # Skip Segment Caching
    "skip_cache_ttl": 3600,
    "skip_cache_max_size": 500,
    # Artwork Fallback Chain
    "artwork_fallback_chain": ["top_posters", "erdb", "tmdb", "nuvio"],
    # Config Hot-Reload
    "config_hot_reload": False,
    # Rate Limiting
    "rate_limit_enabled": True,
    "rate_limit_default": "60/minute",
    # TMDB Rate Limiting
    "tmdb_rate_limit_enabled": True,
    "tmdb_rate_limit_calls": 40,
    "tmdb_rate_limit_period": 10,
    # Health Check
    "health_check_enabled": True,
    # Docker / Headless
    "headless_mode": False,
    # API Key Validation
    "api_key_validation_enabled": True,
    # HTTPS
    "dashboard_https_enabled": False,
    "dashboard_cert_path": "",
    "dashboard_key_path": "",
    # Audit Log
    "audit_log_enabled": True,
    "audit_log_max_entries": 1000,
    # Logging
    "log_json_enabled": False,
    "log_level_overrides": {},
    # Config Schema Validation
    "config_schema_validation": True,
    # New API Integrations
    "anilist_enabled": False,
    "anilist_access_token": "",
    "letterboxd_enabled": False,
    "letterboxd_api_key": "",
    "letterboxd_api_secret": "",
    "justwatch_enabled": False,
    "justwatch_country": "US",
    "opensubtitles_enabled": False,
    "opensubtitles_api_key": "",
    "opensubtitles_username": "",
    "opensubtitles_password": "",
    "simkl_enabled": False,
    "simkl_client_id": "",
    "simkl_access_token": "",
    "kitsu_enabled": False,
    "kitsu_access_token": "",
    "lastfm_enabled": False,
    "lastfm_api_key": "",
    "lastfm_api_secret": "",
    "lastfm_session_key": "",
    "plex_enabled": False,
    "plex_url": "",
    "plex_token": "",
    "jellyfin_enabled": False,
    "jellyfin_url": "",
    "jellyfin_api_key": "",
    "emby_enabled": False,
    "emby_url": "",
    "emby_api_key": "",
    "notion_enabled": False,
    "notion_api_key": "",
    "notion_database_id": "",
    "obsidian_enabled": False,
    "obsidian_vault_path": "",
    # Wako Improvements
    "wako_title_overrides": {},
    "wako_title_cache_enabled": True,
    "wako_focus_lock_whitelist": [],
    "wako_focus_lock_cooldown": 5,
    # mDNS Discovery
    "mdns_discovery_enabled": True,
    # ADB Command Queue
    "adb_retry_count": 3,
    "adb_retry_delay": 1.0,
    "adb_command_dedup": True,
    # Multi-Device
    "multi_device_enabled": False,
    "multi_device_list": [],
    # Onboarding
    "onboarding_completed": False,
}

def load_config() -> Dict:
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG) # Save it immediately so user sees it
        return DEFAULT_CONFIG.copy()
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

            return config
    except:
        return DEFAULT_CONFIG.copy()

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
