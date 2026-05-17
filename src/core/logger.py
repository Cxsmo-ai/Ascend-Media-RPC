import logging
import os
import re
import sys
import time
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler

LOG_FILE = "stremio_debug.log"

# Use safer icons on Windows to prevent UnicodeEncodeError in some terminals
IS_WINDOWS = sys.platform == "win32"
LEVEL_ICONS = {
    logging.DEBUG: "?" if IS_WINDOWS else "🔎",
    logging.INFO: "*" if IS_WINDOWS else "✨",
    logging.WARNING: "!" if IS_WINDOWS else "⚠️",
    logging.ERROR: "X" if IS_WINDOWS else "❌",
    logging.CRITICAL: "!!" if IS_WINDOWS else "💥",
}

LEVEL_NAMES = {
    logging.DEBUG: "DBG",
    logging.INFO: "INF",
    logging.WARNING: "WRN",
    logging.ERROR: "ERR",
    logging.CRITICAL: "CRT",
}

SECRET_PATTERNS = [
    (re.compile(r"(Tk-)[A-Za-z0-9_-]{12,}"), r"\1••••"),
    (re.compile(r"(TP-)[A-Za-z0-9_-]{8,}"), r"\1••••"),
    (re.compile(r"(?i)(api[_-]?key['\"]?\s*[:=]\s*['\"]?)[^,'\"\s]+"), r"\1••••"),
    (re.compile(r"(?i)(token['\"]?\s*[:=]\s*['\"]?)[^,'\"\s]+"), r"\1••••"),
    (re.compile(r"(?i)(client_secret['\"]?\s*[:=]\s*['\"]?)[^,'\"\s]+"), r"\1••••"),
]


def redact_secrets(value) -> str:
    text = str(value)
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _compact_url(value: str, max_len: int = 74) -> str:
    text = redact_secrets(str(value or "").strip())
    if not text:
        return ""

    text = re.sub(r"https://", "", text)
    text = re.sub(r"http://", "", text)

    if len(text) <= max_len:
        return text

    return text[:34] + "…" + text[-max(12, max_len - 37):]


