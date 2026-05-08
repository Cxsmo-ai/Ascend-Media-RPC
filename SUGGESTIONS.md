# Ascend Media RPC - Feature & API Suggestions

> A comprehensive collection of feature ideas, API integration opportunities, and architectural improvements for Ascend Media RPC, compiled from a deep analysis of the entire codebase.

---

## Table of Contents

- [1. Discord RPC Enhancements](#1-discord-rpc-enhancements)
- [2. ADB & Device Management](#2-adb--device-management)
- [3. Metadata & Artwork Pipeline](#3-metadata--artwork-pipeline)
- [4. Skip Segment System](#4-skip-segment-system)
- [5. Trakt Integration](#5-trakt-integration)
- [6. Watch Party System](#6-watch-party-system)
- [7. Smart Home Integration](#7-smart-home-integration)
- [8. Dashboard & Web UI](#8-dashboard--web-ui)
- [9. Analytics & History](#9-analytics--history)
- [10. Wako Mode](#10-wako-mode)
- [11. New API Integrations](#11-new-api-integrations)
- [12. Architecture & Performance](#12-architecture--performance)
- [13. Security & Privacy](#13-security--privacy)
- [14. Developer Experience](#14-developer-experience)

---

## 1. Discord RPC Enhancements

### 1.1 Multi-Activity Support
**Current:** Single activity displayed at a time via `pypresence`.
**Suggestion:** Support Discord's newer Activity types beyond just "Playing" / "Streaming". Allow users to choose between Watching, Listening, and Competing activity types based on content type (e.g., music videos as "Listening", sports as "Competing").

### 1.2 Rich Presence Buttons - Dynamic URLs
**Current:** RPC buttons link to static URLs (TMDB page, trailer).
**Suggestion:**
- Add a "Watch Together" button that generates a watch party invite link.
- Add configurable button templates (e.g., link to Letterboxd, Trakt, or a custom URL with `{imdb_id}` / `{title}` placeholders).
- Allow per-content-type button configurations (movies vs. TV shows vs. anime).

### 1.3 Status Cycling Improvements
**Current:** `rpc_status_cycling_enabled` exists but cycling options are limited.
**Suggestion:**
- Allow users to define custom cycling messages with template variables (`{title}`, `{episode}`, `{progress}`, `{device}`, `{network}`, `{genre}`, `{rating}`).
- Add cycling speed configuration (interval between rotations).
- Support conditional messages (e.g., show rating only when available, show genre only for movies).

### 1.4 Multi-Discord-Account Support
**Current:** Single `discord_client_id` (with a separate one for Wako).
**Suggestion:** Allow a list of Discord Client IDs to broadcast to multiple Discord accounts simultaneously (useful for users with personal and community accounts).

### 1.5 RPC History / Activity Log
**Current:** RPC payloads are sent and forgotten.
**Suggestion:** Keep a local log of all RPC updates sent to Discord (title, timestamp, duration watched) to allow users to view their Discord presence history on the dashboard.

---

## 2. ADB & Device Management

### 2.1 Multi-Device Support
**Current:** Single `adb_host`/`adb_port` connection.
**Suggestion:**
- Support connecting to multiple Android TV devices simultaneously.
- Allow per-device Discord Client IDs (e.g., living room TV uses one app, bedroom another).
- Show a device selector on the dashboard with live status for each device.
- Priority-based active device selection (auto-switch to whichever device is actively playing).

### 2.2 mDNS / Zeroconf Auto-Discovery
**Current:** `ADBDiscovery` does a brute-force subnet scan (1-254) checking port 5555.
**Suggestion:**
- Use mDNS/Zeroconf to discover Android TV devices on the network via `_adb._tcp` service type (the `zeroconf` library is already in `requirements.txt`).
- Cache discovered devices and show a dropdown on the dashboard.
- Auto-reconnect to the last-known device on startup without requiring manual IP entry.

### 2.3 ADB over Wi-Fi Pairing Flow
**Current:** Users must manually enable ADB debugging and find the device IP.
**Suggestion:** Add a guided pairing wizard in the dashboard that walks users through enabling wireless debugging on their Android TV, including QR code pairing support for Android 11+ devices.

### 2.4 Device Health Monitoring
**Current:** Basic connected/disconnected status.
**Suggestion:**
- Show device battery level (for portable devices), CPU temperature, memory usage, and storage via ADB shell commands.
- Add a device uptime indicator.
- Network latency indicator (ping time to ADB device).

### 2.5 ADB Command Queue
**Current:** ADB commands are fire-and-forget with bare `try/except`.
**Suggestion:** Implement a command queue with retry logic, timeout management, and command deduplication to prevent duplicate key events and improve reliability during network hiccups.

---

## 3. Metadata & Artwork Pipeline

### 3.1 Artwork Provider Fallback Chain
**Current:** Providers (Top Posters, ERDB, TMDB, Nuvio) are somewhat independent.
**Suggestion:** Implement a configurable fallback chain:
```
Top Posters -> ERDB -> TMDB -> Nuvio -> Cinemeta -> User Upload
```
If the primary provider fails or returns no result, automatically try the next in the chain. Allow drag-and-drop reordering on the dashboard.

### 3.2 FanArt.tv Integration
**Suggestion:** Add [FanArt.tv](https://fanart.tv/api-docs/) as an artwork provider. It offers high-quality clearart, logos, disc art, and season/episode thumbnails that would complement existing providers.

### 3.3 MusicBrainz / Last.fm for Music Content
**Current:** No special handling for music video playback.
**Suggestion:** When the media player is playing music or music videos, use MusicBrainz or Last.fm APIs to fetch album artwork and artist metadata for Discord RPC.

### 3.4 Local Artwork Cache Management
**Current:** `artwork_cache_enabled` with a size limit of 1024, but no cache eviction UI.
**Suggestion:**
- Add a cache management page to the dashboard showing total cache size, hit/miss ratio, and most-cached titles.
- Allow manual cache clearing (all or selective).
- Implement LRU (Least Recently Used) eviction with configurable max age.

### 3.5 Artwork Quality Settings
**Current:** Fixed canvas size of 512x768 for Top Posters compositing.
**Suggestion:** Allow users to choose artwork quality profiles (Low / Medium / High / Original) to balance between Discord image quality and bandwidth usage. Include automatic WebP conversion for smaller file sizes.

### 3.6 Custom Artwork Upload
**Current:** `artwork_upload_enabled` with a shell command approach.
**Suggestion:**
- Add a built-in image hosting option via Imgur, Catbox (partially implemented), or a self-hosted solution.
- Allow users to manually override artwork for specific titles via the dashboard (upload custom poster/thumbnail).
- Store custom artwork mappings in a local database keyed by IMDb ID.

### 3.7 TMDB Rate Limit Handling
**Current:** No explicit rate limiting or retry logic for TMDB API calls.
**Suggestion:** Implement exponential backoff with jitter for TMDB API failures, respect `Retry-After` headers, and add a request counter to the dashboard showing API usage.

---

## 4. Skip Segment System

### 4.1 User-Contributed Skip Segments
**Current:** All skip data comes from external providers.
**Suggestion:**
- Allow users to manually mark intro/outro/recap boundaries while watching.
- Store user-created segments locally in an encrypted database.
- Optionally submit user segments to a community server (opt-in).

### 4.2 Skip Segment Preview
**Current:** Auto-skip happens silently.
**Suggestion:**
- Add a configurable countdown overlay (similar to Netflix's "Skip Intro" button) that shows on the dashboard before auto-skipping.
- Allow users to cancel a pending skip within a configurable window (e.g., 5 seconds).
- Show a toast notification on the dashboard when a skip occurs.

### 4.3 Skip Category Granularity
**Current:** Categories are intro, outro, with some provider-specific types.
**Suggestion:** Add finer-grained skip categories:
- Recap
- Preview / Next Episode Preview
- Credits (mid-credits vs. end-credits)
- Commercial breaks (for IPTV/live content)
- Content warnings
- Self-promotion segments

Allow per-category enable/disable toggles.

### 4.4 Skip Analytics Dashboard
**Current:** `total_skips` and `total_saved_ms` are tracked globally.
**Suggestion:**
- Per-provider skip success rate (which providers find segments most often).
- Per-category breakdown (how much intro vs. outro time was skipped).
- Weekly/monthly time-saved reports with shareable summary images.
- "Time saved" milestone achievements (e.g., "You've saved 10 hours!").

### 4.5 SponsorBlock Integration
**Suggestion:** Add [SponsorBlock](https://sponsor.ajay.app/) as a skip provider for YouTube content played through Stremio. SponsorBlock has a well-documented public API and could skip sponsor segments, self-promotion, and interaction reminders.

### 4.6 Skip Segment Caching
**Current:** Skip segments are fetched live from providers each time.
**Suggestion:** Cache skip segments locally keyed by IMDb ID + season + episode. Invalidate cache after a configurable TTL (e.g., 7 days) to pick up newly submitted segments.

---

## 5. Trakt Integration

### 5.1 Trakt Scrobble Reliability
**Current:** Circuit breaker after 3x 403 errors, but no token refresh flow.
**Suggestion:**
- Implement OAuth token refresh using the `refresh_token` before the access token expires.
- Persist token expiry time and proactively refresh 5 minutes before expiration (similar to Nuvio's approach).
- Add a "Re-authenticate" button on the dashboard that reinitializes the device code flow.

### 5.2 Trakt Collection Sync
**Current:** Scrobble (start/pause/stop) is the only Trakt interaction.
**Suggestion:**
- Automatically add watched content to the user's Trakt collection.
- Sync ratings from Trakt to display on the Discord RPC.
- Detect if content is already on a Trakt watchlist and show a badge.

### 5.3 Trakt Social Features
**Suggestion:**
- Show what friends are watching via Trakt's social API.
- Display Trakt ratings in the Discord RPC (e.g., "Rated 8.5 on Trakt").
- Support Trakt check-in (different from scrobble - announces to friends what you're watching).

### 5.4 Trakt Calendar Integration
**Suggestion:** Fetch the user's Trakt calendar to show upcoming episodes of shows they're watching. Display "Next episode in X days" on the dashboard.

### 5.5 Simkl / Kitsu as Alternative Scrobble Targets
**Suggestion:** Add [Simkl](https://simkl.docs.apiary.io/) or [Kitsu](https://kitsu.docs.apiary.io/) as alternative or additional scrobble targets alongside Trakt, especially for anime viewers who prefer Kitsu's anime-focused database.

---

## 6. Watch Party System

### 6.1 WebSocket-Based Communication
**Current:** HTTP polling with `requests.post()` for sync commands.
**Suggestion:** Replace the HTTP-based relay with WebSocket communication for:
- Lower latency sync (sub-100ms vs. HTTP request overhead).
- Persistent connections with automatic reconnection.
- Real-time bi-directional event streaming.

### 6.2 Party Chat
**Current:** Watch party only syncs play/pause/seek state.
**Suggestion:** Add a text chat feature within the watch party that displays on the dashboard. Messages could also optionally be bridged to a Discord channel via webhook.

### 6.3 Party Permissions & Roles
**Current:** Any peer can send sync commands.
**Suggestion:**
- Add host-only control mode (only the host can play/pause/seek).
- Add "request control" feature for guests.
- Add vote-to-skip/pause functionality for democratic control.

### 6.4 Internet Watch Parties
**Current:** Watch parties are local network only (raw HTTP on LAN IPs).
**Suggestion:**
- Add NAT traversal support (UPnP, STUN/TURN) for internet watch parties.
- Alternatively, offer a lightweight relay server option that can be self-hosted or use a free tier cloud service.
- Add party invite codes instead of raw IP addresses.

### 6.5 Sync Accuracy Improvements
**Current:** Deduplication threshold is 5000ms (5 seconds).
**Suggestion:**
- Reduce sync threshold to 1-2 seconds for tighter sync.
- Add NTP-style clock synchronization between peers.
- Implement buffering sync (pause all peers, wait for slowest, then resume together).

---

## 7. Smart Home Integration

### 7.1 MQTT Support
**Current:** Webhook, Philips Hue, and Home Assistant.
**Suggestion:** Add MQTT as a smart home provider for users who run MQTT brokers (Mosquitto, etc.). Publish play/pause/stop events to configurable MQTT topics.

### 7.2 Scene-Based Automation
**Current:** Binary play/pause triggers with dim brightness.
**Suggestion:**
- Map different content types to different scenes (e.g., horror movies = red ambient, comedies = warm white).
- Support genre-aware lighting based on TMDB genre data.
- Add fade transitions (gradual dim over X seconds when playback starts).
- Time-of-day aware brightness (don't dim during daytime).

### 7.3 Multi-Light / Multi-Room Support
**Current:** Single `hue_group_id` and single `ha_entity`.
**Suggestion:** Support multiple light groups/entities with different behaviors:
```json
{
  "lights": [
    {"entity": "light.tv_backlight", "on_play": "dim_50", "on_pause": "bright"},
    {"entity": "light.ceiling", "on_play": "off", "on_pause": "on"}
  ]
}
```

### 7.4 Google Home / Alexa Integration
**Suggestion:** Add voice assistant integration via Google Home or Alexa routines. Allow users to say "What am I watching?" and have the device respond with current title and progress.

### 7.5 Webhook Payload Customization
**Current:** Simple GET/POST to `smart_home_play_url` and `smart_home_pause_url`.
**Suggestion:** Allow custom webhook payloads with template variables:
```json
{
  "url": "https://hooks.example.com/media",
  "method": "POST",
  "headers": {"Authorization": "Bearer {token}"},
  "body": {
    "event": "{action}",
    "title": "{title}",
    "progress": "{progress}"
  }
}
```

---

## 8. Dashboard & Web UI

### 8.1 Mobile-Responsive Dashboard
**Current:** Dashboard is designed primarily for desktop browsers.
**Suggestion:** Create a mobile-responsive layout with:
- Swipe gestures for media controls.
- Compact card-based now-playing view.
- Pull-to-refresh for state updates.
- PWA (Progressive Web App) manifest for "Add to Home Screen" support.

### 8.2 Dashboard Authentication
**Current:** No authentication; anyone on the network can access the dashboard.
**Suggestion:**
- Add optional PIN/password protection.
- Support session-based auth with configurable timeout.
- Rate-limit API endpoints to prevent abuse.

### 8.3 Dark / Light Theme Toggle
**Current:** `dashboard_ui_mode` supports "normal" but limited theme options.
**Suggestion:**
- Add system-preference-aware auto dark/light mode.
- Allow custom accent colors.
- Add OLED-black theme option.

### 8.4 Dashboard Notifications
**Current:** No push notification system.
**Suggestion:**
- Browser push notifications for events (ADB disconnected, skip performed, watch party invite).
- Notification center in the dashboard showing recent events.
- Optional Discord webhook notifications for monitoring.

### 8.5 Remote Control Improvements
**Current:** Basic media key events (play/pause, volume, next/prev).
**Suggestion:**
- Full D-pad navigation overlay.
- App launcher (open specific apps on the Android TV).
- Screenshot viewer (see what's on the TV screen, already partially implemented via `capture_screenshot`).
- Keyboard input relay for search fields.

### 8.6 Configuration Import / Export
**Current:** `config.json` must be manually edited for backup/restore.
**Suggestion:**
- Add export/import buttons on the dashboard settings page.
- Support shareable config profiles (e.g., "Anime Setup", "Movie Night").
- Config diff view showing changes from defaults.
- Auto-backup before config changes with rollback option.

### 8.7 Onboarding Wizard
**Current:** Users must configure everything manually.
**Suggestion:** Add a first-run setup wizard that guides users through:
1. ADB device discovery and connection.
2. Discord Client ID configuration.
3. TMDB API key setup.
4. Artwork provider selection.
5. Skip provider preferences.
6. Smart home setup (optional).

### 8.8 Real-Time WebSocket State Updates
**Current:** Dashboard polls `/api/state` on an interval.
**Suggestion:** Replace polling with WebSocket or Server-Sent Events (SSE) for instant state updates. This reduces server load and provides a more responsive UI.

---

## 9. Analytics & History

### 9.1 Advanced Watch Statistics
**Current:** Basic total hours, session count, top titles, daily stats.
**Suggestion:**
- Genre distribution pie chart (comedy vs. drama vs. action, etc.).
- Average session length over time.
- Binge detection (consecutive episodes of the same show).
- Peak watching hours heatmap (what times of day the user watches most).
- Year-in-review summary (total hours, top genres, most-watched shows).

### 9.2 Database Backend
**Current:** JSON files (`analytics.json`, `stats.json`) with 500-session cap.
**Suggestion:**
- Migrate to SQLite for better query performance and no session cap.
- Add data export (CSV, JSON) from the dashboard.
- Support optional cloud sync (encrypted backup to user's own storage).

### 9.3 Watch History Search & Filter
**Current:** History shows recent entries in a flat list.
**Suggestion:**
- Add search by title, date range, and content type.
- Filter by "completed" vs. "in-progress" vs. "abandoned".
- Group history entries by show (collapsible per-show episode list).

### 9.4 Shareable Stats Cards
**Suggestion:** Generate shareable image cards (PNG) showing watch statistics (similar to Spotify Wrapped or Trakt year-in-review). Users can post these to social media or Discord.

---

## 10. Wako Mode

### 10.1 Wako Plugin Ecosystem
**Current:** Wako metadata is scraped from UI via `uiautomator`.
**Suggestion:**
- Create a lightweight Wako plugin/addon that directly sends metadata to Ascend Media RPC via a local API, eliminating the need for UI scraping.
- This would provide more reliable title, season, episode, and progress data.

### 10.2 Improved Wako Title Matching
**Current:** `MediaTitleResolver` uses multiple parser libraries (PTN, anitopy, guessit) with fallback.
**Suggestion:**
- Add a user-configurable title override map for problematic titles (e.g., a title that consistently resolves wrong).
- Store successful title resolutions in a local cache to speed up future lookups.
- Add fuzzy matching as a fallback for titles that don't match exactly.

### 10.3 Wako Focus Lock Improvements
**Current:** `wako_focus_lock` keeps the app in focus but can interfere with other operations.
**Suggestion:**
- Add a whitelist of apps that should not trigger focus-lock behavior (e.g., allow switching to YouTube without Wako reclaiming focus).
- Add a cooldown period after manual focus change before re-locking.

---

## 11. New API Integrations

### 11.1 Letterboxd Integration
**Suggestion:** Use the [Letterboxd API](https://letterboxd.com/api-beta/) to:
- Log watched films automatically.
- Fetch user ratings to display on RPC.
- Show Letterboxd popular reviews in the dashboard.

### 11.2 JustWatch API
**Suggestion:** Integrate [JustWatch](https://www.justwatch.com/) to show where content is available for streaming. Display "Also on Netflix, Hulu" in the dashboard or as RPC button links.

### 11.3 OpenSubtitles Integration
**Suggestion:** Add [OpenSubtitles](https://opensubtitles.stoplight.io/) integration to:
- Show subtitle availability status on the dashboard.
- Auto-download subtitles for content being played.
- Display subtitle language in RPC details.

### 11.4 AniList Integration
**Suggestion:** Add [AniList](https://anilist.gitbook.io/anilist-apiv2-docs/) as an anime metadata and tracking provider alongside MAL. AniList has a GraphQL API and is popular in the anime community. Could be used for:
- Anime metadata (titles in multiple languages, staff info, studio info).
- Automatic progress tracking and list updates.
- User score/rating display on RPC.

### 11.5 Plex/Jellyfin/Emby Companion
**Suggestion:** While Ascend is Android TV focused, add optional support for Plex, Jellyfin, or Emby webhook events. When these servers send playback webhooks, use them as an alternative metadata source or as a secondary presence trigger.

### 11.6 Last.fm Scrobbling
**Suggestion:** For music video or soundtrack playback, add [Last.fm](https://www.last.fm/api) scrobbling support alongside Trakt. Detect when the content is music-based and scrobble to Last.fm.

### 11.7 Notion / Obsidian Watch Log
**Suggestion:** Add optional integration with Notion API or Obsidian (via local files) to maintain a personal watch journal. Auto-create entries with title, rating, date watched, and personal notes prompt.

---

## 12. Architecture & Performance

### 12.1 Async / Event-Driven Architecture
**Current:** Threading-based with synchronous `requests` calls throughout.
**Suggestion:**
- Migrate HTTP calls to `aiohttp` or `httpx` with async support for non-blocking I/O.
- Use `asyncio` event loops for the monitor loop, ADB communication, and API calls.
- This would significantly improve performance when multiple providers are queried concurrently (skip manager already does concurrent fetching but with `ThreadPoolExecutor`).

### 12.2 Plugin / Extension System
**Current:** All providers and integrations are hardcoded.
**Suggestion:** Create a plugin architecture where:
- Metadata providers implement a standard interface (`search()`, `get_details()`, `get_artwork()`).
- Skip providers implement a standard interface (`get_skip_times()`).
- Smart home providers implement a standard interface (`on_play()`, `on_pause()`, `on_stop()`).
- Third-party developers can create and share plugins.

### 12.3 Configuration Hot-Reload
**Current:** Some config changes require restart; `update_config()` updates in-memory state.
**Suggestion:**
- Ensure all configuration changes take effect immediately without restart.
- Add a config file watcher that detects external changes to `config.json`.
- Emit config change events that components can subscribe to.

### 12.4 Health Check Endpoint
**Current:** No dedicated health check.
**Suggestion:** Add a `/api/health` endpoint returning:
```json
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "adb_connected": true,
  "discord_connected": true,
  "trakt_authenticated": true,
  "version": "1.0.0",
  "last_rpc_update": "2024-01-01T00:00:00Z"
}
```
Useful for monitoring with Uptime Kuma, Healthchecks.io, etc.

### 12.5 Docker Support
**Current:** No containerization support.
**Suggestion:**
- Add a `Dockerfile` and `docker-compose.yml` for easy deployment.
- Include volume mounts for config, data, and cache directories.
- Support environment variable configuration as alternative to `config.json`.
- Add a headless mode that runs without the GUI/webview.

### 12.6 Rate Limiter Middleware
**Current:** No rate limiting on the Flask API.
**Suggestion:** Add Flask-Limiter or custom middleware to prevent:
- API abuse from the local network.
- Accidental excessive polling from dashboard bugs.
- ADB command flooding.

---

## 13. Security & Privacy

### 13.1 API Key Validation
**Current:** API keys are stored in plaintext in `config.json`.
**Suggestion:**
- Validate API keys on save (test them against the respective API).
- Show key status indicators on the dashboard (valid, invalid, expired).
- Support encrypted config storage (partially implemented via `EncryptionManager`).

### 13.2 Privacy Mode
**Suggestion:** Add a "privacy mode" toggle that:
- Hides the currently playing title from Discord RPC (shows "Watching something" instead).
- Excludes certain titles or genres from Trakt scrobbling.
- Pauses analytics tracking.
- Allows a "blacklist" of titles that should never appear on RPC.

### 13.3 Dashboard HTTPS Support
**Current:** Flask serves over HTTP on port 5466.
**Suggestion:**
- Support self-signed or Let's Encrypt TLS certificates.
- Auto-generate a self-signed cert on first run for local network security.
- Add CORS configuration for cross-origin dashboard access.

### 13.4 Audit Log
**Suggestion:** Keep a log of all configuration changes, API key updates, and authentication events. Display on the dashboard for security monitoring.

---

## 14. Developer Experience

### 14.1 REST API Documentation
**Current:** API endpoints exist but are undocumented.
**Suggestion:**
- Add OpenAPI/Swagger documentation for all `/api/*` endpoints.
- Generate interactive API docs accessible at `/api/docs`.
- Include request/response examples for each endpoint.

**Current API endpoints to document:**
| Endpoint | Method | Description |
|---|---|---|
| `/api/state` | GET | Get current playback state and config |
| `/api/settings` | POST | Update configuration |
| `/api/command/manual_skip` | POST | Trigger a manual skip |
| `/api/test/skip_pipeline` | POST | Test skip segment lookup |
| `/api/wako/map` | GET/POST | Map Wako UI state |
| `/api/command/{action}` | POST | Send media remote commands |
| `/api/remote/{action}` | POST | Remote control actions |
| `/api/trakt/lists` | GET | Get Trakt watchlists |
| `/api/trakt/lists/{id}/items` | GET | Get items from a Trakt list |
| `/api/launch` | POST | Launch content deep link |
| `/api/analytics/stats` | GET | Get total analytics stats |
| `/api/analytics/daily` | GET | Get daily watch stats |
| `/api/analytics/sessions` | GET | Get recent sessions |
| `/api/party/host` | POST | Start hosting a watch party |
| `/api/party/join` | POST | Join a watch party |
| `/api/party/leave` | POST | Leave a watch party |
| `/api/party/status` | GET | Get watch party status |
| `/api/artwork/top-posters/season` | GET | Get Top Posters season artwork |
| `/api/artwork/erdb/discord` | GET | Get ERDB Discord artwork |
| `/api/artwork/cached/{key}` | GET | Get cached RPC artwork |

### 14.2 Webhook / Event System
**Suggestion:** Add an outbound webhook system that sends events to user-configured URLs:
```
Events: playback.started, playback.paused, playback.stopped,
        skip.performed, device.connected, device.disconnected,
        rpc.updated, party.joined, party.left
```
This enables third-party automation (IFTTT, Zapier, n8n, Node-RED).

### 14.3 CLI Mode
**Current:** Application requires GUI (webview or browser).
**Suggestion:** Add a headless CLI mode for server/NAS deployments:
```bash
ascend-rpc --headless --config /path/to/config.json
```
Output logs to stdout, expose only the Flask API, and skip GUI initialization.

### 14.4 Unit Test Suite
**Current:** No tests in the repository.
**Suggestion:**
- Add unit tests for core modules (`title_resolver`, `skip_manager`, `tmdb`, `erdb`, `trakt`).
- Add integration tests for the Flask API endpoints.
- Set up CI/CD with GitHub Actions for automated testing on PR.
- Add test fixtures for common media title formats and API responses.

### 14.5 Configuration Schema Validation
**Current:** Config keys are checked individually with `.get()` and defaults.
**Suggestion:**
- Define a JSON Schema or Pydantic model for `config.json`.
- Validate config on load and show warnings for unknown/deprecated keys.
- Auto-migrate old config formats to new ones.
- Provide helpful error messages for invalid values.

### 14.6 Logging Improvements
**Current:** Excellent logging with `CompactConsoleHandler`, secret redaction, and log tables.
**Suggestion:**
- Add structured JSON logging option for log aggregation (ELK stack, Grafana Loki).
- Add log level configuration per-module from the dashboard.
- Add log export button on the dashboard (download last N hours of logs).
- Add a log search/filter feature on the dashboard.

---

## Priority Matrix

| Suggestion | Impact | Effort | Priority |
|---|---|---|---|
| Multi-device support | High | High | P1 |
| Trakt token refresh | High | Low | P1 |
| WebSocket dashboard updates | High | Medium | P1 |
| Docker support | High | Low | P1 |
| Privacy mode | High | Low | P1 |
| Dashboard authentication | High | Low | P1 |
| REST API documentation | Medium | Low | P1 |
| Skip segment caching | Medium | Low | P2 |
| Artwork fallback chain | Medium | Medium | P2 |
| Watch party WebSocket upgrade | Medium | Medium | P2 |
| Health check endpoint | Medium | Low | P2 |
| Mobile-responsive dashboard | Medium | Medium | P2 |
| Plugin/extension system | High | High | P2 |
| Onboarding wizard | Medium | Medium | P2 |
| AniList integration | Medium | Medium | P3 |
| SponsorBlock integration | Medium | Medium | P3 |
| MQTT smart home | Low | Low | P3 |
| Letterboxd integration | Low | Medium | P3 |
| Async architecture migration | High | High | P3 |
| Year-in-review stats | Low | Medium | P3 |

---

## API Reference Quick Links

| Service | API Docs | Auth Type |
|---|---|---|
| TMDB | https://developer.themoviedb.org/docs | API Key |
| Trakt | https://trakt.docs.apiary.io/ | OAuth 2.0 |
| MAL | https://myanimelist.net/apiconfig/references/api/v2 | Client ID |
| AniList | https://anilist.gitbook.io/anilist-apiv2-docs/ | OAuth 2.0 |
| Simkl | https://simkl.docs.apiary.io/ | Client ID |
| Kitsu | https://kitsu.docs.apiary.io/ | OAuth 2.0 |
| FanArt.tv | https://fanart.tv/api-docs/ | API Key |
| SponsorBlock | https://wiki.sponsor.ajay.app/w/API_Docs | None |
| Last.fm | https://www.last.fm/api | API Key |
| OpenSubtitles | https://opensubtitles.stoplight.io/ | API Key |
| JustWatch | https://www.justwatch.com/ | Unofficial |
| Discord RPC | https://discord.com/developers/docs/rich-presence/how-to | Client ID |
| Philips Hue | https://developers.meethue.com/ | Bridge Key |
| Home Assistant | https://developers.home-assistant.io/docs/api/rest/ | Bearer Token |
| Nuvio | Custom (Supabase-backed) | JWT |

---

*This document is a living reference. Suggestions are based on analysis of the current codebase architecture and are designed to be incrementally implementable without breaking existing functionality.*
