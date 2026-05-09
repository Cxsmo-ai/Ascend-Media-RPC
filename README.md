<div align="center">

# Ascend Media RPC

### Discord Rich Presence, Android TV telemetry, Smart Skip, and premium artwork for Stremio & Wako

![Ascend Media RPC Logo](src/web/static/logo.png)

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20Docker-blue)
![Python](https://img.shields.io/badge/python-3.x-yellow)
![Android TV](https://img.shields.io/badge/Android%20TV-supported-green)
![Discord RPC](https://img.shields.io/badge/Discord-Rich%20Presence-5865F2)
![Dashboard](https://img.shields.io/badge/dashboard-localhost%3A5466-purple)

**Ascend Media RPC** connects your Android TV media playback to Discord Rich Presence.

Show what you are watching from **Stremio** or **Wako** directly on Discord with live titles, artwork, playback progress, timestamps, custom branding, Smart Skip status, and a real-time local telemetry dashboard.

</div>

---

## Table of Contents

- [What Is Ascend Media RPC?](#what-is-ascend-media-rpc)
- [What Does RPC Mean?](#what-does-rpc-mean)
- [Core Features](#core-features)
- [Discord Community](#discord-community)
- [How It Works](#how-it-works)
- [Artwork Examples](#artwork-examples)
- [Animated Network Icons with Nuvio](#animated-network-icons-with-nuvio)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [What run.bat Does](#what-runbat-does)
- [CLI and Headless Mode](#cli-and-headless-mode)
- [Docker](#docker)
- [Android TV Setup](#android-tv-setup)
- [Connection Methods](#connection-methods)
- [Configuration](#configuration)
- [Example config.json](#example-configjson)
- [API Keys and Providers](#api-keys-and-providers)
- [API Integrations](#api-integrations)
- [Using with Stremio](#using-with-stremio)
- [Using with Wako](#using-with-wako)
- [Dashboard](#dashboard)
- [Smart Skip Pipeline](#smart-skip-pipeline)
- [Analytics](#analytics)
- [Plugin System](#plugin-system)
- [Privacy and Security](#privacy-and-security)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)
- [API Reference](#api-reference)
- [Built With](#built-with)
- [Credits](#credits)
- [Disclaimer](#disclaimer)
- [Support](#support)

---

## What Is Ascend Media RPC?

**Ascend Media RPC** is a local application that bridges your Android TV media playback with **Discord Rich Presence**.

When you play something in **Stremio** or **Wako** on Android TV, Ascend Media RPC detects the playback activity, enriches it with metadata and artwork, and updates your Discord status in real time.

It can display:

- Movie, show, season, and episode information
- Playback state
- Elapsed or remaining time
- Posters, backdrops, season art, and episode thumbnails
- Custom Discord branding text
- Small playback, app, network, or device icons
- Smart Skip status with 8 skip providers
- Real-time telemetry in a local browser dashboard
- Watch history and analytics
- Integration status for 9+ connected services

Ascend Media RPC runs on **Windows** natively, and on **Linux** or any platform via **Docker** or **headless mode**.

---

## Discord Community

Need help, want updates, or want to hang out around the broader Cxsmo-ai projects?

<p align="center">
  <a href="https://DeepAscension.net">
    <img src="https://img.shields.io/badge/Main%20Site-DeepAscension.net-00D4FF?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Visit DeepAscension.net">
  </a>
  <a href="https://discord.gg/njSKPUQtFa">
    <img src="https://img.shields.io/badge/Discord-Share%20Your%20DFM%20Live-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join the Share Your DFM Live Discord server">
  </a>
  <a href="https://throne.com/cxsmo">
    <img src="https://img.shields.io/badge/Support-throne.com%2Fcxsmo-1F8ACB?style=for-the-badge&logo=githubsponsors&logoColor=white" alt="Support through throne.com/cxsmo">
  </a>
</p>

Main site:

```txt
https://DeepAscension.net
```

Support site:

```txt
https://throne.com/cxsmo
```

Join the Discord for project support, release updates, setup help, and community discussion:

```txt
https://discord.gg/njSKPUQtFa
```

---

## What Does RPC Mean?

In this project, **RPC** means:

```txt
Rich Presence Client
```

A Rich Presence Client connects to Discord and updates your profile activity with live, detailed information.

Instead of Discord only showing that you are online, Ascend Media RPC can show what you are currently watching.

Example Discord status:

```txt
Watching Interstellar
1h 12m remaining
on Stremio
```

Flow:

```txt
Stremio / Wako
      |
Ascend Media RPC
      |
Discord Rich Presence
```

Official Discord Rich Presence documentation:

```txt
https://docs.discord.com/developers/platform/rich-presence
```

---

## Core Features

### Android TV Telemetry

- Built-in ADB tooling — no manual ADB installation required
- Auto IP scanning and mDNS/Zeroconf device discovery
- Dashboard-based device scanner with manual IP fallback
- Android TV, Google TV, NVIDIA Shield, and Chromecast with Google TV support
- Stremio and Wako playback detection
- Playback state and progress tracking
- Device reconnect support
- Multi-device management
- ADB command deduplication and retry logic
- First-time debugging permission support

---

### Discord Rich Presence

- Live Discord activity updates for movies and TV shows
- Season and episode display
- Custom branding text
- Elapsed or remaining time display
- Poster, backdrop, season, and episode thumbnail artwork
- Small icon modes: playback state, app, network, device, animated Nuvio GIFs
- Status message cycling with configurable interval
- Dynamic button URLs
- Multi-activity support
- Privacy mode (hides what you are watching)
- RPC history logging
- Profanity filter
- Multi-Discord account support

---

### Real-Time Local Dashboard

Ascend Media RPC includes a local web dashboard with 7 tabs for monitoring and control.

Default URL:

```txt
http://localhost:5466
```

**Dashboard tabs:**

| Tab | Description |
| :--- | :--- |
| **Dashboard** | Connection status, playback info, artwork preview, live log, skip HUD |
| **Connections** | API keys, skip sources with priority reordering, pipeline sandbox, 9 integration cards |
| **Settings** | Appearance, RPC customization, privacy, config management, device management, setup wizard |
| **History** | Watch history and session log |
| **Analytics** | Watch stats, top genres, peak hours heatmap, streaks, search |
| **Debug** | Audit log viewer, skip cache stats, system health, plugins |
| **Trakt** | Trakt OAuth login and scrobbling status |

Dashboard features:

- Toast notification system (replaces alert dialogs)
- Sidebar navigation with icon tooltips
- Config export and import (JSON)
- Multi-step onboarding wizard (6 steps: Welcome, ADB, Discord, TMDB, Artwork, Skip)
- Dark/light/OLED theme toggle with custom accent colors
- Optional PIN-based authentication
- Optional HTTPS support
- Live SSE event stream with real-time UI updates
- Browser push notifications
- Glassmorphism UI with gradient accents and staggered animations

---

### Artwork Engine

Multi-source artwork system for Discord and dashboard visuals.

Supported artwork types:

- Movie and TV show posters
- Season posters and episode thumbnails
- Backdrops and logos
- Rating badges and provider-enhanced posters

Artwork providers:

- **EasyRatingsDB** — rating overlays, generated posters
- **Top Posters** — modern streaming-style posters
- **TMDB** — fallback artwork
- **FanArt.tv** — high-quality fan-made artwork (posters, backgrounds, logos)
- **Nuvio** — animated network GIF icons

Configurable fallback chain with drag-and-drop reordering in the dashboard:

```json
"artwork_fallback_chain": ["tmdb", "fanart", "tvdb"]
```

---

### Smart Skip Pipeline

8-provider skip segment pipeline with priority ordering, category-aware conflict resolution, and TTL caching.

**Supported skip providers:**

| # | Provider | Description |
| :--- | :--- | :--- |
| 1 | **IntroDB.app** | Intro and outro timestamps |
| 2 | **TheIntroDB.org (TIDB)** | Intro, recap, credits, preview, filler segments |
| 3 | **Remote JSON** | Custom skip database from a remote URL |
| 4 | **VideoSkip.org** | Mature content filters (sex, violence, profanity) |
| 5 | **NotScare.me (Major)** | Major jump scare timestamps |
| 6 | **NotScare.me (Minor)** | Minor jump scare timestamps |
| 7 | **AniSkip** | Anime opening and ending skip segments |
| 8 | **SkipMe.db** | Community skip database |

Features:

- Individual enable/disable toggles per provider
- Drag-to-reorder priority in the dashboard
- Cloudflare bypass via cloudscraper for TIDB and NotScare
- Category-aware conflict resolution
- TTL-based skip segment cache (thread-safe)
- Pipeline Sandbox in dashboard for testing

---

### NotScare Support

Jump scare detection for horror content via notscare.me.

- Major and Minor severity levels
- Episode slicing from full season pages
- Cloudflare bypass via cloudscraper
- Dashboard HUD alerts

---

### 9 API Integrations

All manageable from the dashboard Connections tab. Integrations auto-scrobble and sync during active playback — toggling an integration ON actually calls its API methods in the main playback loop.

| Integration | Description |
| :--- | :--- |
| **AniList** | Track anime progress and sync watchlist |
| **Simkl** | Sync watch history across platforms |
| **Kitsu** | Connect to the Kitsu anime community |
| **Letterboxd** | Log movies to your diary as you watch |
| **Last.fm** | Scrobble soundtrack info |
| **JustWatch** | Find where content is streaming |
| **OpenSubtitles** | Find and fetch subtitles |
| **Plex / Jellyfin / Emby** | Media server connections |
| **Notion / Obsidian** | Watch journals and note logging |

---

### Trakt Social

Extended Trakt features beyond basic scrobbling:

- **Collection Sync** — auto-add watched content to your Trakt collection
- **Friends Watching** — see what your Trakt friends are watching right now
- **Calendar** — upcoming episodes from your watchlist
- **Check-In** — auto check-in to Trakt when watching
- **Recommendations** — get personalized recommendations
- **Ratings** — rate content during or after watching
- **Stats** — view your Trakt watch statistics

---

### Analytics

Local SQLite-backed watch analytics:

- Total watch time, session counts, average session duration
- Top genres breakdown
- Peak watch hours (24-hour heatmap)
- Watch streak tracking
- Total skips count
- Session search
- Auto-migration from legacy JSON format
- **Skip provider analytics** — per-provider success rates and hit counts
- **Skip category breakdown** — stats per category (intro, outro, recap, etc.)
- **Weekly reports** — aggregated watch statistics for the past 7 days
- **Monthly reports** — aggregated watch statistics for the past 30 days
- **Shareable stats cards** — generate PNG images of your watch statistics (Spotify Wrapped style)
- **Watch history filter** — filter by status (all, completed, in progress, abandoned)
- **Per-show grouping** — group watch history entries by show title

---

### Core Modules

| Module | Description |
| :--- | :--- |
| audit_log.py | Config change and auth event logging with sensitive key masking |
| skip_cache.py | Thread-safe TTL cache for skip segments |
| rpc_history.py | RPC activity history with SQLite storage |
| api_validator.py | API key validation against provider endpoints |
| config_watcher.py | File system watcher for config hot-reload |
| plugin_system.py | Abstract base classes and registry for extending functionality |
| stats_card_generator.py | Shareable PNG stats card generation (requires Pillow, optional) |
| integrations/fanart.py | FanArt.tv high-quality artwork client |

---

## How It Works

```txt
Android TV / Google TV
        |
Stremio or Wako playback
        |
Ascend Media RPC built-in ADB tooling
        |
Playback and app telemetry
        |
Metadata, artwork, ratings, and skip providers
        |
Discord Rich Presence + Dashboard + Analytics + Integrations
```

Ascend Media RPC runs locally on your PC and communicates with your Android TV over your local network using built-in ADB tooling. You do **not** need to manually install ADB or run ADB commands.

Ascend Media RPC can:

1. Scan your local network for Android TV devices (IP scan + mDNS/Zeroconf)
2. Connect automatically using Auto IP mode
3. Detect Stremio or Wako playback
4. Fetch metadata and artwork from supported providers
5. Fetch skip segments from 8 providers simultaneously
6. Update Discord Rich Presence
7. Display live telemetry in the local dashboard
8. Log watch history and analytics
9. Sync with connected integrations (Trakt, AniList, Last.fm, etc.)

---

## Artwork Examples

Ascend Media RPC can use premium artwork providers to create cleaner, richer visuals for Discord Rich Presence and the local dashboard.

<table>
  <tr>
    <td align="center">
      <strong>EasyRatingsDB Example</strong>
    </td>
    <td align="center">
      <strong>Top Posters Example</strong>
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="./ERDB%20Example.png" alt="EasyRatingsDB poster example" width="360">
    </td>
    <td align="center">
      <img src="./Top%20Poster%20Example.png" alt="Top Posters poster example" width="360">
    </td>
  </tr>
</table>

---

## Animated Network Icons with Nuvio

Ascend Media RPC can use Nuvio community GIF covers as animated Discord small icons for streaming networks (Netflix, Paramount+, Prime Video, Hulu, Disney+, HBO Max, etc.).

Demo animated WebP:

<img src="./Animated%20network%20icons.webp" alt="Animated network icons demo" width="720">

Links:

```txt
https://nuvioapp.space/
https://nuvioapp.space/covers?format=gif&sort=popular
```

Setup:

1. Sign up or sign in at Nuvio.
2. Open the Ascend Media RPC dashboard.
3. Set the small icon mode to the Nuvio network GIF option.
4. Enable Nuvio Network GIFs.
5. Enter your Nuvio email and password.
6. Save settings.

Notes:

- 401 in the log means the Nuvio login failed or expired.
- If no animated GIF is found, Ascend Media RPC falls back to a static network logo.
- wsrv.nl is used for static PNG resizing only. Animated GIFs are handled without wsrv.nl.

---

## Requirements

- Windows PC, Linux machine, or Docker environment
- Discord desktop app installed and running (for RPC features)
- Android TV, Google TV, NVIDIA Shield, Chromecast with Google TV, or another Android-based streaming device
- Stremio or Wako installed on the Android TV
- PC and Android TV on the same local network
- Developer Options and ADB/Network/Wireless Debugging enabled on the Android TV
- Python 3.x (if running without Docker)
- Optional API keys for artwork, metadata, ratings, and skip features

> You do **not** need to manually install ADB. Ascend Media RPC includes its own ADB tooling.

---

## Quick Start

1. Download or clone this repository.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Enable Developer Options on your Android TV.
4. Enable ADB, Network Debugging, or Wireless Debugging.
5. Open config.json and configure your settings.
6. Run the app:

**Windows:**

```
run.bat
```

**Any platform (headless):**

```bash
python start_gui.py --headless
```

**Docker:**

```bash
docker-compose up -d
```

7. Open the dashboard:

```
http://localhost:5466
```

8. Connect to your Android TV and start playback.

---

## Installation

### Option 1: Download ZIP

1. Click **Code** then **Download ZIP**
2. Extract the ZIP
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Edit config.json
5. Double-click run.bat

### Option 2: Clone with Git

```bash
git clone https://github.com/Cxsmo-ai/Ascend-Media-RPC.git
cd Ascend-Media-RPC
pip install -r requirements.txt
```

Edit config.json, then run run.bat or python start_gui.py --headless.

### Option 3: Docker

See the [Docker](#docker) section below.

---

## What run.bat Does

run.bat is the main launcher for Ascend Media RPC on Windows. It prepares the local environment, installs dependencies, starts the controller, connects to your Android TV via built-in ADB tooling, starts Discord Rich Presence updates, and serves the local dashboard.

---

## CLI and Headless Mode

Ascend Media RPC supports CLI arguments and a headless mode for running without a GUI.

```bash
python start_gui.py [options]
```

| Flag | Description | Example |
| :--- | :--- | :--- |
| --headless | Run without GUI (Flask API only) | python start_gui.py --headless |
| --config PATH | Use a custom config file | python start_gui.py --config /path/to/config.json |
| --port PORT | Override dashboard port | python start_gui.py --port 8080 |
| --host HOST | Override ADB host address | python start_gui.py --host 192.168.1.50 |

Headless mode is useful for Linux servers, Docker containers, and environments without a display.

Environment variables also work:

```bash
HEADLESS=1 python start_gui.py
```

---

## Docker

Ascend Media RPC includes Docker support for containerized deployment.

### Docker Compose (recommended)

```bash
docker-compose up -d
```

The docker-compose.yml includes:

- Health checks every 30 seconds
- Automatic restart on failure
- Host network mode (required for ADB and Discord IPC)
- Volume mount for persistent config

### Manual Docker build

```bash
docker build -t ascend-media-rpc .
docker run -d --network host --name ascend-rpc ascend-media-rpc
```

The container uses Python 3.11 slim, runs in headless mode by default, exposes port 5466, and includes a health check at /api/health.

### Docker environment variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| HEADLESS | Run in headless mode | 1 |
| GUI_MODE | UI mode | browser |
| ASCEND_PORT | Dashboard port override | — |
| ASCEND_ADB_HOST | ADB host override | — |
| ASCEND_CONFIG_PATH | Config file path override | — |

> **Note:** network_mode: host is required for ADB device communication and Discord IPC.

---

## Android TV Setup

Ascend Media RPC needs Android TV debugging enabled so it can communicate with your device locally. You do **not** need to type ADB commands manually.

### Step 1: Enable Developer Options

On your Android TV:

1. Open **Settings**
2. Go to **System**, **Device Preferences**, or **About**
3. Find **Android TV OS build** or **Build number**
4. Click it about **7 times**
5. You should see: You are now a developer!

### Step 2: Enable Debugging

Go to Settings then System then Developer options and enable whichever debugging option your device provides (ADB debugging, Network debugging, or Wireless debugging).

### Step 3: Accept the First-Time Permission Prompt

The first time Ascend Media RPC connects, your Android TV will show a permission prompt. Select **Always allow from this computer**, then **Allow**.

---

## Connection Methods

Ascend Media RPC can connect to your Android TV in four ways:

### Method 1: Auto IP Mode

```json
"auto_ip": true
```

Scans your local network for compatible Android TV devices and connects automatically. Easiest option for most setups.

### Method 2: mDNS/Zeroconf Discovery

```json
"mdns_discovery_enabled": true
```

Uses Zeroconf to find Android TV devices broadcasting _adb._tcp services. Faster and more reliable than IP scanning on some networks.

### Method 3: Dashboard Device Scanner

Open the dashboard at http://localhost:5466 and use the built-in scanner to find and select your device.

### Method 4: Manual IP Fallback

Find your Android TV IP in Settings then Network & Internet, then set:

```json
"adb_host": "192.168.1.50"
```

---

## Configuration

Ascend Media RPC uses a single **config.json** file in the project root. All settings are managed from this one file — there is no second config file. The Python module src/core/config.py is the code that loads, saves, and validates config.json.

The config is organized into 12 labeled sections:

1. **ADB / Device Connection** — host, port, retry, mDNS, multi-device
2. **Metadata Providers** — TMDB, MAL API keys and rate limits
3. **Discord RPC** — branding, icons, buttons, cycling, history, privacy
4. **Skip Providers** — provider toggles, priority order, cache settings
5. **Artwork & Covers** — provider, fallback chain, Top Posters, ERDB, Nuvio
6. **Wako Mode** — Wako-specific detection settings
7. **API Integrations — Tracking** — AniList, Simkl, Kitsu, Letterboxd, Last.fm
8. **API Integrations — Discovery** — JustWatch, OpenSubtitles
9. **API Integrations — Media Servers** — Plex, Jellyfin, Emby
10. **API Integrations — Journals** — Notion, Obsidian
11. **Privacy & Security** — privacy mode, dashboard auth, blacklist
12. **Dashboard & System** — port, HTTPS, headless, rate limiting, audit log, health check

Config features:

- **Validation** — warns about invalid values and unknown keys
- **Export** — export config as JSON (sensitive keys excluded)
- **Import** — import config from JSON, merged with current config
- **Hot-reload** — watch config file for changes and reload automatically (config_hot_reload: true)
- **Schema validation** — validates config keys against the default schema
- **Migration** — automatically migrates legacy key names

---

## Example config.json

```json
{
    "auto_ip": true,
    "adb_host": "",
    "adb_port": 5555,
    "dashboard_port": 5466,

    "tmdb_api_key": "YOUR_TMDB_API_KEY",
    "mal_client_id": "YOUR_MAL_CLIENT_ID",
    "erdb_token": "YOUR_ERDB_TOKEN",
    "top_posters_api_key": "YOUR_TOP_POSTERS_API_KEY",

    "discord_client_id": "",
    "rpc_branding": "on Stremio",
    "rpc_large_image_mode": "season",
    "rpc_small_icon_mode": "content_network_gif",
    "rpc_time_display": "remaining",

    "nuvio_covers_enabled": true,
    "nuvio_covers_email": "you@example.com",
    "nuvio_covers_password": "YOUR_NUVIO_PASSWORD",

    "introdb_enabled": true,
    "tidb_enabled": true,
    "videoskip_enabled": true,
    "notscare_major_enabled": true,
    "notscare_minor_enabled": true,
    "aniskip_enabled": false,
    "skipme_enabled": true,

    "wako_mode": false,

    "anilist_enabled": false,
    "simkl_enabled": false,
    "kitsu_enabled": false,
    "letterboxd_enabled": false,
    "lastfm_enabled": false,
    "justwatch_enabled": false,
    "opensubtitles_enabled": false,
    "plex_enabled": false,
    "jellyfin_enabled": false,
    "emby_enabled": false,
    "notion_enabled": false,
    "obsidian_enabled": false,

    "privacy_mode": false,
    "dashboard_auth_enabled": false,
    "audit_log_enabled": true,
    "config_hot_reload": false
}
```

---

## API Keys and Providers

API keys are optional but unlock better artwork, metadata, ratings, and skip features. You do not need every key for Ascend Media RPC to launch.

### TMDB API Key

TMDB provides movie/show metadata and fallback artwork.

```json
"tmdb_api_key": "YOUR_TMDB_API_KEY"
```

Get your key at: https://www.themoviedb.org/settings/api

### EasyRatingsDB Token

EasyRatingsDB provides generated artwork with rating overlays.

```json
"erdb_token": "YOUR_ERDB_TOKEN"
```

Get your token at: https://easyratingsdb.com/configurator

### Top Posters API Key

Top Posters provides modern streaming-style posters with rating badges.

```json
"top_posters_api_key": "YOUR_TOP_POSTERS_API_KEY"
```

Get your key at: https://api.top-streaming.stream/user/register

### Nuvio (Animated Network Icons)

Nuvio provides community GIF covers for animated Discord network badges.

```json
"nuvio_covers_enabled": true,
"nuvio_covers_email": "you@example.com",
"nuvio_covers_password": "YOUR_NUVIO_PASSWORD"
```

Sign up at: https://nuvioapp.space/

### Trakt

Trakt provides metadata and scrobbling with automatic token refresh.

```json
"trakt_client_id": "YOUR_TRAKT_CLIENT_ID",
"trakt_client_secret": "YOUR_TRAKT_CLIENT_SECRET"
```

Create an app at: https://trakt.tv/oauth/applications

### MyAnimeList

MyAnimeList provides anime metadata.

```json
"mal_client_id": "YOUR_MAL_CLIENT_ID"
```

Get your key at: https://myanimelist.net/apiconfig

---

## API Integrations

### AniList

Track anime progress and sync your watchlist automatically via the AniList GraphQL API.

```json
"anilist_enabled": true,
"anilist_access_token": "YOUR_ANILIST_TOKEN"
```

Get your token at: https://anilist.co/settings/developer

### Simkl

Sync watch history across TV, movies, and anime platforms.

```json
"simkl_enabled": true,
"simkl_client_id": "YOUR_SIMKL_CLIENT_ID",
"simkl_access_token": "YOUR_SIMKL_TOKEN"
```

Get your key at: https://simkl.com/settings/developer/

### Kitsu

Connect to the Kitsu anime community and library.

```json
"kitsu_enabled": true,
"kitsu_access_token": "YOUR_KITSU_TOKEN"
```

### Letterboxd

Log movies to your Letterboxd diary as you watch.

```json
"letterboxd_enabled": true,
"letterboxd_api_key": "YOUR_LETTERBOXD_KEY",
"letterboxd_api_secret": "YOUR_LETTERBOXD_SECRET"
```

### Last.fm

Scrobble soundtrack and score info to Last.fm.

```json
"lastfm_enabled": true,
"lastfm_api_key": "YOUR_LASTFM_KEY",
"lastfm_api_secret": "YOUR_LASTFM_SECRET"
```

Get your key at: https://www.last.fm/api/account/create

### JustWatch

Find where movies and shows are streaming in your country.

```json
"justwatch_enabled": true,
"justwatch_country": "US"
```

No API key required — uses public data.

### OpenSubtitles

Find and fetch subtitles for your media.

```json
"opensubtitles_enabled": true,
"opensubtitles_api_key": "YOUR_OPENSUBTITLES_KEY",
"opensubtitles_username": "YOUR_USERNAME",
"opensubtitles_password": "YOUR_PASSWORD"
```

Get your key at: https://www.opensubtitles.com/en/consumers

### Plex / Jellyfin / Emby

Connect to your media server for playback sync.

**Plex:**

```json
"plex_enabled": true,
"plex_url": "http://192.168.1.100:32400",
"plex_token": "YOUR_PLEX_TOKEN"
```

**Jellyfin:**

```json
"jellyfin_enabled": true,
"jellyfin_url": "http://192.168.1.100:8096",
"jellyfin_api_key": "YOUR_JELLYFIN_KEY"
```

**Emby:**

```json
"emby_enabled": true,
"emby_url": "http://192.168.1.100:8096",
"emby_api_key": "YOUR_EMBY_KEY"
```

### Notion

Log watch activity to a Notion database.

```json
"notion_enabled": true,
"notion_api_key": "YOUR_NOTION_KEY",
"notion_database_id": "YOUR_DATABASE_ID"
```

### Obsidian

Write watch notes to an Obsidian vault folder.

```json
"obsidian_enabled": true,
"obsidian_vault_path": "/path/to/your/vault"
```

### FanArt.tv

High-quality fan-made artwork for movies and TV shows.

```json
"fanart_enabled": true,
"fanart_api_key": "YOUR_FANART_API_KEY"
```

Get your key at: https://fanart.tv/get-an-api-key/

All integrations can be enabled/disabled from the dashboard Connections tab. They initialize lazily in a background thread only when their enabled flag is true.

---

## Using with Stremio

```json
"wako_mode": false
```

1. Enable debugging on your Android TV.
2. Start Ascend Media RPC (run.bat or python start_gui.py --headless).
3. Open the dashboard at http://localhost:5466.
4. Connect to your Android TV.
5. Start playing in Stremio.
6. Discord Rich Presence updates automatically.

---

## Using with Wako

```json
"wako_mode": true
```

1. Enable debugging on your Android TV.
2. Start Ascend Media RPC.
3. Open the dashboard.
4. Connect to your Android TV.
5. Start playback in Wako.
6. Discord Rich Presence updates automatically.

Wako-specific config options:

| Config Key | Description |
| :--- | :--- |
| wako_player_only | Only detect player activity |
| wako_stay_awake_on_pause | Keep device awake when paused |
| wako_focus_lock | Lock focus to Wako app |
| wako_title_overrides | Manual title corrections |
| wako_title_cache_enabled | Cache parsed titles |
| wako_focus_lock_whitelist | Apps allowed when focus lock is on |
| wako_focus_lock_cooldown | Cooldown between focus checks (seconds) |

---

## Dashboard

The dashboard is the local control center for Ascend Media RPC at http://localhost:5466.

### Dashboard Tab

Connection status, device scanner, playback info (app, title, state, progress), artwork preview, Discord RPC status, Smart Skip HUD, and live log.

### Connections Tab

- **Core APIs** — TMDB, MAL, Trakt, Discord credential inputs
- **Skip Sources** — Provider priority list with reorder arrows and toggles, provider config (API keys, URLs, TMDB/MAL ID overrides), Pipeline Sandbox for testing
- **Tracking & Scrobbling** — AniList, Simkl, Kitsu, Letterboxd, Last.fm cards with toggles and descriptions
- **Discovery & Utilities** — JustWatch, OpenSubtitles cards
- **Media Servers** — Plex, Jellyfin, Emby cards
- **Watch Journals** — Notion, Obsidian cards
- **Trakt Social** — collection sync, friends watching, calendar, check-in cards with toggles
- **Integration Status** — overview grid showing connected/disconnected status

### Settings Tab

Appearance and theme (dark/light/OLED mode, accent color picker), RPC customization, skip category per-category toggles (8 categories: intro, outro, recap, preview, credits, filler, mature content, jump scares), artwork fallback chain configuration with drag reordering, FanArt.tv settings (enable toggle, API key), device health monitoring (battery, CPU, memory, storage), ADB Wi-Fi pairing wizard, push notification toggle, privacy mode, dashboard PIN authentication, config export/import, and multi-step setup wizard.

### History Tab

Watch history entries and session log with filter buttons (All, Completed, In Progress, Abandoned) and per-show grouping view.

### Analytics Tab

Total watch time, top genres, peak watch hours heatmap, watch streak, total skips, average session duration, session search, skip provider stats (per-provider success rates), skip category breakdown, weekly and monthly reports, and shareable stats card generator (PNG).

### Debug Tab

Audit log viewer (searchable, filterable), skip cache statistics (hit rate, size, clear button), system health (uptime, status), plugin list, and log export (last 50, last 200, or all logs as JSON download).

### Trakt Tab

Trakt OAuth login flow and scrobbling status.

---

## Smart Skip Pipeline

The Smart Skip pipeline fetches skip segments from up to 8 providers simultaneously using a thread pool executor.

### How It Works

1. When playback starts, Ascend Media RPC resolves the media IMDB ID (via TMDB lookup or manual override).
2. All enabled providers are queried in parallel.
3. Results are merged using category-aware conflict resolution:
   - Segments of **different categories** (e.g. structure vs mature content) are all kept.
   - Segments of the **same category** that overlap are resolved by provider priority order.
4. Results are cached using a TTL-based cache (default 1 hour, configurable).

### Pipeline Sandbox

The dashboard includes a Pipeline Sandbox for testing skip providers without active playback:

1. Go to the **Connections** tab.
2. Scroll to **Pipeline Sandbox**.
3. Enter a title (e.g. Stranger Things), season, and episode.
4. Click **Run Pipeline Test**.
5. View color-coded results grouped by source.

### Provider Details

| Provider | Notes |
| :--- | :--- |
| **IntroDB.app** | Intro/outro timestamps for TV episodes |
| **TheIntroDB.org (TIDB)** | Cloudflare-protected; uses cloudscraper for bypass |
| **Remote JSON** | Custom URL for your own skip database |
| **VideoSkip.org** | Mature content markers (sex, violence, profanity) |
| **NotScare.me** | Cloudflare-protected; uses cloudscraper. Supports episode slicing from season pages |
| **AniSkip** | Requires MAL ID for anime lookups |
| **SkipMe.db** | Community skip segment database |

---

## Analytics

Ascend Media RPC stores watch analytics in a local SQLite database (analytics.db).

- **SQLite backend** with WAL mode and indexed columns
- **Automatic migration** from legacy JSON format
- **Watch stats** — total sessions, total watch time, average session
- **Top genres** — genre breakdown from TMDB metadata
- **Peak hours** — 24-hour heatmap
- **Watch streak** — consecutive days of watching
- **Total skips** — count of all skipped segments
- **Search** — search sessions by title, genre, or date

View analytics in the **Analytics** tab of the dashboard.

---

## Plugin System

Ascend Media RPC includes a plugin system for extending functionality.

| Plugin Type | Base Class | Description |
| :--- | :--- | :--- |
| Metadata | MetadataProvider | Custom metadata sources |
| Skip | SkipProvider | Custom skip segment sources |
| Scrobble | ScrobbleProvider | Custom scrobbling destinations |
| Artwork | ArtworkProvider | Custom artwork sources |

Plugins are loaded from a configurable directory via the PluginRegistry. The plugin list is visible in the **Debug** tab.

> The plugin system provides the base classes and registry. No concrete plugins are bundled — this is scaffolding for community extensions.

---

## Privacy and Security

### Privacy Mode

Hide what you are watching from Discord:

```json
"privacy_mode": true,
"privacy_hidden_text": "Watching something"
```

Privacy mode can also blacklist specific titles, pause analytics, and pause Trakt scrobbling.

### Dashboard Authentication

Protect your dashboard with a PIN:

```json
"dashboard_auth_enabled": true,
"dashboard_auth_pin": "1234"
```

### HTTPS Support

Enable HTTPS for the dashboard:

```json
"dashboard_https_enabled": true,
"dashboard_cert_path": "/path/to/cert.pem",
"dashboard_key_path": "/path/to/key.pem"
```

### Audit Log

Track config changes and auth events with sensitive key masking:

```json
"audit_log_enabled": true,
"audit_log_max_entries": 1000
```

View the audit log in the **Debug** tab.

### API Rate Limiting

```json
"rate_limit_enabled": true,
"rate_limit_default": "60/minute"
```

### General Safety

- Only enable debugging on trusted home networks
- Do not expose Android TV debugging ports to the internet
- Do not publicly expose the dashboard port
- Do not share API keys or tokens publicly

---

## Customization

### Discord Branding

```json
"rpc_branding": "on Stremio"
```

### Large Image Mode

```json
"rpc_large_image_mode": "season"
```

Options: show, season, episode

### Time Display

```json
"rpc_time_display": "remaining"
```

Options: remaining, elapsed

### Dashboard Port

```json
"dashboard_port": 5466
```

### Status Message Cycling

```json
"rpc_status_cycling_enabled": true,
"rpc_cycling_messages": ["Chilling", "Binge watching", "Movie night"],
"rpc_cycling_interval": 30
```

### Dynamic Buttons

```json
"rpc_dynamic_buttons": [
  {"label": "My Profile", "url": "https://example.com"}
]
```

---

## Troubleshooting

### Android TV does not appear in the dashboard scanner

- Android TV is turned on and awake
- PC and Android TV are on the same network
- Developer Options and debugging are enabled
- VPN/firewall is not blocking local discovery
- Try enabling mDNS discovery (mdns_discovery_enabled: true)
- Try manual IP fallback

### Auto IP mode does not connect

- Confirm auto_ip: true
- Debugging is enabled on the TV
- First-time debugging prompt was accepted
- Try mDNS discovery or manual IP

### Discord Rich Presence does not show

- Discord desktop app is open and logged in
- Activity Status is enabled in Discord settings (User Settings then Activity Privacy)
- Ascend Media RPC is running
- Stremio or Wako is actively playing
- Another Discord RPC app is not overriding the status

### Dashboard does not open

- Check run.bat or start_gui.py is still running
- Try http://localhost:5466 (or your custom port)
- No other app is using the same port

### Playback does not update

- Correct Android TV device is selected
- wako_mode matches the app you are using (false for Stremio, true for Wako)
- TV is awake

### Artwork is missing

- API keys are correct in config.json
- Internet connection is working
- Media exists in TMDB or selected artwork provider
- Try TMDB as fallback

### Skip providers returning 0 segments

- Provider is enabled in config or dashboard
- Media has data in that provider database
- For TIDB/NotScare: cloudscraper is installed (pip install cloudscraper)
- For TIDB: Cloudflare may IP-block certain networks
- For AniSkip: valid MAL ID is required
- Check server logs for errors

---

## API Reference

Ascend Media RPC exposes a REST API for the dashboard and external integrations.

### Core

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| GET | /api/health | Health check (uptime, version, status) |
| GET | /api/state | Current app state (playback, config, metadata) |
| POST | /api/update_settings | Update config values |
| GET | /api/events | SSE event stream for live updates |

### Config Management

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| GET | /api/config/export | Export config as JSON (sensitive keys excluded) |
| POST | /api/config/import | Import config from JSON |
| GET | /api/config/validate | Validate current config |
| GET | /api/config/schema | Get config schema with types |

### Skip Pipeline

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| POST | /api/test/skip_pipeline | Test skip pipeline (title, season, episode) |
| GET | /api/skip/cache | Skip cache statistics |
| DELETE | /api/skip/cache | Clear skip cache |

### Analytics

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| GET | /api/analytics/advanced | Full analytics (genres, hours, streaks, stats) |
| GET | /api/analytics/search?q=QUERY | Search watch sessions |

### System

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| GET | /api/audit | Audit log entries |
| GET | /api/rpc/history | RPC activity history |
| POST | /api/validate/keys | Validate API keys |
| GET | /api/plugins | List loaded plugins |
| GET | /api/integrations/status | Integration connection status |
| GET | /api/devices | List discovered devices |
| POST | /api/devices/switch | Switch active device |

### Authentication

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| POST | /api/auth/login | Dashboard PIN login |
| POST | /api/auth/logout | Dashboard logout |

### Onboarding

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| GET | /api/onboarding/status | Onboarding progress |
| POST | /api/onboarding/start | Start setup wizard |
| POST | /api/onboarding/complete | Mark onboarding complete |

### Trakt Social

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| GET | /api/trakt/collection | Get Trakt collection |
| POST | /api/trakt/collection | Add to Trakt collection |
| POST | /api/trakt/checkin | Check in to Trakt |
| GET | /api/trakt/friends | Friends watching now |
| GET | /api/trakt/calendar | Upcoming episodes |
| GET | /api/trakt/recommendations | Personalized recommendations |
| POST | /api/trakt/rate | Rate content |
| GET | /api/trakt/stats | Trakt watch stats |

### Skip Analytics

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| GET | /api/analytics/skip/providers | Per-provider skip stats |
| GET | /api/analytics/skip/categories | Per-category skip breakdown |
| GET | /api/analytics/report/weekly | Weekly watch report |
| GET | /api/analytics/report/monthly | Monthly watch report |

### Watch History

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| GET | /api/history/filter?status=STATUS | Filter history (completed/in_progress/abandoned) |
| GET | /api/history/grouped | History grouped by show |

### Device Management

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| GET | /api/device/health | Device health (battery, CPU, memory, storage) |
| POST | /api/device/adb-pair | ADB Wi-Fi pairing (IP:port + code) |

### Remote Control

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| POST | /api/remote/text | Send text input to device |
| POST | /api/remote/launch | Launch app on device |
| GET | /api/remote/apps | List installed apps |

### Artwork & Theme

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| GET | /api/fanart/images | Fetch FanArt.tv images for a title |
| GET | /api/artwork/chain | Get artwork fallback chain order |
| POST | /api/artwork/chain | Set artwork fallback chain order |
| GET | /api/theme | Get current theme settings |
| POST | /api/theme | Update theme (mode, accent, OLED) |

### Stats & Logs

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| POST | /api/stats-card | Generate shareable stats card (PNG) |
| GET | /api/logs?limit=N | Get recent logs |
| GET | /api/logs/export?limit=N | Export logs as JSON download |

---

## Built With

- Python
- Flask
- pypresence
- cloudscraper
- guessit
- anitopy
- SQLite
- Zeroconf
- Pillow (optional, for stats card PNG generation)
- Built-in ADB tooling
- Discord Rich Presence
- TMDB, EasyRatingsDB, Top Posters, FanArt.tv, Nuvio
- Trakt, MyAnimeList
- AniList, Simkl, Kitsu, Letterboxd, Last.fm, JustWatch, OpenSubtitles
- Plex, Jellyfin, Emby
- Notion, Obsidian
- IntroDB, TheIntroDB.org, VideoSkip, NotScare, AniSkip, SkipMe

---

## Credits

Developed by **Cxsmo-ai**.

---

## Disclaimer

This project is not affiliated with Discord, Stremio, Wako, TMDB, Trakt, MyAnimeList, EasyRatingsDB, Top Posters, FanArt.tv, Nuvio, AniSkip, IntroDB, TheIntroDB.org, SkipMe, VideoSkip, NotScare, AniList, Simkl, Kitsu, Letterboxd, Last.fm, JustWatch, OpenSubtitles, Plex, Jellyfin, Emby, Notion, or Obsidian.

All trademarks, names, logos, and brands belong to their respective owners.

Ascend Media RPC does not provide, host, index, distribute, or stream media content. It only detects local playback activity and updates Discord Rich Presence.

---

## Support

If you like this project, consider starring the repository.

```txt
Ascend Media RPC
Rich Presence Client + Smart Skip + Android TV Telemetry + Analytics + Integrations
```
