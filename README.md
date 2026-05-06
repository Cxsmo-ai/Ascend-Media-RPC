<div align="center">

# 🌌 Ascend Media RPC

### Discord Rich Presence, Android TV telemetry, Smart Skip, and premium artwork for Stremio & Wako

![Ascend Media RPC Logo](src/web/static/logo.png)

![Platform](https://img.shields.io/badge/platform-Windows-blue)
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
- [What `run.bat` Does](#what-runbat-does)
- [Android TV Setup](#android-tv-setup)
- [Connection Methods](#connection-methods)
- [Configuration](#configuration)
- [Example `config.json`](#example-configjson)
- [API Keys and Providers](#api-keys-and-providers)
- [Using with Stremio](#using-with-stremio)
- [Using with Wako](#using-with-wako)
- [Dashboard](#dashboard)
- [Customization](#customization)
- [Troubleshooting](#troubleshooting)
- [Security and Privacy](#security-and-privacy)
- [Built With](#built-with)
- [Credits](#credits)
- [Disclaimer](#disclaimer)
- [Support](#support)

---

## What Is Ascend Media RPC?

**Ascend Media RPC** is a local Windows application that bridges your Android TV media playback with **Discord Rich Presence**.

When you play something in **Stremio** or **Wako** on Android TV, Ascend Media RPC detects the playback activity, enriches it with metadata and artwork, and updates your Discord status in real time.

It can display:

- Movie, show, season, and episode information
- Playback state
- Elapsed or remaining time
- Posters, backdrops, season art, and episode thumbnails
- Custom Discord branding text
- Small playback, app, network, or device icons
- Smart Skip status
- Real-time telemetry in a local browser dashboard

Ascend Media RPC is designed to make Android TV playback feel more connected, polished, and customizable.

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

> GitHub READMEs do not allow live Discord embeds, iframes, or scripts. For live member/online counts, enable the Discord server widget and add a Shields.io Discord badge using the server ID.

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
      ↓
Ascend Media RPC
      ↓
Discord Rich Presence
```

Official Discord Rich Presence documentation:

```txt
https://docs.discord.com/developers/platform/rich-presence
```

---

## Core Features

### Android TV Telemetry

- Built-in ADB tooling
- No manual ADB installation required
- No manual platform-tools setup required
- Auto IP scanning
- Dashboard-based device scanner
- Manual IP fallback
- Android TV and Google TV support
- NVIDIA Shield support
- Chromecast with Google TV support
- Other Android-based TV device support
- Stremio playback detection
- Wako playback detection
- Playback state tracking
- Progress tracking when available
- Local network connection support
- Device reconnect support
- First-time debugging permission support

---

### Discord Rich Presence

- Live Discord activity updates
- Movie status support
- TV show status support
- Season and episode display
- Custom branding text
- Elapsed time display
- Remaining time display
- Poster artwork support
- Backdrop artwork support
- Season artwork support
- Episode thumbnail support when available
- Small icon modes
- Playback state icons
- App, network, and device icon modes
- Automatic activity refresh when playback changes
- Status clearing or refreshing when playback stops
- Designed for Discord desktop activity status

---

### Real-Time Local Dashboard

Ascend Media RPC includes a local web dashboard for monitoring and control.

Default dashboard URL:

```txt
http://localhost:5466
```

The dashboard can show:

- Android TV connection status
- Device/IP scanner
- Selected device
- Current app
- Current playback metadata
- Playback state
- Playback progress
- Artwork preview
- Discord RPC status
- Skip status
- Smart Skip HUD
- Provider and metadata status

---

### Artwork Engine

Ascend Media RPC includes a multi-source artwork system designed to improve Discord and dashboard visuals.

Supported artwork types may include:

- Movie posters
- TV show posters
- Season posters
- Episode thumbnails
- Backdrops
- Logos
- Rating badges
- Provider-enhanced posters
- Fallback posters

Artwork providers include:

- EasyRatingsDB
- Top Posters
- TMDB fallback artwork

---

### Smart Skip Pipeline

Ascend Media RPC includes a Smart Skip pipeline that can use multiple providers to detect or expose skippable media segments.

Supported skip categories may include:

- Intros
- Outros
- Recaps
- Credits
- Anime openings
- Anime endings
- Jump scares
- Provider-specific skip segments

Supported providers include:

- AniSkip
- IntroDB
- Tidb
- SkipMe
- VideoSkip
- NotScare

---

### NotScare Support

NotScare support is designed for horror content.

It can help expose jump scare information through the Smart Skip pipeline and dashboard HUD.

Useful for:

- Horror movies
- Horror shows
- Jump scare warnings
- Jump scare skip logic
- Dashboard alerts

---

## How It Works

```txt
Android TV / Google TV
        ↓
Stremio or Wako playback
        ↓
Ascend Media RPC built-in ADB tooling
        ↓
Playback and app telemetry
        ↓
Metadata, artwork, ratings, and skip providers
        ↓
Discord Rich Presence + local dashboard
```

Ascend Media RPC runs locally on your Windows PC.

It communicates with your Android TV over your local network using built-in ADB tooling. You do **not** need to manually install ADB or run ADB commands.

Ascend Media RPC can:

1. Scan your local network for Android TV devices
2. Connect automatically using Auto IP mode
3. Let you choose a device from the dashboard scanner
4. Detect Stremio or Wako playback
5. Fetch metadata and artwork from supported providers
6. Update Discord Rich Presence
7. Display live telemetry in the local dashboard

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

These examples show how Ascend Media RPC can enhance media artwork with generated posters, rating overlays, clean layouts, and dashboard-ready visuals.

> The example images should be placed in the repository root, at the same level as `README.md`.

Expected repo layout:

```txt
Ascend-Media-RPC/
├─ README.md
├─ ERDB Example.png
├─ Top Poster Example.png
├─ config.json
├─ run.bat
├─ src/
└─ ...
```

---

## Animated Network Icons with Nuvio

Ascend Media RPC can use Nuvio community GIF covers as animated Discord small icons for streaming networks. This makes the small badge show a matching animated network icon when the show metadata says it is from Netflix, Paramount+, Prime Video, Hulu, Disney+, HBO Max, and similar providers.

Demo animated WebP:

<img src="./Animated%20network%20icons.webp" alt="Animated network icons demo" width="720">

Links:

```txt
https://nuvioapp.space/
https://nuvioapp.space/covers?format=gif&sort=popular
```

Simple setup:

1. Sign up or sign in at Nuvio.
2. Open the local Ascend Media RPC dashboard.
3. Set the small icon or badge mode to the Nuvio network GIF option.
4. Enable Nuvio Network GIFs.
5. Enter your Nuvio email and password in the Nuvio login fields.
6. Save settings and restart or let the next Discord update refresh the icon.

How the Nuvio login works:

1. Create a Nuvio account or sign in at `https://nuvioapp.space/`.
2. Use the same email and password in the Ascend Media RPC dashboard.
3. Ascend Media RPC logs in for you and uses the session to search community GIF covers.
4. If you change your Nuvio password, update it in the dashboard too.

Notes:

- `401` in the log means the Nuvio login failed, expired, or needs the email/password saved again.
- The password field is saved hidden in the dashboard. Enter a new password to replace it.
- `Paramount+` is searched as `Paramount +`, `Paramount`, and `Paramount+` so it can match the community upload names.
- If no animated GIF is found, Ascend Media RPC falls back to the normal static network logo.
- `wsrv.nl` is used for static PNG resizing only. Animated GIFs are handled without `wsrv.nl` because it does not preserve animation.

---

## Requirements

Before using Ascend Media RPC, you need:

- Windows PC
- Discord desktop app installed and running
- Android TV, Google TV, NVIDIA Shield, Chromecast with Google TV, or another Android-based streaming device
- Stremio or Wako installed on the Android TV
- PC and Android TV on the same local network
- Developer Options enabled on the Android TV
- ADB, Network Debugging, or Wireless Debugging enabled on the Android TV
- Optional API keys for artwork, metadata, ratings, and skip features

> You do **not** need to manually install ADB.  
> Ascend Media RPC includes its own ADB tooling and can scan/connect automatically.

---

## Quick Start

1. Download or clone this repository.
2. Enable Developer Options on your Android TV.
3. Enable ADB, Network Debugging, or Wireless Debugging.
4. Open `config.json`.
5. Enable Auto IP scanning:

```json
"auto_ip": true
```

6. Double-click:

```txt
run.bat
```

7. Open the dashboard:

```txt
http://localhost:5466
```

8. Use Auto IP or the dashboard scanner to connect to your Android TV.
9. Start playback in Stremio or Wako.
10. Watch Discord Rich Presence update automatically.

---

## Installation

### Option 1: Download ZIP

1. Click **Code**
2. Click **Download ZIP**
3. Extract the ZIP somewhere easy to access, for example:

```txt
C:\Ascend-Media-RPC
```

4. Open the extracted folder.
5. Edit `config.json`.
6. Double-click `run.bat`.

---

### Option 2: Clone with Git

```bash
git clone https://github.com/Cxsmo-ai/Ascend-Media-RPC.git
cd Ascend-Media-RPC
```

Then edit:

```txt
config.json
```

And run:

```txt
run.bat
```

---

## What `run.bat` Does

`run.bat` is the main launcher for Ascend Media RPC.

It can:

- Prepare the local environment
- Install required dependencies
- Start the Ascend controller
- Use the built-in ADB tooling
- Scan for Android TV devices
- Connect to your selected Android TV
- Start Discord Rich Presence updates
- Start or serve the local dashboard

You do not need a separate setup script.

---

## Android TV Setup

Ascend Media RPC needs Android TV debugging enabled so it can communicate with your device locally.

You do **not** need to type ADB commands manually.

Official Android ADB documentation:

```txt
https://developer.android.com/tools/adb
```

This link is provided for reference only. Ascend Media RPC handles ADB internally.

---

### Step 1: Enable Developer Options

On your Android TV:

1. Open **Settings**
2. Go to **System**, **Device Preferences**, or **About**
3. Find **Android TV OS build**, **Build**, or **Build number**
4. Click it about **7 times**
5. You should see a message similar to:

```txt
You are now a developer!
```

Developer Options are now enabled.

Menu names may vary depending on your device.

---

### Step 2: Enable Debugging

Go to:

```txt
Settings > System > Developer options
```

Enable whichever debugging option your device provides:

```txt
ADB debugging
Network debugging
Wireless debugging
USB debugging
```

For Ascend Media RPC, network or wireless debugging is preferred because the app connects over your local network.

---

### Step 3: Accept the First-Time Permission Prompt

The first time Ascend Media RPC connects, your Android TV may show a permission prompt.

It may say:

```txt
Allow USB debugging?
```

Or:

```txt
Allow network debugging?
```

Select:

```txt
Always allow from this computer
```

Then select:

```txt
Allow
```

After allowing it once, Ascend Media RPC should be able to reconnect automatically later.

---

## Connection Methods

Ascend Media RPC can connect to your Android TV in three ways.

Recommended order:

1. Auto IP scanning
2. Dashboard device scanner
3. Manual IP fallback

---

### Method 1: Auto IP Mode

Open:

```txt
config.json
```

Enable Auto IP:

```json
"auto_ip": true
```

Example:

```json
{
  "auto_ip": true,
  "dashboard_port": 5466,
  "rpc_branding": "on Stremio",
  "rpc_large_image_mode": "season",
  "rpc_time_display": "remaining",
  "wako_mode": false
}
```

Auto IP mode scans your local network for compatible Android TV devices and attempts to connect automatically.

This is the easiest option if:

- Your TV and PC are on the same network
- You mainly use one Android TV device
- You do not want to enter an IP address manually
- Your TV IP address changes sometimes

---

### Method 2: Dashboard Device Scanner

Start Ascend Media RPC:

```txt
run.bat
```

Open:

```txt
http://localhost:5466
```

Use the dashboard scanner to search for Android TV devices on your network.

This is useful if:

- You do not know your Android TV IP
- Your TV IP changes often
- You have multiple Android TV devices
- You want to choose the device visually
- Auto IP finds more than one device

---

### Method 3: Manual IP Fallback

Use manual IP only if Auto IP or the dashboard scanner does not find your Android TV.

To find your Android TV IP:

```txt
Android TV Settings > Network & Internet
```

Select your Wi-Fi or Ethernet network and look for the IP address.

Example:

```txt
192.168.1.50
```

Then open `config.json` and set:

```json
"adb_host": "192.168.1.50"
```

Example manual configuration:

```json
{
  "auto_ip": false,
  "adb_host": "192.168.1.50",
  "dashboard_port": 5466,
  "rpc_branding": "on Stremio",
  "rpc_large_image_mode": "season",
  "rpc_time_display": "remaining",
  "wako_mode": false
}
```

Tip: If you use manual IP, set a static IP or DHCP reservation for your Android TV in your router settings.

---

## Configuration

Open:

```txt
config.json
```

Common options:

| Config Key | Description | Example |
| :--- | :--- | :--- |
| `auto_ip` | Enables automatic Android TV discovery | `true` |
| `adb_host` | Optional manual Android TV IP fallback | `"192.168.1.50"` |
| `dashboard_port` | Local dashboard port | `5466` |
| `rpc_branding` | Text shown in Discord status | `"on Stremio"` |
| `rpc_large_image_mode` | Preferred Discord artwork mode | `"season"` |
| `rpc_small_icon_mode` | Preferred Discord small icon mode | `"content_network_gif"` |
| `rpc_time_display` | Shows remaining or elapsed time | `"remaining"` |
| `wako_mode` | Enables Wako detection mode | `false` |
| `tmdb_api_key` | TMDB API key | `"YOUR_TMDB_API_KEY"` |
| `erdb_token` | EasyRatingsDB token | `"YOUR_ERDB_TOKEN"` |
| `trakt_client_id` | Trakt client ID | `"YOUR_TRAKT_CLIENT_ID"` |
| `mal_client_id` | MyAnimeList client ID | `"YOUR_MAL_CLIENT_ID"` |
| `top_posters_api_key` | Top Posters API key | `"YOUR_TOP_POSTERS_API_KEY"` |
| `nuvio_covers_enabled` | Enables animated Nuvio network icons | `true` |
| `nuvio_covers_email` | Nuvio account email for community GIF covers | `"you@example.com"` |
| `nuvio_covers_password` | Nuvio account password for community GIF covers | `"YOUR_NUVIO_PASSWORD"` |

---

## Example `config.json`

```json
{
  "auto_ip": true,
  "adb_host": "",
  "dashboard_port": 5466,

  "rpc_branding": "on Stremio",
  "rpc_large_image_mode": "season",
  "rpc_small_icon_mode": "content_network_gif",
  "rpc_time_display": "remaining",

  "wako_mode": false,

  "tmdb_api_key": "YOUR_TMDB_API_KEY",
  "erdb_token": "YOUR_ERDB_TOKEN",
  "trakt_client_id": "YOUR_TRAKT_CLIENT_ID",
  "mal_client_id": "YOUR_MAL_CLIENT_ID",
  "top_posters_api_key": "YOUR_TOP_POSTERS_API_KEY",

  "nuvio_covers_enabled": true,
  "nuvio_covers_email": "you@example.com",
  "nuvio_covers_password": "YOUR_NUVIO_PASSWORD",
  "nuvio_covers_base_url": "https://nuvioapp.space",
  "nuvio_covers_orientation": "all"
}
```

---

## API Keys and Providers

API keys are optional, but they unlock better artwork, metadata, ratings, posters, and skip features.

You do not need every key for Ascend Media RPC to launch. Adding more keys improves coverage and quality.

---

### TMDB API Key

TMDB is useful for movie/show metadata and fallback artwork.

Config field:

```json
"tmdb_api_key": "YOUR_TMDB_API_KEY"
```

Links:

```txt
https://www.themoviedb.org/settings/api
https://developer.themoviedb.org/docs/getting-started
```

Basic steps:

1. Create or log in to your TMDB account.
2. Open account settings.
3. Go to the API section.
4. Create or request an API key.
5. Copy the key.
6. Paste it into `config.json`.

---

### EasyRatingsDB Token

EasyRatingsDB can provide high-quality generated artwork and rating-focused media visuals.

Ascend Media RPC can use EasyRatingsDB artwork for richer Discord cards and better dashboard previews.

Example output:

<img src="./ERDB%20Example.png" alt="EasyRatingsDB poster example" width="420">

Useful for:

- Posters
- Backdrops
- Logos
- Thumbnails
- Rating badges
- Addon-style media artwork
- Better dashboard visuals
- Better Discord Rich Presence images

Config field:

```json
"erdb_token": "YOUR_ERDB_TOKEN"
```

Links:

```txt
https://easyratingsdb.com/
https://easyratingsdb.com/configurator
https://easyratingsdb.com/docs
```

Basic steps:

1. Open EasyRatingsDB.
2. Open the configurator/workspace.
3. Register or log in if needed.
4. Create or restore your workspace.
5. Copy your token or config token.
6. Paste it into `config.json`.

---

### Top Posters API Key

Top Posters provides modern generated posters with rating badges and streaming-style layouts.

Ascend Media RPC can use Top Posters artwork to give Discord Rich Presence and the dashboard a more polished streaming-app style.

Example output:

<img src="./Top%20Poster%20Example.png" alt="Top Posters poster example" width="420">

Useful for:

- High-resolution posters
- Movie posters
- TV show posters
- Season posters
- Rating overlays
- Trend indicators
- Modern streaming visuals

Config field:

```json
"top_posters_api_key": "YOUR_TOP_POSTERS_API_KEY"
```

Links:

```txt
https://api.top-streaming.stream/
https://api.top-streaming.stream/user/register
https://api.top-streaming.stream/faq
https://api.top-streaming.stream/api
```

Basic steps:

1. Open the Top Posters registration page.
2. Create an account.
3. Open your dashboard.
4. Copy your API key.
5. Paste it into `config.json`.

---

### Nuvio Animated Network Icons

Nuvio provides community-uploaded GIF covers that can be used as animated Discord small icons for network badges.

Use this when you want the small icon beside your Discord activity to show an animated Netflix, Paramount+, Prime Video, Hulu, Disney+, HBO Max, or similar network badge.

Config fields:

```json
"rpc_small_icon_mode": "content_network_gif",
"nuvio_covers_enabled": true,
"nuvio_covers_email": "you@example.com",
"nuvio_covers_password": "YOUR_NUVIO_PASSWORD"
```

Links:

```txt
https://nuvioapp.space/
https://nuvioapp.space/covers?format=gif&sort=popular
```

Basic steps:

1. Create or sign in to your Nuvio account.
2. Open the Nuvio covers page.
3. Enter your Nuvio email and password in the dashboard Nuvio login fields.
4. Select the Nuvio/network GIF small icon mode.
5. Save settings.

If a GIF is not found for the current network, Ascend Media RPC falls back to the normal static network logo.

---

### Trakt Client ID

Trakt can be used for extra movie/show metadata or watch-related integrations.

Config field:

```json
"trakt_client_id": "YOUR_TRAKT_CLIENT_ID"
```

Links:

```txt
https://trakt.tv/oauth/applications
https://trakt.tv/apps
https://trakt.docs.apiary.io/
```

Basic steps:

1. Log in to Trakt.
2. Open OAuth Applications.
3. Create a new application.
4. Copy the Client ID.
5. Paste it into `config.json`.

---

### MyAnimeList Client ID

MyAnimeList can be used for anime-related metadata.

Config field:

```json
"mal_client_id": "YOUR_MAL_CLIENT_ID"
```

Link:

```txt
https://myanimelist.net/apiconfig
```

Basic steps:

1. Log in to MyAnimeList.
2. Open the API config page.
3. Create an API client.
4. Copy the Client ID.
5. Paste it into `config.json`.

## Using with Stremio

For Stremio, set:

```json
"wako_mode": false
```

Recommended connection setting:

```json
"auto_ip": true
```

Then:

1. Enable debugging on your Android TV.
2. Start Ascend Media RPC with `run.bat`.
3. Open the dashboard:

```txt
http://localhost:5466
```

4. Let Auto IP connect, or choose your TV using the dashboard scanner.
5. Open Stremio on your Android TV.
6. Start playing a movie or episode.
7. Discord Rich Presence should update automatically.

---

## Using with Wako

For Wako, set:

```json
"wako_mode": true
```

Recommended connection setting:

```json
"auto_ip": true
```

Then:

1. Enable debugging on your Android TV.
2. Start Ascend Media RPC with `run.bat`.
3. Open the dashboard:

```txt
http://localhost:5466
```

4. Let Auto IP connect, or choose your TV using the dashboard scanner.
5. Open Wako on your Android TV.
6. Start playback.
7. Discord Rich Presence and dashboard telemetry should update automatically.

Wako mode uses dedicated detection because Wako may expose playback information differently than Stremio.

---

## Dashboard

The dashboard is the local control center for Ascend Media RPC.

Default URL:

```txt
http://localhost:5466
```

The dashboard may show:

- Android TV connection status
- Device/IP scanner
- Selected Android TV device
- Current playback app
- Current title
- Playback state
- Playback progress
- Artwork preview
- Discord RPC status
- Skip status
- Smart Skip HUD
- Provider and metadata status

If you change the dashboard port:

```json
"dashboard_port": 8080
```

Then open:

```txt
http://localhost:8080
```

---

## Customization

### Discord Branding

Controls the text shown in your Discord status.

```json
"rpc_branding": "on Stremio"
```

Examples:

```json
"rpc_branding": "on Android TV"
```

```json
"rpc_branding": "with Ascend"
```

```json
"rpc_branding": "on Wako"
```

---

### Large Image Mode

Controls which artwork type Discord should prefer.

```json
"rpc_large_image_mode": "season"
```

Common artwork modes may include:

```txt
season
show
episode
poster
backdrop
```

Use the values supported by your current app version.

---

### Time Display

Controls whether Discord shows remaining or elapsed time.

```json
"rpc_time_display": "remaining"
```

Common options:

```txt
remaining
elapsed
```

---

### Dashboard Port

Controls the local dashboard port.

```json
"dashboard_port": 5466
```

Default dashboard:

```txt
http://localhost:5466
```

---

## Troubleshooting

### Android TV does not appear in the dashboard scanner

Check that:

- Android TV is turned on
- Android TV is awake
- PC and Android TV are on the same network
- Developer Options are enabled
- ADB, Network Debugging, or Wireless Debugging is enabled
- VPN is not separating your PC from your TV
- Firewall is not blocking local network scanning
- Router allows local device discovery

Try:

1. Restart Ascend Media RPC.
2. Restart your Android TV.
3. Reopen the dashboard.
4. Run the scanner again.
5. Use manual IP fallback if needed.

---

### Auto IP mode does not connect

Confirm this is enabled:

```json
"auto_ip": true
```

Then check:

- Android TV is awake
- Debugging is enabled
- PC and TV are on the same network
- First-time debugging prompt was accepted
- VPN/firewall is not blocking local discovery
- Router is not isolating devices from each other

If Auto IP still fails, use the dashboard scanner or manual IP fallback.

---

### Dashboard scanner finds multiple devices

Choose the Android TV device you use for Stremio or Wako.

Possible detected devices may include:

- Android TV
- Google TV
- NVIDIA Shield
- Chromecast with Google TV
- Fire TV or Android-based TV boxes
- Phones or tablets with debugging enabled

---

### Android TV asks for debugging permission

This is normal the first time.

On the TV, select:

```txt
Always allow from this computer
```

Then select:

```txt
Allow
```

Restart Ascend Media RPC if needed.

---

### Android TV asks for debugging permission every time

Make sure you selected:

```txt
Always allow from this computer
```

If it still asks every time:

- TV debugging permissions may have been reset
- PC network identity may have changed
- Android TV debugging keys may have reset
- VPN or network changes may be affecting the connection

Try disabling and re-enabling debugging on the TV, then accept the prompt again.

---

### Discord Rich Presence does not show

Check that:

- Discord desktop app is open
- You are logged into Discord
- Discord Activity Status is enabled
- Ascend Media RPC is running
- Stremio or Wako is actively playing something
- Android TV is connected in the dashboard
- Another Discord RPC app is not overriding the status

In Discord, check:

```txt
User Settings > Activity Privacy
```

Make sure activity sharing is enabled.

---

### Dashboard does not open

Open it manually:

```txt
http://localhost:5466
```

If you changed the port, use that port instead.

Check that:

- `run.bat` is still running
- The app did not crash
- No other app is using the same port
- Firewall is not blocking local connections

---

### Playback does not update

Check that:

- Stremio or Wako is actively playing
- Correct Android TV device is selected
- TV is awake
- Dashboard shows the TV as connected
- `wako_mode` matches the app you are using

For Stremio:

```json
"wako_mode": false
```

For Wako:

```json
"wako_mode": true
```

---

### Artwork is missing

Check that your API keys are correct:

```json
"tmdb_api_key": "YOUR_TMDB_API_KEY",
"erdb_token": "YOUR_ERDB_TOKEN",
"top_posters_api_key": "YOUR_TOP_POSTERS_API_KEY"
```

Also check:

- Internet connection is working
- Media title is detected correctly
- Title exists in TMDB or the selected artwork provider
- Selected artwork mode is supported
- API provider is not rate-limiting requests

TMDB is useful as a fallback when other providers do not return artwork.

---

### Stremio is not detected correctly

Check:

```json
"wako_mode": false
```

Also confirm:

- Stremio is open
- Playback is active
- Android TV is connected
- Android TV screen is awake
- Dashboard shows the correct selected device

---

### Wako is not detected correctly

Check:

```json
"wako_mode": true
```

Also confirm:

- Wako is open
- Playback is active
- Android TV is connected
- Android TV screen is awake
- Dashboard shows the correct selected device

---

## Security and Privacy

Ascend Media RPC is designed for local use.

It connects to your Android TV over your local network and serves a local dashboard from your PC.

For safety:

- Only enable debugging on trusted home networks
- Do not expose Android TV debugging ports to the internet
- Do not port-forward Android TV debugging through your router
- Only accept debugging prompts from your own computer
- Disable debugging when not using it if you want maximum security
- Do not publicly expose the dashboard port
- Do not share your API keys or tokens publicly

Ascend Media RPC is intended to run on your private local network.

---

## Built With

- Python
- Flask
- pypresence
- Built-in ADB tooling
- Discord Rich Presence
- TMDB
- EasyRatingsDB
- Top Posters
- Nuvio
- Trakt
- MyAnimeList

---

## Credits

Developed by **Cxsmo-ai**.

---

## Disclaimer

This project is not affiliated with Discord, Stremio, Wako, TMDB, Trakt, MyAnimeList, EasyRatingsDB, Top Posters, Nuvio, AniSkip, IntroDB, Tidb, SkipMe, VideoSkip, or NotScare.

All trademarks, names, logos, and brands belong to their respective owners.

Ascend Media RPC does not provide, host, index, distribute, or stream media content. It only detects local playback activity and updates Discord Rich Presence.

---

## Support

If you like this project, consider starring the repository.

```txt
🌌 Ascend Media RPC
Rich Presence Client + Smart Skip + Android TV Telemetry
```