def _clean_repeat_key(text: str) -> str:
    text = redact_secrets(text)
    text = re.sub(r"\[\d{2}:\d{2}:\d{2}\]", "", text)
    text = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\s*/\s*\d{1,2}:\d{2}(?::\d{2})?\b", "<progress>", text)
    text = re.sub(r"\b\d{10,13}\b", "<num>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class PrettyConsoleFormatter(logging.Formatter):
    def format(self, record):
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        icon = LEVEL_ICONS.get(record.levelno, "•")
        level = LEVEL_NAMES.get(record.levelno, record.levelname[:3])
        message = redact_secrets(record.getMessage())

        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        if message.startswith("╭") or message.startswith("\n╭"):
            message = message.lstrip("\n")
            return f"[{timestamp}] {icon} {message}"

        separator = "|" if IS_WINDOWS else "│"
        return f"[{timestamp}] {icon} {level} {separator} {message}"


class DebugFileFormatter(logging.Formatter):
    def format(self, record):
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        message = redact_secrets(record.getMessage())

        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        return f"{timestamp} | {record.levelname:<8} | {record.name:<18} | {message}"


class WindowsSafeRotatingFileHandler(RotatingFileHandler):
    """Rotates when possible, but keeps logging if Windows has the file locked."""

    def doRollover(self):
        try:
            super().doRollover()
        except PermissionError:
            if self.stream:
                try:
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
            self.mode = "a"
            self.stream = self._open()

    def handleError(self, record):
        exc_type, _, _ = sys.exc_info()
        if exc_type is PermissionError:
            return
        super().handleError(record)


class CompactConsoleHandler(logging.StreamHandler):
    """
    Compresses repeated console messages.

    Example:
      [17:46:48] ✨ INF │ 🖼️ ERDB Discord Image: wsrv png proxy ok
      [17:47:05] 🔁 INF │ compressed 27 repeated lines

    The debug file still keeps detailed logs.
    """

    def __init__(self, stream=None, repeat_window=30.0):
        super().__init__(stream)
        self.repeat_window = repeat_window
        self._lock = threading.Lock()
        self._last_key = None
        self._last_level = logging.INFO
        self._last_time = 0.0
        self._repeat_count = 0

    def emit(self, record):
        try:
            formatted = self.format(record)
            key = _clean_repeat_key(formatted)
            now = time.time()

            with self._lock:
                if (
                    self._last_key == key
                    and now - self._last_time <= self.repeat_window
                ):
                    self._repeat_count += 1
                    self._last_time = now
                    return

                if self._repeat_count:
                    timestamp = datetime.fromtimestamp(now).strftime("%H:%M:%S")
                    level = LEVEL_NAMES.get(self._last_level, "INF")
                    rpt = "🔁" if not IS_WINDOWS else "[RPT]"
                    sep = "|" if IS_WINDOWS else "│"
                    self.stream.write(
                        f"[{timestamp}] {rpt} {level} {sep} compressed {self._repeat_count} repeated lines\n"
                    )
                    self._repeat_count = 0

                self._last_key = key
                self._last_level = record.levelno
                self._last_time = now

            self.stream.write(formatted + self.terminator)
            self.flush()

        except Exception:
            self.handleError(record)


def make_table(title: str, rows, icon: str = "✨", width: int = 76) -> str:
    title = f" {icon} {str(title).strip()} "
    inner_width = max(44, width - 2)

    if IS_WINDOWS:
        top = "+" + title + "-" * max(1, inner_width - len(title)) + "+"
        bottom = "+" + "-" * inner_width + "+"
    else:
        top = "╭" + title + "─" * max(1, inner_width - len(title)) + "╮"
        bottom = "╰" + "─" * inner_width + "╯"

    normalized_rows = []
    if isinstance(rows, dict):
        rows = rows.items()

    for key, value in rows:
        key = str(key).strip()
        value = "" if value is None else str(value).strip()
        value = redact_secrets(value)

        if key.lower() in {"url", "source", "image", "large_image", "small_image"}:
            value = _compact_url(value)

        normalized_rows.append((key, value))

    key_width = min(18, max([len(k) for k, _ in normalized_rows] + [6]))
    lines = [top]

    sep = "|" if IS_WINDOWS else "│"
    for key, value in normalized_rows:
        prefix = f"{sep} {key:<{key_width}} "
        available = inner_width - len(prefix) - 2

        if len(value) > available:
            value = value[: max(0, available - 1)] + "…"

        lines.append(prefix + f"{value:<{available}} {sep}")

    lines.append(bottom)
    return "\n".join(lines)


_last_once = {}
_once_lock = threading.Lock()


def log_once(key: str, message: str, seconds: float = 30.0, level=logging.INFO):
    now = time.time()
    with _once_lock:
        last = _last_once.get(key, 0)
        if now - last < seconds:
            return
        _last_once[key] = now

    logger.log(level, message)


def log_table(title: str, rows, icon: str = "✨", level=logging.INFO):
    logger.log(level, make_table(title, rows, icon=icon))


def setup_logging(console_level=logging.INFO, file_level=logging.DEBUG):
    root = logging.getLogger()

    if getattr(root, "_ascend_logging_ready", False):
        return

    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    except Exception:
        pass

    console = CompactConsoleHandler(sys.stdout)
    console.setLevel(console_level)
    console.setFormatter(PrettyConsoleFormatter())

    file_handler = WindowsSafeRotatingFileHandler(
        LOG_FILE,
        mode="a",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(DebugFileFormatter())

    root.addHandler(console)
    root.addHandler(file_handler)

    logging.getLogger("adb_shell").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("charset_normalizer").setLevel(logging.WARNING)

    root._ascend_logging_ready = True


setup_logging()
logger = logging.getLogger("stremio-rpc")


class LoggerWriter:
    def __init__(self, writer=None):
        self.writer = writer

    def write(self, buf):
        text = str(buf or "").strip()
        if text:
            logger.info(text)

    def flush(self):
        pass
