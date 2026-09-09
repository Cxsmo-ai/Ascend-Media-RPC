import re
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ResolvedMediaTitle:
    raw: str
    title: str
    year: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    episode_title: Optional[str] = None
    media_type_hint: Optional[str] = None
    confidence: float = 0.0


class MediaTitleResolver:
    """Normalize noisy media-session titles and filenames before metadata lookup."""

    VIDEO_EXTENSIONS = {
        "mkv", "mp4", "avi", "mov", "m4v", "wmv", "webm", "ts", "m2ts", "strm"
    }
    JUNK_TOKENS = {
        "480p", "576p", "720p", "1080p", "2160p", "4320p", "4k", "8k",
        "uhd", "hdr", "hdr10", "dv", "dolby", "vision", "web", "webrip",
        "web-dl", "webdl", "bluray", "blu-ray", "bdrip", "br rip", "dvdrip",
        "hdtv", "nf", "amzn", "dsnp", "hulu", "max", "remastered",
        "proper", "repack", "extended", "unrated", "ddp", "ddp5", "ddp5.1",
        "aac", "aac2", "aac2.0", "ac3", "eac3", "dts", "atmos", "x264",
        "x265", "h264", "h265", "hevc", "avc", "10bit", "yts", "rarbg"
    }

    def resolve(self, value: str, media_type_hint: Optional[str] = None) -> ResolvedMediaTitle:
        raw = value or ""
        text = self._basic_cleanup(raw)
        parser_data = self._external_parser_guess(text)

        season, episode, ep_title = self._extract_episode(text)
        if season is None:
            season = self._to_int(parser_data.get("season"))
        if episode is None:
            episode = self._to_int(parser_data.get("episode"))

        year = self._extract_year(text) or self._to_year(parser_data.get("year"))
        local_title = self._strip_metadata(text, year, season, episode)
        title = self._best_title(local_title, parser_data.get("title"))

        inferred_type = media_type_hint
        if not inferred_type:
            inferred_type = "tv" if season is not None or episode is not None else "movie" if year else None

        confidence = 0.35
        if title:
            confidence += 0.25
        if year:
            confidence += 0.15
        if season is not None or episode is not None:
            confidence += 0.2
        if parser_data:
            confidence += 0.05

        return ResolvedMediaTitle(
            raw=raw,
            title=title,
            year=year,
            season=season,
            episode=episode,
            episode_title=self._humanize_title(self._clean_episode_title(ep_title)) if ep_title else None,
            media_type_hint=inferred_type,
            confidence=min(confidence, 1.0),
        )

    def _external_parser_guess(self, text: str) -> Dict:
        for parser in (self._guess_with_parse_torrent_title, self._guess_with_anitopy, self._guess_with_guessit):
            data = parser(text)
            if data.get("title"):
                return data
        return {}

    def _guess_with_parse_torrent_title(self, text: str) -> Dict:
        try:
            import PTN
        except Exception:
            return {}
        try:
            data = PTN.parse(text) or {}
            return {
                "title": data.get("title"),
                "year": data.get("year"),
                "season": data.get("season"),
                "episode": data.get("episode"),
            }
        except Exception:
            return {}

    def _guess_with_anitopy(self, text: str) -> Dict:
        try:
            import anitopy
        except Exception:
            return {}
        try:
            data = anitopy.parse(text) or {}
            return {
                "title": data.get("anime_title"),
                "year": data.get("anime_year"),
                "episode": data.get("episode_number"),
            }
        except Exception:
            return {}

    def _guess_with_guessit(self, text: str) -> Dict:
        try:
            from guessit import guessit
        except Exception:
            return {}
        try:
            data = guessit(text) or {}
            return {
                "title": data.get("title"),
                "year": data.get("year"),
                "season": data.get("season"),
                "episode": data.get("episode"),
            }
        except Exception:
            return {}

    def _basic_cleanup(self, value: str) -> str:
        text = str(value or "").strip()
        text = re.sub(r"^(watching|playing|paused)(\s+on)?\s+[^:]{1,30}:\s*", "", text, flags=re.I)
        text = re.sub(r"^(watching|playing|paused)\s+", "", text, flags=re.I)
        text = re.sub(r"^(.+?[/\\])+", "", text)
        text = re.sub(r"\.(mkv|mp4|avi|mov|m4v|wmv|webm|ts|m2ts|strm)$", "", text, flags=re.I)
        text = re.sub(r"\[[0-9A-Fa-f]{6,10}\]", " ", text)
        text = text.replace("_", " ").replace(".", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _extract_episode(self, text: str):
        patterns = [
            r"\bS(?P<season>\d{1,2})\s*[.: -]?\s*E(?P<episode>\d{1,3})(?:\s*[- ]\s*(?P<title>.*?))?(?=\s+(?:19|20)\d{2}\b|$)",
            r"\b(?P<season>\d{1,2})x(?P<episode>\d{1,3})(?:\s*[- ]\s*(?P<title>.*?))?(?=\s+(?:19|20)\d{2}\b|$)",
            r"\bSeason\s+(?P<season>\d{1,2})\s+Episode\s+(?P<episode>\d{1,3})(?:\s*[-: ]\s*(?P<title>.*?))?(?=\s+(?:19|20)\d{2}\b|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return int(match.group("season")), int(match.group("episode")), (match.groupdict().get("title") or None)

        anime_match = re.search(r"\s-\s(?P<episode>\d{1,4})(?:\s|$)", text)
        if anime_match:
            return None, int(anime_match.group("episode")), None
        return None, None, None

    def _extract_year(self, text: str) -> Optional[str]:
        years = re.findall(r"\b(19\d{2}|20\d{2})\b", text)
        return years[-1] if years else None

    def _strip_metadata(self, text: str, year, season, episode) -> str:
        title = text
        title = re.sub(r"\[[^\]]*\]", " ", title)
        title = re.sub(r"\([^\)]*(?:1080p|720p|2160p|x264|x265|hevc|web|bluray)[^\)]*\)", " ", title, flags=re.I)
        title = re.sub(r"\bS\d{1,2}\s*[.: -]?\s*E\d{1,3}\b.*$", " ", title, flags=re.I)
        title = re.sub(r"\b\d{1,2}x\d{1,3}\b.*$", " ", title, flags=re.I)
        title = re.sub(r"\bSeason\s+\d{1,2}\s+Episode\s+\d{1,3}\b.*$", " ", title, flags=re.I)
        title = re.sub(r"\s-\s\d{1,4}\b.*$", " ", title)
        if year:
            title = re.sub(rf"\b{re.escape(str(year))}\b.*$", " ", title)
        tokens = []
        for token in re.split(r"\s+", title):
            cleaned = token.strip(" -_.()[]{}")
            if not cleaned:
                continue
            if cleaned.lower() in self.JUNK_TOKENS:
                break
            tokens.append(cleaned)
        return " ".join(tokens)

    def _clean_episode_title(self, title: Optional[str]) -> str:
        if not title:
            return ""
        text = re.sub(r"\[[^\]]*\]", " ", str(title))
        text = re.sub(r"\([^\)]*(?:1080p|720p|2160p|x264|x265|hevc|web|bluray)[^\)]*\)", " ", text, flags=re.I)
        tokens = []
        for token in re.split(r"\s+", text):
            cleaned = token.strip(" -_.()[]{}")
            if not cleaned:
                continue
            if cleaned.lower() in self.JUNK_TOKENS:
                break
            tokens.append(cleaned)
        return " ".join(tokens)

    def _best_title(self, local_title: str, parser_title: Optional[str]) -> str:
        local = self._humanize_title(local_title)
        parsed = self._humanize_title(parser_title)
        if not parsed:
            return local
        if not local:
            return parsed
        if len(parsed.split()) < len(local.split()) and len(parsed.split()) >= 2:
            return parsed
        return local

    def _humanize_title(self, title: Optional[str]) -> str:
        if not title:
            return ""
        text = re.sub(r"[\._]+", " ", str(title))
        text = re.sub(r"\s+", " ", text).strip(" -_[](){}")
        small_words = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "no", "nor", "of", "on", "or", "the", "to"}
        words = []
        for idx, word in enumerate(text.split()):
            if word.isupper() and len(word) <= 3:
                words.append(word)
            elif idx > 0 and word.lower() in small_words and not words[-1].endswith(":"):
                words.append(word.lower())
            else:
                words.append(word[:1].upper() + word[1:])
        return " ".join(words)

    def _to_int(self, value) -> Optional[int]:
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _to_year(self, value) -> Optional[str]:
        year = self._to_int(value)
        if year and 1900 <= year <= 2100:
            return str(year)
        return None
