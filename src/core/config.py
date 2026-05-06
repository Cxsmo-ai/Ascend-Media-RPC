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
