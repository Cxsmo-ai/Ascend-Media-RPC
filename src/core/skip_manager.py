import os
import requests
import logging
from typing import Dict, List, Optional
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

try:
    import cloudscraper
    _cloudscraper_available = True
except ImportError:
    _cloudscraper_available = False

logger = logging.getLogger("stremio-rpc")

class SkipManager:
    """
    Manages Skip Providers and evaluates skip targets.
    Fetches concurrently from all enabled providers and merges results.
    """
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    }

    def __init__(self, config: Dict):
        self.INTRODB_BASE = "https://api.introdb.app"
        self.JIKAN_BASE = "https://api.jikan.moe/v4/anime"
        self.ANISKIP_BASE = "https://api.aniskip.com/v2/skip-times"
        self.TIDB_BASE = "https://theintrodb.org/api/v1"
        self.REMOTE_JSON_URL = config.get("remote_json_url", "")
        self.TIDB_KEY = config.get("tidb_api_key", "")
        
        self.cache = {}
        self.mal_cache = {}

        # Cloudscraper is available for Cloudflare-protected sites (TIDB, NotScare)
        # Note: create_scraper() per-request for thread safety
        self._cf_available = _cloudscraper_available

        # TTL-based persistent cache
        from src.core.skip_cache import SkipSegmentCache
        self._ttl_cache = SkipSegmentCache(
            ttl=config.get("skip_cache_ttl", 3600),
            max_size=config.get("skip_cache_max_size", 500),
        )
        
        self.enabled = (config.get("skip_mode", "off") != "off")
        
        # Provider states
        self.introdb_enabled = config.get("introdb_enabled", True)
        self.aniskip_fallback = config.get("aniskip_fallback", True)
        self.tidb_enabled = config.get("tidb_enabled", True)
        self.remote_json_enabled = config.get("remote_json_enabled", True)
        self.videoskip_enabled = config.get("videoskip_enabled", True)
        self.notscare_major_enabled = config.get("notscare_major_enabled", True)
        self.notscare_minor_enabled = config.get("notscare_minor_enabled", True)
        self.skipme_enabled = config.get("skipme_enabled", True)
        self.skipit_enabled = config.get("skipit_enabled", False)
        self.SKIPIT_BASE = "https://getskipit.com/api"
        # Auth holder: handles lazy Clerk refresh and persists new tokens
        # back via the on_token_refresh callback wired by the web layer.
        from src.core.skipit_auth import SkipItAuth
        self._skipit_on_token_refresh = None  # set externally by server/gui
        self.skipit_auth = SkipItAuth(
            token=config.get("skipit_token", ""),
            session_cookie=config.get("skipit_session_cookie", ""),
            session_id=config.get("skipit_session_id", ""),
            frontend_api=config.get("skipit_frontend_api", ""),
            on_token_refresh=lambda tok, status: (
                self._skipit_on_token_refresh(tok, status)
                if self._skipit_on_token_refresh else None
            ),
        )

        # Priority Order
        self.skip_priority_order = config.get("skip_priority_order", [
            "tidb", "skipme", "remote_json", "notscare_major", "notscare_minor", "introdb", "videoskip", "skipit", "aniskip"
        ])

        self.manual_tmdb_id = config.get("skip_tmdb_id", "")
        self.manual_mal_id = config.get("skip_mal_id", "")
        
        # Per-category toggles
        self.cat_intro = config.get("skip_cat_intro", True)
        self.cat_outro = config.get("skip_cat_outro", True)
        self.cat_recap = config.get("skip_cat_recap", True)
        self.cat_preview = config.get("skip_cat_preview", True)
        self.cat_credits = config.get("skip_cat_credits", True)
        self.cat_filler = config.get("skip_cat_filler", True)
        self.cat_mature = config.get("skip_cat_mature", True)
        self.cat_scare = config.get("skip_cat_scare", True)

    @staticmethod
    def _html_text(value: str) -> str:
        value = re.sub(r'<!--.*?-->', '', value or '', flags=re.S)
        value = re.sub(r'<[^>]+>', ' ', value)
        return re.sub(r'\s+', ' ', value).strip()

    def _slice_notscare_episode_block(self, content: str, episode: int) -> str:
        # Strategy 1: HTML heading tags (<h1-6>)
        headings = []
        for match in re.finditer(r'<h[1-6][^>]*>.*?</h[1-6]>', content or '', re.I | re.S):
            text = self._html_text(match.group(0))
            number_match = re.match(rf'0*{episode}\s*[.:)\-]\s+', text, re.I)
            generic_match = re.match(rf'(?:episode|chapter)\s+0*{episode}\b', text, re.I)
            any_episode_heading = re.match(r'(?:\d+\s*[.:)\-]\s+|(?:episode|chapter)\s+\d+\b)', text, re.I)
            headings.append((match.start(), match.end(), text, bool(number_match or generic_match), bool(any_episode_heading)))

        for index, (start, end, _text, is_target, _is_episode_heading) in enumerate(headings):
            if not is_target:
                continue
            block_end = len(content)
            for next_start, _next_end, _next_text, _next_is_target, next_is_episode_heading in headings[index + 1:]:
                if next_is_episode_heading:
                    block_end = next_start
                    break
            return content[start:block_end]

        # Strategy 2: Text-based episode markers (e.g. "2. Chapter Two" in flat text)
        # NotScare often puts all episodes in one block as plain text
        plain = self._html_text(content)
        markers = []
        for m in re.finditer(r'(\d+)\.\s+(?:Chapter|Episode)\s+\w+', plain, re.I):
            markers.append((int(m.group(1)), m.start()))

        if markers:
            target_idx = None
            for i, (ep_num, pos) in enumerate(markers):
                if ep_num == episode:
                    target_idx = i
                    break
            if target_idx is not None:
                start_pos = markers[target_idx][1]
                end_pos = markers[target_idx + 1][1] if target_idx + 1 < len(markers) else len(plain)
                return plain[start_pos:end_pos]

        return content

    def get_skip_times(self, imdb_id: str, season: int, episode: int, tmdb_id: Optional[int] = None, title: Optional[str] = None, is_movie: bool = False, year: Optional[str] = None) -> Optional[List[Dict]]:
        # Handle cases where season/episode might come in as strings from Flask
        try:
            season = int(season)
            episode = int(episode)
        except (TypeError, ValueError):
            pass
        
        if not imdb_id and not tmdb_id and not title:
            return None
        
        key = f"{imdb_id}-{tmdb_id}-{title}-{season}-{episode}-{is_movie}-{year}"
        if key in self.cache: return self.cache[key]

        # Check TTL cache first
        cached = self._ttl_cache.get(imdb_id or "", season, episode,
                                     tmdb_id=tmdb_id, title=title,
                                     is_movie=is_movie, year=year)
        if cached is not None:
            self.cache[key] = cached
            return cached
            
        all_segments = []
        mal_id = None
        if self.aniskip_fallback:
            if self.manual_mal_id:
                try: mal_id = int(self.manual_mal_id)
                except (TypeError, ValueError): pass
            else:
                mal_id = self._get_mal_id(imdb_id)
                
        lookup_tmdb = self.manual_tmdb_id if self.manual_tmdb_id else tmdb_id

        futures = {}
        with ThreadPoolExecutor(max_workers=8) as executor:
            if self.tidb_enabled:
                futures[executor.submit(self._fetch_tidb, imdb_id, season, episode, tmdb_id=lookup_tmdb)] = "tidb"
            if self.remote_json_enabled and self.REMOTE_JSON_URL:
                futures[executor.submit(self._fetch_remote_json, imdb_id, season, episode)] = "remote_json"
            if self.introdb_enabled:
                futures[executor.submit(self._fetch_introdb, lookup_tmdb, season, episode, imdb_id=imdb_id)] = "introdb"
            if self.videoskip_enabled:
                futures[executor.submit(self._fetch_videoskip, title, season, episode)] = "videoskip"
            if self.notscare_major_enabled or self.notscare_minor_enabled:
                futures[executor.submit(self._fetch_notscare, title, season, episode, is_movie, imdb_id, year)] = "notscare"
            if self.aniskip_fallback and mal_id:
                futures[executor.submit(self._fetch_aniskip, mal_id, episode)] = "aniskip"

            if self.skipme_enabled:
                futures[executor.submit(self._fetch_skipme, imdb_id, season, episode, is_movie, tmdb_id)] = "skipme"
            if self.skipit_enabled and self.skipit_auth.token:
                futures[executor.submit(self._fetch_skipit, lookup_tmdb, season, episode, is_movie)] = "skipit"

            
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res: all_segments.extend(res)
                except: pass

        if not all_segments:
            self.cache[key] = None
            return None
        
        # --- CATEGORY-AWARE SMART MIX ---
        # 1. Map types to conflict categories
        CAT_STRUCTURE = ["intro", "outro", "recap", "preview", "credits", "filler", "transition", "intermission", "part"]
        CAT_SCARE = ["jumpscare_major", "jumpscare_minor", "scare"]
        # Everything else (Mature/Violence/Sex/etc from VideoSkip) is CAT_MATURE
        
        def get_cat(stype):
            stype = stype.lower()
            if stype in CAT_STRUCTURE: return "structure"
            if stype in CAT_SCARE: return "scare"
            return "mature"
            
        def get_priority_score(source):
            if source in self.skip_priority_order:
                return self.skip_priority_order.index(source)
            return 999

        # Drop malformed/invalid segments (missing or non-numeric times, end <= start)
        cleaned_segments = []
        for seg in all_segments:
            if not isinstance(seg, dict):
                continue
            try:
                s_start = float(seg.get("start"))
                s_end = float(seg.get("end"))
            except (TypeError, ValueError):
                continue
            if s_end <= s_start or s_start < 0:
                continue
            seg["start"] = s_start
            seg["end"] = s_end
            cleaned_segments.append(seg)
        all_segments = cleaned_segments
        if not all_segments:
            self.cache[key] = None
            return None

        for seg in all_segments:
            seg["_priority"] = get_priority_score(seg.get("source", ""))
            seg["_cat"] = get_cat(seg.get("type", "unknown"))

        resolved_segments = []
        all_segments.sort(key=lambda x: (x["start"], x["_priority"]))
        
        for i, seg in enumerate(all_segments):
            keep = True
            for other in resolved_segments:
                # Check for overlap
                overlap_start = max(seg["start"], other["start"])
                overlap_end = min(seg["end"], other["end"])
                
                if overlap_start < overlap_end:
                    # ONLY resolve conflict if they are in the SAME category
                    # (e.g. Intro vs Intro, OR Major vs Minor Scare)
                    if seg["_cat"] == other["_cat"]:
                        overlap_dur = overlap_end - overlap_start
                        seg_dur = seg["end"] - seg["start"]
                        other_dur = other["end"] - other["start"]
                        
                        is_major_overlap = (overlap_dur > (seg_dur * 0.4) or overlap_dur > (other_dur * 0.4))
                        
                        if is_major_overlap:
                            if seg["_priority"] < other["_priority"]:
                                resolved_segments.remove(other)
                            else:
                                keep = False
                                break
                    else:
                        # Different Categories (Scare vs Mature) -> ALWAYS KEEP BOTH
                        pass
            
            if keep:
                resolved_segments.append(seg)

        resolved_segments.sort(key=lambda x: x["start"])
        # Apply per-category toggles
        cat_map = {
            "intro": self.cat_intro, "outro": self.cat_outro,
            "recap": self.cat_recap, "preview": self.cat_preview,
            "credits": self.cat_credits, "filler": self.cat_filler,
        }
        filtered = []
        for s in resolved_segments:
            s_type = s.get("type", "").lower()
            cat = s.get("_cat", "")
            if cat == "structure" and not cat_map.get(s_type, True):
                continue
            if cat == "mature" and not self.cat_mature:
                continue
            if cat == "scare" and not self.cat_scare:
                continue
            s.pop("_priority", None)
            s.pop("_cat", None)
            filtered.append(s)
        resolved_segments = filtered
            
        self.cache[key] = resolved_segments
        # Store in TTL cache for persistence across in-memory cache clears
        self._ttl_cache.put(imdb_id or "", season, episode, resolved_segments,
                           tmdb_id=tmdb_id, title=title,
                           is_movie=is_movie, year=year)
        return resolved_segments

    def get_cache_stats(self) -> Dict:
        """Return cache statistics."""
        return self._ttl_cache.stats()

    def clear_cache(self):
        """Clear both in-memory and TTL caches."""
        self.cache.clear()
        self._ttl_cache.invalidate()

    def _fetch_tidb(self, imdb_id: str, season: int, episode: int, tmdb_id: Optional[int] = None) -> Optional[List[Dict]]:
        try:
            url = f"https://api.theintrodb.org/v2/media?tmdb_id={tmdb_id or ''}&imdb_id={imdb_id or ''}&season={season}&episode={episode}"
            print(f"PIPELINE: Fetching TIDB -> {url}")
            if self._cf_available:
                http = cloudscraper.create_scraper()
                response = http.get(url, timeout=10)
            else:
                response = requests.get(url, headers=self.HEADERS, timeout=10)
            if response.status_code == 200:
                # Detect Cloudflare challenge pages masquerading as 200
                ct = response.headers.get("content-type", "")
                if "text/html" in ct and "Just a moment" in response.text[:500]:
                    print("PIPELINE: TIDB blocked by Cloudflare challenge.")
                    return None
                data = response.json()
                res = []
                for k in ["intro", "recap", "credits", "preview", "filler", "transition", "part"]:
                    for s in data.get(k, []):
                        # Handle TIDB V2 (start_ms/end_ms) and key variations
                        start = s.get('start_ms') or s.get('start') or s.get('start_time')
                        end = s.get('end_ms') or s.get('end') or s.get('end_time')
                        
                        if start is None or end is None: continue
                        
                        val = float(start)
                        val_end = float(end)
                        
                        # TIDB V2 logic: if values are > 1,000,000 they are likely ms
                        # If they are > 3,600,000 they are definitely ms (1 hour)
                        # But some shows are shorter. If val > 60000 (1 min) it could be ms.
                        # Let's standardize: if it's > 86400 (1 day in seconds), it's definitely MS or samples.
                        # Most segments don't start at 10+ hours.
                        if val > 10000: val /= 1000.0
                        if val_end > 10000: val_end /= 1000.0
                        
                        res.append({
                            "start": val, 
                            "end": val_end, 
                            "type": "outro" if k=="credits" else k, 
                            "source": "tidb", 
                            "label": f"Skip {k.capitalize()}"
                        })
                print(f"PIPELINE: TIDB found {len(res)} segments.")
                return res
            elif response.status_code == 403:
                print("PIPELINE: TIDB returned 403 (Cloudflare block). May work from a different network.")
        except Exception as e: 
            print(f"PIPELINE: TIDB Error -> {e}")
        return None

    def _fetch_notscare(self, title: str, season: int, episode: int, is_movie: bool, imdb_id: str = None, year: str = None) -> Optional[List[Dict]]:
        if not title: return None
        try:
            base = "https://notscare.me"
            content = None
            target_url = None
            if self._cf_available:
                http = cloudscraper.create_scraper()
                def _get(url):
                    return http.get(url, timeout=15)
            else:
                def _get(url):
                    return requests.get(url, headers=self.HEADERS, timeout=10)
            
            # Try Direct Slug Probe (Bypasses dynamic search issues)
            clean_name = title.lower().replace(':','').replace('&','and').strip()
            slug_base = clean_name.replace(' ', '-')
            probes = [f"jump-scares-in-{slug_base}"]
            if year: probes.insert(0, f"jump-scares-in-{slug_base}-{year}")
            if imdb_id: probes.append(imdb_id)
            
            category = "movies" if is_movie else "series"
            for probe in probes:
                probe_url = f"{base}/{category}/{probe}/"
                if not is_movie: probe_url += f"season/{season}/"
                print(f"PIPELINE: NotScare Probing -> {probe_url}")
                r = _get(probe_url)
                if r.status_code == 200:
                    target_url = probe_url
                    content = r.text
                    break
            
            if not content:
                # FALLBACK TO SEARCH 
                print(f"PIPELINE: NotScare Probe Failed. Trying Search Fallback.")
                search_url = f"{base}/{category}/?s={urllib.parse.quote(title)}"
                resp = _get(search_url)
                if resp.status_code == 403:
                    print("PIPELINE: NotScare search blocked by Cloudflare (403).")
                    return None
                pattern = rf'href="(?P<url>(?:https://notscare.me)?/{category}/(?P<slug>[^/"]+))'
                matches = list(re.finditer(pattern, resp.text))
                if matches:
                    target_url = matches[0].group("url")
                    if not target_url.startswith("http"): target_url = base + target_url
                    if not is_movie: target_url = target_url.split("/season/")[0].rstrip("/") + f"/season/{season}/"
                    resp = _get(target_url)
                    content = resp.text
            
            if not content: return None
            
            # Isolate target episode block for series. NotScare uses numbered card
            # headings like "3. Chapter Three" rather than "Episode 3".
            if not is_movie:
                content = self._slice_notscare_episode_block(content, episode)
            
            # Look for timestamps, then inspect the nearby text for the severity badge.
            # NotScare pages often render as "00:14:50 Minor ..." inside dense HTML.
            findings = []
            for match in re.finditer(r'\d{1,2}:\d{2}:\d{2}', content, re.I):
                nearby = self._html_text(content[match.start():match.start() + 700])
                severity_match = re.search(r'\b(Major|Minor)\b', nearby, re.I)
                findings.append((match.group(0), severity_match.group(1) if severity_match else "Major"))
            
            res = []
            for time_str, severity in findings:
                # If no severity found nearby, check if we're in a section that implies it or default to Major
                severity = severity if severity else "Major"
                
                parts = time_str.split(':')
                sec = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                severity_low = severity.lower()
                res.append({
                    "start": sec, 
                    "end": sec + 3.0, 
                    "type": f"jumpscare_{severity_low}", 
                    "source": f"notscare_{severity_low}", 
                    "label": f"NotScare: {severity}"
                })
            
            # Filter out impossible times (> 5 hours)
            unique_res = [r for r in res if r["start"] < 18000]
            
            print(f"PIPELINE: NotScare found {len(unique_res)} segments.")
            return unique_res if unique_res else None
        except Exception as e: 
            print(f"PIPELINE: NotScare Error -> {e}")
        return None

    def _fetch_videoskip(self, title: str, season: int, episode: int) -> Optional[List[Dict]]:
        if not title: return None
        try:
            base = "https://videoskip.herokuapp.com"
            search_url = f"{base}/exchange/search?q={urllib.parse.quote(title)}"
            print(f"PIPELINE: Searching VideoSkip -> {search_url}")
            r = requests.get(search_url, headers=self.HEADERS, timeout=5)
            
            # Try to find series link
            m = re.search(r'href="/exchange/series/(\d+)/"', r.text)
            if not m:
                # Try broadening search with S/E tags
                r = requests.get(f"{base}/exchange/search?q={urllib.parse.quote(title + f' S{season} E{episode}')}", headers=self.HEADERS, timeout=5)
                m = re.search(r'href="/exchange/series/(\d+)/"', r.text)
            
            if not m: return None
            
            r = requests.get(f"{base}/exchange/series/{m.group(1)}/", headers=self.HEADERS, timeout=5)
            # Find specific episode link
            m = re.search(rf'S0*{season}\s*E0*{episode}.*?href="/exchange/(?:videos|episode)/(\d+)/"', r.text, re.I | re.S)
            if not m: return None
            
            target_id = m.group(1)
            r = requests.get(f"{base}/exchange/videos/{target_id}/", headers=self.HEADERS, timeout=5)
            if r.status_code != 200: r = requests.get(f"{base}/exchange/episode/{target_id}/", headers=self.HEADERS, timeout=5)
            
            m = re.search(r'href="/exchange/skip/(\d+)/"', r.text)
            if not m: return None
            
            r = requests.get(f"{base}/exchange/skip/{m.group(1)}/download/", headers=self.HEADERS, timeout=5)
            
            def ts(t):
                p = t.replace(',', '.').split(':')
                if len(p) == 3: return int(p[0])*3600 + int(p[1])*60 + float(p[2])
                return float(t)
                
            res = []
            lines = r.text.splitlines()
            for i in range(len(lines)):
                if '-->' in lines[i]:
                    start_t, end_t = lines[i].split('-->')
                    sk_type = lines[i+1].strip() if i+1 < len(lines) else 'skip'
                    res.append({"start": ts(start_t.strip()), "end": ts(end_t.strip()), "type": sk_type, "source": "videoskip", "label": "VideoSkip: " + sk_type.capitalize()})
            print(f"PIPELINE: VideoSkip found {len(res)} segments.")
            return res
        except Exception as e: 
            print(f"PIPELINE: VideoSkip Error -> {e}")
        return None

    def _fetch_skipme(self, imdb_id: str, season: int, episode: int, is_movie: bool, tmdb_id: Optional[int] = None) -> Optional[List[Dict]]:
        try:
            base_url = "https://db.skipme.workers.dev/v1"
            endpoint = "/movies" if is_movie else "/shows"
            url = base_url + endpoint
            
            # SkipMe API requires an ARRAY of objects and the official User-Agent
            item = {"imdb_id": imdb_id}
            if tmdb_id: item["tmdb_id"] = int(tmdb_id)
            if not is_movie:
                item["season"] = season
                item["episode"] = episode
            
            headers = self.HEADERS.copy()
            headers["User-Agent"] = "SkipMe.db"
            
            print(f"PIPELINE: Fetching SkipMe -> {url}")
            response = requests.post(url, json=[item], headers=headers, timeout=5)
            
            if response.status_code == 200:
                # The API returns a list of results (for each ID sent), segments are in result["segments"]
                data = response.json()
                if not data or not isinstance(data, list) or len(data) == 0: return None
                
                # First result in the batch mapping
                series_result = data[0]
                if not isinstance(series_result, dict):
                    return None
                segments = series_result.get("segments", []) or []
                
                res = []
                for entry in segments:
                    # Filter for target episode/season (API often returns multiple)
                    if not is_movie:
                        if int(entry.get("season", -1)) != season or int(entry.get("episode", -1)) != episode:
                            continue
                            
                    label = entry.get("segment", "intro")
                    stype = "intro"
                    if "credits" in label: stype = "outro"
                    if "recap" in label: stype = "recap"
                    if "preview" in label: stype = "preview"
                    
                    res.append({
                        "start": entry.get("start_ms", 0) / 1000.0,
                        "end": entry.get("end_ms", 0) / 1000.0,
                        "type": stype,
                        "source": "skipme",
                        "label": f"SkipMe: {label.capitalize()}"
                    })
                print(f"PIPELINE: SkipMe matched {len(res)} segments.")
                return res if res else None
        except Exception as e: 
            print(f"PIPELINE: SkipMe Error -> {e}")
        return None

    def _fetch_skipit(self, tmdb_id, season: int, episode: int, is_movie: bool) -> Optional[List[Dict]]:
        """Fetch mature-content skip timestamps from SkipIt (getskipit.com).

        Covers nudity, sex, and gore for Movies and TV episodes. Requires a
        Clerk bearer token from the user's getskipit.com session.

        Reference: https://github.com/wahibonae/skipit (src/lib/api.ts).
        """
        if not tmdb_id:
            return None
        # Lazy-refresh via Clerk if a __client cookie is configured; falls
        # back to the existing JWT if refresh isn't possible/needed.
        token = self.skipit_auth.get_active_token() if self.skipit_auth else ""
        if not token:
            return None
        try:
            try:
                tid = int(tmdb_id)
            except (TypeError, ValueError):
                return None

            content_type = "movie" if is_movie else "episode"
            params = [
                "source=extension",
                "skip_nudity=true",
                "skip_sex=true",
                "skip_gore=true",
            ]
            if not is_movie:
                params.append(f"seasonNumber={int(season)}")
                params.append(f"episodeNumber={int(episode)}")

            url = f"{self.SKIPIT_BASE}/timestamps/{content_type}/{tid}?{'&'.join(params)}"
            print(f"PIPELINE: Fetching SkipIt -> {url}")

            auth_header = token if token.lower().startswith("bearer ") else f"Bearer {token}"
            headers = self.HEADERS.copy()
            headers["Authorization"] = auth_header
            headers["Accept"] = "application/json"

            response = requests.get(url, headers=headers, timeout=8)
            if response.status_code == 401:
                # One retry: force a refresh in case the cached token just
                # expired between the freshness check and this network call.
                if self.skipit_auth and self.skipit_auth.can_refresh:
                    refreshed = self.skipit_auth.force_refresh()
                    if refreshed.get("ok"):
                        headers["Authorization"] = f"Bearer {self.skipit_auth.token}"
                        response = requests.get(url, headers=headers, timeout=8)
                if response.status_code == 401:
                    print("PIPELINE: SkipIt 401 Unauthorized - token missing/expired.")
                    return None
            if response.status_code == 404:
                print("PIPELINE: SkipIt 404 - no timestamps for this content.")
                return None
            if response.status_code != 200:
                print(f"PIPELINE: SkipIt HTTP {response.status_code}.")
                return None

            data = response.json() or {}
            timestamps = data.get("timestamps") or []
            res = []
            for entry in timestamps:
                start = entry.get("start_time")
                end = entry.get("end_time")
                if start is None or end is None:
                    continue
                try:
                    start_f = float(start)
                    end_f = float(end)
                except (TypeError, ValueError):
                    continue
                if end_f <= start_f:
                    continue
                raw_type = str(entry.get("type") or "mature").lower()
                # Skipit types are Nudity/Sex/Gore -> all map to mature category
                res.append({
                    "start": start_f,
                    "end": end_f,
                    "type": raw_type,
                    "source": "skipit",
                    "label": f"SkipIt: {raw_type.capitalize()}",
                })
            print(f"PIPELINE: SkipIt found {len(res)} segments.")
            return res if res else None
        except Exception as e:
            print(f"PIPELINE: SkipIt Error -> {e}")
        return None

    def _fetch_introdb(self, lookup_tmdb: str, season: int, episode: int, imdb_id: Optional[str] = None) -> Optional[List[Dict]]:
        if not lookup_tmdb and not imdb_id: return None
        try:
            if imdb_id:
                url = f"{self.INTRODB_BASE}/segments?imdb_id={urllib.parse.quote(str(imdb_id))}&season={season}&episode={episode}"
            else:
                url = f"https://introdb.app/api/v1/episodes/{lookup_tmdb}/{season}/{episode}"
            print(f"PIPELINE: Fetching IntroDB -> {url}")
            response = requests.get(url, headers=self.HEADERS, timeout=5)
            if response.status_code == 200:
                data = response.json()
                res = []
                for k, stype in [("intro", "intro"), ("introduction", "intro"), ("outro", "outro"), ("recap", "recap")]:
                    segment = data.get(k)
                    if not segment:
                        continue
                    start = segment.get("start_sec", segment.get("start"))
                    end = segment.get("end_sec", segment.get("end"))
                    if start is None and segment.get("start_ms") is not None:
                        start = float(segment["start_ms"]) / 1000.0
                    if end is None and segment.get("end_ms") is not None:
                        end = float(segment["end_ms"]) / 1000.0
                    if start is None or end is None:
                        continue
                    res.append({"start": float(start), "end": float(end), "type": stype, "source": "introdb", "label": f"Skip {stype.capitalize()}"})
                return res
        except: pass
        return None

    def _fetch_remote_json(self, imdb_id: str, season: int, episode: int) -> Optional[List[Dict]]:
        if not self.REMOTE_JSON_URL: return None
        try:
            print(f"PIPELINE: Fetching Remote JSON -> {self.REMOTE_JSON_URL}")
            resp = requests.get(self.REMOTE_JSON_URL, headers=self.HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                key = f"{imdb_id}:{season}:{episode}"
                if key in data:
                    res = []
                    for s in data[key]:
                        if not isinstance(s, dict):
                            continue
                        start = s.get("start")
                        end = s.get("end")
                        if start is None or end is None:
                            continue
                        res.append({
                            "start": start,
                            "end": end,
                            "type": s.get("type", "intro"),
                            "source": "remote_json",
                            "label": s.get("label", "Remote Skip")
                        })
                    print(f"PIPELINE: Remote JSON matched {len(res)} segments.")
                    return res if res else None
        except Exception as e: 
            print(f"PIPELINE: Remote JSON Error -> {e}")
        return None

    def _fetch_aniskip(self, mal_id: int, episode: int) -> Optional[List[Dict]]:
        try:
            url = f"https://api.aniskip.com/v2/skip-times/{mal_id}/{episode}?types[]=op&types[]=ed&types[]=recap"
            print(f"PIPELINE: Fetching AniSkip -> {url}")
            response = requests.get(url, headers=self.HEADERS, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("found"):
                    res = []
                    for t in data.get("results", []):
                        if not isinstance(t, dict):
                            continue
                        interval = t.get("interval") or {}
                        start = interval.get("startTime")
                        end = interval.get("endTime")
                        if start is None or end is None:
                            continue
                        st = t.get("skipType", "intro").replace("op", "intro").replace("ed", "outro")
                        res.append({"start": start, "end": end, "type": st, "source": "aniskip", "label": "Skip " + st.capitalize()})
                    print(f"PIPELINE: AniSkip found {len(res)} segments.")
                    return res if res else None
        except Exception as e: 
            print(f"PIPELINE: AniSkip Error -> {e}")
        return None

    def _get_mal_id(self, imdb_id: str) -> Optional[int]:
        if imdb_id in self.mal_cache: return self.mal_cache[imdb_id]
        try:
            name = requests.get(f"https://v3-cinemeta.strem.io/meta/series/{imdb_id}.json", timeout=5).json().get("meta", {}).get("name")
            data = requests.get(f"{self.JIKAN_BASE}?q={urllib.parse.quote(name)}&type=tv&limit=1", timeout=5).json().get("data", [])
            if data:
                mal_id = data[0]["mal_id"]
                self.mal_cache[imdb_id] = mal_id
                return mal_id
        except: pass
        return None

    def should_skip(self, position_ms: int, skip_times: List[Dict]) -> Optional[tuple]:
        if not self.enabled or not skip_times: return None
        try:
            pos_sec = float(position_ms) / 1000.0
        except (TypeError, ValueError):
            return None
        for interval in skip_times:
            if not isinstance(interval, dict):
                continue
            start = interval.get("start")
            end = interval.get("end")
            if start is None or end is None:
                continue
            try:
                start_f = float(start)
                end_f = float(end)
            except (TypeError, ValueError):
                continue
            if end_f <= start_f:
                continue
            if start_f <= pos_sec < end_f:
                target_ms = int(end_f * 1000)
                if target_ms - position_ms > 1000:
                    return (target_ms, interval.get("type", "skip"))
        return None
