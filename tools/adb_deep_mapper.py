"""Maximum-depth, local-only Android/Android TV mapper over adb-shell.

The mapper never auto-activates UI controls. Taps, long presses, ENTER, BACK,
and HOME are available only in the interactive mode after confirmation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.controller import StremioController


BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
SAFE_SHELL_NAME_RE = re.compile(r"^[A-Za-z0-9_.:@/+-]+$")
TRUE_ATTRIBUTES = {
    "checkable", "checked", "clickable", "enabled", "focusable", "focused",
    "long-clickable", "password", "scrollable", "selected",
}


@dataclass(frozen=True)
class Probe:
    category: str
    name: str
    command: str
    timeout: float = 15.0
    sensitive: bool = False


CURATED_PROBES = [
    Probe("identity", "properties", "getprop", 20),
    Probe("identity", "kernel", "uname -a; cat /proc/version; id; date; uptime"),
    Probe("identity", "build", "getprop ro.build.fingerprint; getprop ro.product.manufacturer; getprop ro.product.model; getprop ro.build.version.release; getprop ro.build.version.sdk"),
    Probe("identity", "users", "cmd user list; pm list users"),
    Probe("identity", "services", "service list", 25),
    Probe("identity", "shell_commands", "cmd -l", 20),
    Probe("display", "wm", "wm size; wm density; wm overscan 2>/dev/null"),
    Probe("display", "display", "dumpsys display", 25),
    Probe("display", "surface_layers", "dumpsys SurfaceFlinger --list", 20),
    Probe("display", "surface_displays", "dumpsys SurfaceFlinger --display-id 2>/dev/null", 20),
    Probe("display", "graphics_stats", "dumpsys graphicsstats", 25),
    Probe("display", "gfxinfo", "dumpsys gfxinfo", 30),
    Probe("window", "windows", "dumpsys window windows", 30),
    Probe("window", "displays", "dumpsys window displays", 25),
    Probe("window", "policy", "dumpsys window policy", 25),
    Probe("window", "tokens", "dumpsys window tokens", 25),
    Probe("window", "focus", "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp|mTopFullscreenOpaqueWindow|mDreamingLockscreen'"),
    Probe("activity", "activities", "dumpsys activity activities", 35),
    Probe("activity", "top", "dumpsys activity top", 30),
    Probe("activity", "recents", "dumpsys activity recents", 25, True),
    Probe("activity", "processes", "dumpsys activity processes", 35),
    Probe("activity", "services", "dumpsys activity services", 35),
    Probe("activity", "providers", "dumpsys activity providers", 30),
    Probe("activity", "broadcasts", "dumpsys activity broadcasts", 35, True),
    Probe("activity", "exit_info", "dumpsys activity exit-info 2>/dev/null", 25),
    Probe("packages", "all", "pm list packages -U -i --show-versioncode", 30),
    Probe("packages", "third_party", "pm list packages -3 -U -i --show-versioncode", 20),
    Probe("packages", "system", "pm list packages -s -U -i --show-versioncode", 30),
    Probe("packages", "disabled", "pm list packages -d -U --show-versioncode", 20),
    Probe("packages", "features", "pm list features"),
    Probe("packages", "libraries", "pm list libraries"),
    Probe("packages", "permissions", "pm list permissions -f -g", 25),
    Probe("packages", "roles", "cmd role dump 2>/dev/null", 20),
    Probe("packages", "overlays", "cmd overlay list --user current 2>/dev/null", 20),
    Probe("packages", "shortcuts", "dumpsys shortcut", 30, True),
    Probe("media", "sessions", "dumpsys media_session", 25),
    Probe("media", "audio", "dumpsys audio", 30),
    Probe("media", "audio_flinger", "dumpsys media.audio_flinger", 30),
    Probe("media", "audio_policy", "dumpsys media.audio_policy", 30),
    Probe("media", "codec", "dumpsys media.codec", 30),
    Probe("media", "extractor", "dumpsys media.extractor", 20),
    Probe("media", "drm", "dumpsys media.drm", 20),
    Probe("tv", "tv_input", "dumpsys tv_input 2>/dev/null", 25),
    Probe("tv", "hdmi_control", "dumpsys hdmi_control 2>/dev/null", 25),
    Probe("tv", "companion", "dumpsys companiondevice 2>/dev/null", 20),
    Probe("input", "input", "dumpsys input", 35),
    Probe("input", "devices", "getevent -pl 2>/dev/null", 25),
    Probe("input", "input_method", "dumpsys input_method", 25, True),
    Probe("input", "accessibility", "dumpsys accessibility", 25, True),
    Probe("input", "autofill", "dumpsys autofill 2>/dev/null", 25, True),
    Probe("power", "power", "dumpsys power", 25),
    Probe("power", "battery", "dumpsys battery; dumpsys batteryproperties"),
    Probe("power", "dream", "dumpsys dream", 15),
    Probe("power", "device_idle", "dumpsys deviceidle", 25),
    Probe("power", "alarm", "dumpsys alarm", 35, True),
    Probe("power", "jobs", "dumpsys jobscheduler", 35, True),
    Probe("power", "thermal", "dumpsys thermalservice 2>/dev/null", 20),
    Probe("network", "interfaces", "ip -details addr; ip route; ip -6 route", 20, True),
    Probe("network", "connectivity", "dumpsys connectivity", 35, True),
    Probe("network", "wifi", "dumpsys wifi", 35, True),
    Probe("network", "ethernet", "dumpsys ethernet 2>/dev/null", 20, True),
    Probe("network", "netstats", "dumpsys netstats", 35, True),
    Probe("network", "dns", "dumpsys dnsresolver 2>/dev/null", 20, True),
    Probe("storage", "filesystem", "df -h; mount; cat /proc/mounts", 25),
    Probe("storage", "storage", "dumpsys storage; dumpsys storaged", 30),
    Probe("performance", "memory", "cat /proc/meminfo; dumpsys meminfo", 40),
    Probe("performance", "cpu", "cat /proc/cpuinfo; dumpsys cpuinfo", 30),
    Probe("performance", "processes", "ps -A -o USER,PID,PPID,VSZ,RSS,STAT,NAME,ARGS 2>/dev/null || ps -A", 25, True),
    Probe("performance", "procstats", "dumpsys procstats", 40, True),
    Probe("performance", "diskstats", "dumpsys diskstats", 25),
    Probe("security", "selinux", "getenforce; getenforce 2>/dev/null; cat /sys/fs/selinux/enforce 2>/dev/null"),
    Probe("security", "device_policy", "dumpsys device_policy", 25, True),
    Probe("security", "trust", "dumpsys trust", 20, True),
    Probe("security", "appops", "dumpsys appops", 45, True),
    Probe("system", "settings_global", "settings list global", 25, True),
    Probe("system", "settings_secure", "settings list secure", 25, True),
    Probe("system", "settings_system", "settings list system", 25, True),
    Probe("system", "notifications", "dumpsys notification --noredact", 40, True),
    Probe("system", "accounts", "dumpsys account", 25, True),
    Probe("system", "usage", "dumpsys usagestats", 40, True),
    Probe("system", "clipboard", "dumpsys clipboard 2>/dev/null", 15, True),
    Probe("system", "dumpsys_services", "dumpsys -l", 20),
    Probe("logs", "logcat", "logcat -d -v threadtime -t 10000", 45, True),
    Probe("logs", "events", "logcat -b events -d -v threadtime -t 5000", 35, True),
    Probe("logs", "crash", "logcat -b crash -d -v threadtime -t 2000", 25, True),
]


def safe_name(value: str, fallback: str = "item") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")
    return (cleaned[:120] or fallback)


def parse_bounds(value: str) -> Optional[Tuple[int, int, int, int]]:
    match = BOUNDS_RE.fullmatch(str(value or "").strip())
    if not match:
        return None
    x1, y1, x2, y2 = map(int, match.groups())
    if x2 < x1 or y2 < y1:
        return None
    return x1, y1, x2, y2


def parse_ui_xml(xml_text: str) -> List[Dict]:
    if not xml_text or "<hierarchy" not in xml_text:
        return []
    root = ET.fromstring(xml_text[xml_text.index("<hierarchy"):])
    records: List[Dict] = []

    def walk(element, parent_index: Optional[int], depth: int):
        if element.tag != "node":
            for child in element:
                walk(child, parent_index, depth)
            return
        attrs = dict(element.attrib)
        bounds = parse_bounds(attrs.get("bounds", ""))
        index = len(records)
        record = {
            "index": index,
            "parent_index": parent_index,
            "depth": depth,
            "text": attrs.get("text", ""),
            "content_desc": attrs.get("content-desc", ""),
            "resource_id": attrs.get("resource-id", ""),
            "class": attrs.get("class", ""),
            "package": attrs.get("package", ""),
            "bounds": attrs.get("bounds", ""),
            "x1": bounds[0] if bounds else None,
            "y1": bounds[1] if bounds else None,
            "x2": bounds[2] if bounds else None,
            "y2": bounds[3] if bounds else None,
            "center_x": ((bounds[0] + bounds[2]) // 2) if bounds else None,
            "center_y": ((bounds[1] + bounds[3]) // 2) if bounds else None,
            "width": (bounds[2] - bounds[0]) if bounds else None,
            "height": (bounds[3] - bounds[1]) if bounds else None,
            "attributes": attrs,
        }
        for key in TRUE_ATTRIBUTES:
            record[key.replace("-", "_")] = attrs.get(key) == "true"
        record["tap_command"] = (
            f"input tap {record['center_x']} {record['center_y']}" if bounds else ""
        )
        record["long_press_command"] = (
            f"input swipe {record['center_x']} {record['center_y']} {record['center_x']} {record['center_y']} 800"
            if bounds else ""
        )
        records.append(record)
        for child in element:
            walk(child, index, depth + 1)

    walk(root, None, 0)
    return records


def parse_package_names(output: str) -> List[str]:
    packages = []
    for line in (output or "").splitlines():
        match = re.search(r"(?:^|\s)package:(?:[^=\s]+\.apk=)?([A-Za-z0-9_.]+)(?:\s|$)", line)
        if match and match.group(1) not in packages:
            packages.append(match.group(1))
    return packages


def parse_service_names(output: str) -> List[str]:
    names = []
    for line in (output or "").splitlines():
        value = line.strip().lstrip("-").strip()
        if value and SAFE_SHELL_NAME_RE.fullmatch(value) and value not in names:
            names.append(value)
    return names


class DeepMapper:
    def __init__(self, host: str, port: int, output_root: Path, include_sensitive: bool = False):
        self.host = host
        self.port = int(port)
        self.output_root = output_root
        self.include_sensitive = include_sensitive
        self.controller = StremioController(host, port)
        self.device = None
        self.run_dir: Optional[Path] = None
        self.manifest: Dict = {"probes": [], "screens": []}
        self._watch_stop = threading.Event()
        self._watch_thread = None
        self._frame_thread = None
        self._user_stop = threading.Event()
        self._stop_listener = None

    def connect(self):
        print(f"[ADB] Connecting to {self.host}:{self.port}...")
        if not self.controller.connect():
            raise RuntimeError(self.controller.last_connect_error or "ADB connection failed")
        self.device = self.controller.device
        model = self.controller.get_device_name()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = self.output_root / f"{safe_name(model, 'android_tv')}_{stamp}"
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.manifest.update({
            "schema_version": 1,
            "host": self.host,
            "port": self.port,
            "device": model,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "include_sensitive": self.include_sensitive,
            "apk_files_collected": False,
            "output": str(self.run_dir),
        })
        print(f"[ADB] Connected: {model}")
        print(f"[MAP] Output: {self.run_dir}")

    def close(self):
        try:
            self.controller.mark_disconnected("mapper complete")
        except Exception:
            pass

    def shell(self, command: str, timeout: float = 15.0) -> Tuple[bool, str, float]:
        started = time.monotonic()
        try:
            output = self.device.shell(command, timeout_s=timeout)
            return True, str(output or ""), time.monotonic() - started
        except Exception as exc:
            return False, f"{exc.__class__.__name__}: {exc}", time.monotonic() - started

    def save_probe(self, probe: Probe) -> Dict:
        if probe.sensitive and not self.include_sensitive:
            record = {"category": probe.category, "name": probe.name, "skipped": "sensitive"}
            self.manifest["probes"].append(record)
            return record
        folder = self.run_dir / "diagnostics" / safe_name(probe.category)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{safe_name(probe.name)}.txt"
        ok, output, elapsed = self.shell(probe.command, probe.timeout)
        path.write_text(output, encoding="utf-8", errors="replace")
        record = {
            "category": probe.category, "name": probe.name, "ok": ok,
            "seconds": round(elapsed, 3), "bytes": len(output.encode("utf-8", errors="replace")),
            "path": str(path.relative_to(self.run_dir)),
        }
        self.manifest["probes"].append(record)
        print(f"[{'OK' if ok else '!!'}] {probe.category}/{probe.name} ({elapsed:.1f}s, {record['bytes']} bytes)")
        return {**record, "output": output}

    def capture_screen(self, label: str = "screen", prefetched_xml: str = "") -> Dict:
        label = safe_name(label, "screen")
        folder = self.run_dir / "screens" / label
        suffix = 1
        while folder.exists():
            suffix += 1
            folder = self.run_dir / "screens" / f"{label}_{suffix:03d}"
        folder.mkdir(parents=True)
        remote_base = f"/sdcard/ascend_mapper_{os.getpid()}"

        xml_text = prefetched_xml if "<hierarchy" in (prefetched_xml or "") else ""
        attempts = []
        if xml_text:
            xml_text = xml_text[xml_text.index("<hierarchy"):]
            attempts.append({"name": "prefetched", "ok": True, "seconds": 0, "bytes": len(xml_text)})
        else:
            for name, command in (
                ("compressed", f"uiautomator dump --compressed {remote_base}.xml >/dev/null 2>&1; cat {remote_base}.xml"),
                ("standard", f"uiautomator dump {remote_base}.xml >/dev/null 2>&1; cat {remote_base}.xml"),
                ("stdout", "uiautomator dump --compressed /dev/tty 2>/dev/null"),
            ):
                ok, output, elapsed = self.shell(command, 15)
                attempts.append({"name": name, "ok": ok, "seconds": round(elapsed, 3), "bytes": len(output)})
                if "<hierarchy" in output:
                    xml_text = output[output.index("<hierarchy"):]
                    break

        (folder / "window.xml").write_text(xml_text, encoding="utf-8", errors="replace")
        try:
            nodes = parse_ui_xml(xml_text)
            parse_error = ""
        except Exception as exc:
            nodes = []
            parse_error = f"{exc.__class__.__name__}: {exc}"
        (folder / "nodes.json").write_text(json.dumps(nodes, indent=2, ensure_ascii=False), encoding="utf-8")
        self._write_nodes_csv(folder / "nodes.csv", nodes)

        screenshot_path = folder / "screen.png"
        shot_ok, shot_out, shot_elapsed = self.shell(f"screencap -p {remote_base}.png", 15)
        pull_error = ""
        if shot_ok:
            try:
                self.device.pull(str(remote_base + ".png"), str(screenshot_path), read_timeout_s=30)
            except Exception as exc:
                pull_error = f"{exc.__class__.__name__}: {exc}"
        self.shell(f"rm -f {remote_base}.xml {remote_base}.png", 5)

        focus = {}
        for name, command in {
            "window_focus": "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'",
            "resumed_activity": "dumpsys activity activities | grep mResumedActivity",
            "media_state": "dumpsys media_session | grep -E 'package=|state=PlaybackState|description='",
        }.items():
            _ok, output, _elapsed = self.shell(command, 8)
            focus[name] = output.strip()
        (folder / "focus.json").write_text(json.dumps(focus, indent=2, ensure_ascii=False), encoding="utf-8")

        summary = {
            "label": folder.name,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "xml_sha256": hashlib.sha256(xml_text.encode("utf-8", errors="replace")).hexdigest(),
            "node_count": len(nodes),
            "text_count": sum(bool(n["text"]) for n in nodes),
            "description_count": sum(bool(n["content_desc"]) for n in nodes),
            "clickable_count": sum(bool(n["clickable"]) for n in nodes),
            "focusable_count": sum(bool(n["focusable"]) for n in nodes),
            "focused": [n["index"] for n in nodes if n["focused"]],
            "packages": sorted({n["package"] for n in nodes if n["package"]}),
            "xml_attempts": attempts,
            "parse_error": parse_error,
            "screenshot_ok": screenshot_path.exists(),
            "screenshot_shell_ok": shot_ok,
            "screenshot_shell_output": shot_out[:500],
            "screenshot_seconds": round(shot_elapsed, 3),
            "pull_error": pull_error,
            "path": str(folder.relative_to(self.run_dir)),
            "focus": focus,
        }
        (folder / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        self._write_html_report(folder, nodes, summary)
        self.manifest["screens"].append(summary)
        print(f"[UI] {folder.name}: {len(nodes)} nodes, {summary['clickable_count']} clickable, {summary['focusable_count']} focusable")
        return {"folder": folder, "nodes": nodes, "summary": summary}

    @staticmethod
    def _write_nodes_csv(path: Path, nodes: List[Dict]):
        fields = [
            "index", "parent_index", "depth", "text", "content_desc", "resource_id", "class", "package",
            "bounds", "center_x", "center_y", "width", "height", "clickable", "long_clickable", "focusable",
            "focused", "enabled", "selected", "scrollable", "checkable", "checked", "password",
            "tap_command", "long_press_command",
        ]
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(nodes)

    @staticmethod
    def _write_html_report(folder: Path, nodes: List[Dict], summary: Dict):
        safe_nodes = json.dumps(nodes, ensure_ascii=False).replace("</", "<\\/")
        rows = []
        for node in nodes:
            label = node["text"] or node["content_desc"] or node["resource_id"] or node["class"]
            flags = ", ".join(k for k in ("clickable", "long_clickable", "focusable", "focused", "scrollable", "selected") if node.get(k))
            rows.append(
                f"<tr data-index='{node['index']}'><td>{node['index']}</td><td>{html.escape(label)}</td>"
                f"<td>{html.escape(node['package'])}</td><td>{html.escape(node['class'])}</td>"
                f"<td>{html.escape(node['resource_id'])}</td><td>{html.escape(node['bounds'])}</td>"
                f"<td>{html.escape(flags)}</td><td><code>{html.escape(node['tap_command'])}</code></td></tr>"
            )
        image_html = "<img id='shot' src='screen.png' alt='ADB screenshot'>" if summary["screenshot_ok"] else "<div class='missing'>Screenshot unavailable</div>"
        doc = f"""<!doctype html><html><head><meta charset='utf-8'><title>ADB UI map</title>
<style>body{{background:#0b1020;color:#e7ecff;font:14px system-ui;margin:20px}}h1{{margin-bottom:4px}}.stats{{color:#9fb0dc}}#stage{{position:relative;display:inline-block;max-width:100%;margin:16px 0}}#shot{{max-width:100%;height:auto;display:block}}#overlay{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}}input{{width:min(700px,90%);padding:10px;background:#121a31;color:white;border:1px solid #42527b}}table{{border-collapse:collapse;width:100%;margin-top:12px}}th,td{{border:1px solid #273354;padding:6px;text-align:left;vertical-align:top}}th{{position:sticky;top:0;background:#15203c}}tr:hover{{background:#1d2a4c}}code{{font-size:12px}}.missing{{padding:80px;border:1px solid #42527b}}</style></head>
<body><h1>ADB UI map: {html.escape(summary['label'])}</h1><div class='stats'>{summary['node_count']} nodes · {summary['clickable_count']} clickable · {summary['focusable_count']} focusable · packages: {html.escape(', '.join(summary['packages']))}</div>
<div id='stage'>{image_html}<canvas id='overlay'></canvas></div><div><input id='filter' placeholder='Filter text, description, resource ID, package, class, flags, bounds'></div>
<table><thead><tr><th>#</th><th>Text / description</th><th>Package</th><th>Class</th><th>Resource ID</th><th>Bounds</th><th>Flags</th><th>Safe tap command</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<script>const nodes={safe_nodes};const shot=document.getElementById('shot'),canvas=document.getElementById('overlay');function draw(){{if(!shot||!shot.naturalWidth)return;canvas.width=shot.clientWidth;canvas.height=shot.clientHeight;const c=canvas.getContext('2d'),sx=canvas.width/shot.naturalWidth,sy=canvas.height/shot.naturalHeight;c.clearRect(0,0,canvas.width,canvas.height);nodes.forEach(n=>{{if(n.x1===null)return;c.strokeStyle=n.focused?'#00ff88':n.clickable?'#ff3b6b':n.focusable?'#ffd43b':'#39a0ff';c.lineWidth=n.focused?4:1;c.strokeRect(n.x1*sx,n.y1*sy,n.width*sx,n.height*sy);if(n.clickable||n.focused){{c.fillStyle=c.strokeStyle;c.font='12px sans-serif';c.fillText(n.index,n.x1*sx+2,n.y1*sy+12)}}}})}}if(shot){{shot.onload=draw;window.addEventListener('resize',draw)}}document.getElementById('filter').addEventListener('input',e=>{{const q=e.target.value.toLowerCase();document.querySelectorAll('tbody tr').forEach(r=>r.style.display=r.innerText.toLowerCase().includes(q)?'':'none')}});</script></body></html>"""
        (folder / "report.html").write_text(doc, encoding="utf-8")

    def run_curated(self):
        for probe in CURATED_PROBES:
            if self._user_stop.is_set():
                break
            self.save_probe(probe)

    def dump_every_service(self):
        print("[MAX] Enumerating every dumpsys service...")
        result = self.save_probe(Probe("maximum", "dumpsys_service_list", "dumpsys -l", 20))
        services = parse_service_names(result.get("output", ""))
        self.manifest["dumpsys_service_count"] = len(services)
        for index, service in enumerate(services, 1):
            if self._user_stop.is_set():
                break
            print(f"[MAX] Service {index}/{len(services)}: {service}")
            self.save_probe(Probe("all_dumpsys_services", service, f"dumpsys {service}", 40, sensitive=True))

    def dump_every_package(self):
        print("[MAX] Enumerating every installed package...")
        ok, output, _elapsed = self.shell("pm list packages", 30)
        packages = parse_package_names(output) if ok else []
        self.manifest["package_count"] = len(packages)
        for index, package in enumerate(packages, 1):
            if self._user_stop.is_set():
                break
            if not SAFE_SHELL_NAME_RE.fullmatch(package):
                continue
            print(f"[MAX] Package {index}/{len(packages)}: {package}")
            self.save_probe(Probe("all_packages", f"{package}__package", f"dumpsys package {package}", 35, sensitive=True))
            self.save_probe(Probe("all_packages", f"{package}__appops", f"cmd appops get {package} 2>/dev/null", 20, sensitive=True))
            self.save_probe(Probe("all_packages", f"{package}__activity", f"dumpsys activity package {package} 2>/dev/null", 20, sensitive=True))

    def finalize(self):
        self._write_global_ui_catalogs()
        self.manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.manifest["probe_count"] = len(self.manifest["probes"])
        self.manifest["probe_failures"] = sum(1 for p in self.manifest["probes"] if p.get("ok") is False)
        manifest_path = self.run_dir / "manifest.json"
        manifest_path.write_text(json.dumps(self.manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        index = ["# Ascend Deep ADB Map", "", f"Device: {self.manifest['device']}", f"Target: {self.host}:{self.port}", "", "## Screen reports", ""]
        for screen in self.manifest["screens"]:
            index.append(f"- [{screen['label']}](screens/{screen['label']}/report.html) — {screen['node_count']} nodes")
        index += ["", "See `manifest.json` for every diagnostic file and status."]
        (self.run_dir / "README.md").write_text("\n".join(index), encoding="utf-8")
        print(f"[DONE] Map complete: {self.run_dir}")
        print(f"[OPEN] {self.run_dir / 'screens' / self.manifest['screens'][0]['label'] / 'report.html' if self.manifest['screens'] else self.run_dir}")

    def _write_global_ui_catalogs(self):
        """Merge all changed screens into run-wide text/control indexes."""
        catalog_dir = self.run_dir / "catalogs"
        catalog_dir.mkdir(parents=True, exist_ok=True)
        all_nodes = []
        unique: Dict[str, Dict] = {}
        text_lines = []
        for screen_number, screen in enumerate(self.manifest.get("screens", []), 1):
            nodes_path = self.run_dir / screen["path"] / "nodes.json"
            try:
                nodes = json.loads(nodes_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for node in nodes:
                row = {"screen_number": screen_number, "screen": screen["label"], "captured_at": screen["captured_at"], **node}
                all_nodes.append(row)
                label = node.get("text") or node.get("content_desc")
                if label:
                    text_lines.append(f"{screen_number:05d}\t{screen['label']}\t{node.get('package', '')}\t{label}")
                identity_parts = [
                    node.get("package", ""), node.get("resource_id", ""), node.get("class", ""),
                    node.get("text", ""), node.get("content_desc", ""), node.get("bounds", ""),
                ]
                identity = "|".join(str(part) for part in identity_parts)
                key = hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest()[:20]
                entry = unique.setdefault(key, {
                    "element_id": key,
                    "package": node.get("package", ""),
                    "resource_id": node.get("resource_id", ""),
                    "class": node.get("class", ""),
                    "text": node.get("text", ""),
                    "content_desc": node.get("content_desc", ""),
                    "bounds": node.get("bounds", ""),
                    "clickable": node.get("clickable", False),
                    "focusable": node.get("focusable", False),
                    "long_clickable": node.get("long_clickable", False),
                    "screens": [],
                    "occurrences": 0,
                })
                entry["occurrences"] += 1
                if screen["label"] not in entry["screens"]:
                    entry["screens"].append(screen["label"])

        fields = [
            "screen_number", "screen", "captured_at", "index", "parent_index", "depth", "text", "content_desc",
            "resource_id", "class", "package", "bounds", "center_x", "center_y", "width", "height", "clickable",
            "long_clickable", "focusable", "focused", "enabled", "selected", "scrollable", "checkable", "checked",
            "password", "tap_command", "long_press_command",
        ]
        with (catalog_dir / "all_ui_nodes.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_nodes)
        with (catalog_dir / "all_click_targets.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(node for node in all_nodes if node.get("clickable") or node.get("focusable") or node.get("long_clickable"))
        (catalog_dir / "all_visible_text.txt").write_text("\n".join(text_lines), encoding="utf-8")
        (catalog_dir / "unique_ui_elements.json").write_text(
            json.dumps(list(unique.values()), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (catalog_dir / "screen_timeline.json").write_text(
            json.dumps(self.manifest.get("screens", []), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.manifest["ui_catalog"] = {
            "screen_count": len(self.manifest.get("screens", [])),
            "node_occurrences": len(all_nodes),
            "unique_elements": len(unique),
            "click_target_occurrences": sum(bool(n.get("clickable") or n.get("focusable") or n.get("long_clickable")) for n in all_nodes),
            "path": "catalogs",
        }

    def watch(self, seconds: int, interval: float, until_stopped: bool = False):
        deadline = None if until_stopped else time.monotonic() + max(1, seconds)
        last_hash = None
        count = 0
        duration_text = "until you stop it" if until_stopped else f"for {seconds}s"
        print(f"[WATCH] Watching UI changes {duration_text}. Use the remote normally.")
        while not self._user_stop.is_set() and (deadline is None or time.monotonic() < deadline):
            ok, output, _elapsed = self.shell("uiautomator dump --compressed /sdcard/ascend_watch.xml >/dev/null 2>&1; cat /sdcard/ascend_watch.xml", 12)
            if ok and "<hierarchy" in output:
                xml_text = output[output.index("<hierarchy"):]
                digest = hashlib.sha256(xml_text.encode("utf-8", errors="replace")).hexdigest()
                if digest != last_hash:
                    count += 1
                    captured = self.capture_screen(f"watch_{count:04d}", prefetched_xml=xml_text)
                    last_hash = captured["summary"].get("xml_sha256") or digest
            time.sleep(max(0.25, interval))
        self.shell("rm -f /sdcard/ascend_watch.xml", 5)

    def start_stop_listener(self):
        """Let the user stop a long scan without losing completed captures."""
        if self._stop_listener and self._stop_listener.is_alive():
            return

        def listen():
            try:
                input("\n[CONTROL] Press ENTER at any time to stop mapping and build the final catalogs...\n")
            except EOFError:
                pass
            self._user_stop.set()
            self._watch_stop.set()
            print("[CONTROL] Stop requested. Finishing the current ADB command...")

        self._stop_listener = threading.Thread(target=listen, name="adb-stop-listener", daemon=True)
        self._stop_listener.start()

    def wait_for_user_stop(self):
        while not self._user_stop.wait(0.25):
            pass

    def start_background_screen_watcher(self, interval: float = 0.1):
        """Capture every distinct screen while the primary connection runs probes."""
        if self._watch_thread and self._watch_thread.is_alive():
            return
        self._watch_stop.clear()

        def worker():
            watcher = DeepMapper(self.host, self.port, self.output_root, self.include_sensitive)
            watcher.run_dir = self.run_dir
            watcher.manifest = self.manifest
            watcher.controller = StremioController(self.host, self.port)
            if not watcher.controller.connect():
                self.manifest["background_watch_error"] = watcher.controller.last_connect_error or "connection failed"
                return
            watcher.device = watcher.controller.device
            last_hash = self.manifest["screens"][-1].get("xml_sha256") if self.manifest["screens"] else None
            count = 0
            print("[WATCH] Continuous changed-screen capture started. Move around with the remote.")
            try:
                while not self._watch_stop.is_set() and not self._user_stop.is_set():
                    ok, output, _elapsed = watcher.shell(
                        "uiautomator dump --compressed /sdcard/ascend_background_watch.xml >/dev/null 2>&1; cat /sdcard/ascend_background_watch.xml",
                        12,
                    )
                    if ok and "<hierarchy" in output:
                        xml_text = output[output.index("<hierarchy"):]
                        digest = hashlib.sha256(xml_text.encode("utf-8", errors="replace")).hexdigest()
                        if digest != last_hash:
                            count += 1
                            # Reuse the hierarchy that triggered the change;
                            # another uiautomator dump would lose 1-3 seconds.
                            captured = watcher.capture_screen(f"changed_{count:05d}", prefetched_xml=xml_text)
                            last_hash = captured["summary"].get("xml_sha256") or digest
                    self._watch_stop.wait(max(0.35, interval))
            finally:
                watcher.shell("rm -f /sdcard/ascend_background_watch.xml", 5)
                watcher.close()
                self.manifest["background_changed_screens"] = count
                print(f"[WATCH] Continuous capture stopped after {count} changed screens.")

        self._watch_thread = threading.Thread(target=worker, name="adb-screen-watcher", daemon=True)
        self._watch_thread.start()

    def start_rapid_frame_watcher(self, interval: float = 0.5):
        """Capture deduplicated screenshots independently of slow UIAutomator."""
        if self._frame_thread and self._frame_thread.is_alive():
            return

        def worker():
            controller = StremioController(self.host, self.port)
            if not controller.connect():
                self.manifest["rapid_frame_error"] = controller.last_connect_error or "connection failed"
                return
            device = controller.device
            frame_dir = self.run_dir / "rapid_frames"
            frame_dir.mkdir(parents=True, exist_ok=True)
            remote = f"/sdcard/ascend_rapid_frame_{os.getpid()}.png"
            frame_number = 0
            kept = 0
            duplicate = 0
            last_hash = None
            timeline_path = frame_dir / "timeline.jsonl"
            print(f"[RAPID] Screenshot recorder started (target interval {interval:.2f}s).")
            try:
                while not self._watch_stop.is_set() and not self._user_stop.is_set():
                    cycle_started = time.monotonic()
                    frame_number += 1
                    path = frame_dir / f"frame_{frame_number:07d}.png"
                    ok = False
                    error = ""
                    try:
                        device.shell(f"screencap -p {remote}", timeout_s=8)
                        device.pull(remote, str(path), read_timeout_s=15)
                        ok = path.exists() and path.stat().st_size > 0
                    except Exception as exc:
                        error = f"{exc.__class__.__name__}: {exc}"
                    digest = ""
                    changed = False
                    if ok:
                        digest = hashlib.sha256(path.read_bytes()).hexdigest()
                        changed = digest != last_hash
                        if changed:
                            kept += 1
                            last_hash = digest
                        else:
                            duplicate += 1
                            try:
                                path.unlink()
                            except OSError:
                                pass
                    event = {
                        "attempt": frame_number,
                        "kept_number": kept if changed else None,
                        "captured_at": datetime.now(timezone.utc).isoformat(),
                        "changed": changed,
                        "sha256": digest,
                        "path": str(path.relative_to(self.run_dir)) if changed else "",
                        "error": error,
                        "seconds": round(time.monotonic() - cycle_started, 3),
                    }
                    with timeline_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(event) + "\n")
                    remaining = max(0.0, interval - (time.monotonic() - cycle_started))
                    self._watch_stop.wait(remaining)
            finally:
                try:
                    device.shell(f"rm -f {remote}", timeout_s=5)
                except Exception:
                    pass
                controller.mark_disconnected("rapid mapper complete")
                self.manifest["rapid_frames"] = {
                    "attempted": frame_number,
                    "kept_changed": kept,
                    "deduplicated": duplicate,
                    "target_interval_seconds": interval,
                    "path": "rapid_frames",
                }
                print(f"[RAPID] Screenshot recorder stopped: {kept} changed frames kept, {duplicate} duplicates removed.")

        self._frame_thread = threading.Thread(target=worker, name="adb-rapid-frames", daemon=True)
        self._frame_thread.start()

    def stop_background_screen_watcher(self):
        self._watch_stop.set()
        if self._watch_thread:
            self._watch_thread.join(timeout=90)
            if self._watch_thread.is_alive():
                self.manifest["background_watch_error"] = "watcher did not stop within 90 seconds"
            self._watch_thread = None
        if self._frame_thread:
            self._frame_thread.join(timeout=45)
            if self._frame_thread.is_alive():
                self.manifest["rapid_frame_error"] = "rapid frame watcher did not stop within 45 seconds"
            self._frame_thread = None

    def focus_scan(self, rounds: int):
        directions = [(19, "up"), (22, "right"), (20, "down"), (21, "left")]
        transitions = []
        current = self.capture_screen("focus_start")
        for step in range(max(1, rounds) * len(directions)):
            keycode, name = directions[step % len(directions)]
            before = current["summary"].get("focused", [])
            self.shell(f"input keyevent {keycode}", 5)
            time.sleep(0.35)
            current = self.capture_screen(f"focus_{step + 1:03d}_{name}")
            after = current["summary"].get("focused", [])
            transitions.append({"step": step + 1, "direction": name, "keycode": keycode, "before": before, "after": after, "screen": current["summary"]["label"]})
        (self.run_dir / "focus_transitions.json").write_text(json.dumps(transitions, indent=2), encoding="utf-8")

    def interactive(self):
        count = 0
        while True:
            count += 1
            captured = self.capture_screen(f"interactive_{count:04d}")
            actionable = [n for n in captured["nodes"] if n.get("clickable") or n.get("focusable") or n.get("long_clickable")]
            print("\n#   C F L  CENTER       TEXT / DESCRIPTION / RESOURCE")
            for node in actionable:
                label = node["text"] or node["content_desc"] or node["resource_id"] or node["class"]
                print(f"{node['index']:3} {int(node['clickable'])} {int(node['focusable'])} {int(node['long_clickable'])}  ({node['center_x']},{node['center_y']})  {label[:100]}")
            print("\nCommands: tap N | long N | key up/down/left/right/center/back/home/playpause | snap | quit")
            raw = input("mapper> ").strip().lower()
            if raw in {"q", "quit", "exit"}:
                return
            if raw in {"s", "snap", "snapshot"}:
                continue
            parts = raw.split()
            if len(parts) != 2:
                print("Invalid command.")
                continue
            action, value = parts
            command = None
            description = raw
            if action in {"tap", "long"} and value.isdigit():
                index = int(value)
                node = next((n for n in actionable if n["index"] == index), None)
                if node:
                    command = node["tap_command"] if action == "tap" else node["long_press_command"]
                    description = f"{action} node {index}: {node['text'] or node['content_desc'] or node['resource_id']}"
            elif action == "key":
                keycodes = {"up": 19, "down": 20, "left": 21, "right": 22, "center": 23, "back": 4, "home": 3, "playpause": 85}
                if value in keycodes:
                    command = f"input keyevent {keycodes[value]}"
            if not command:
                print("Unknown or unavailable target.")
                continue
            answer = input(f"CONFIRM state-changing action '{description}'? Type YES: ").strip()
            if answer != "YES":
                print("Cancelled.")
                continue
            ok, output, elapsed = self.shell(command, 8)
            event = {"at": datetime.now(timezone.utc).isoformat(), "action": description, "command": command, "ok": ok, "output": output, "seconds": elapsed}
            with (self.run_dir / "interactive_actions.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            time.sleep(0.7)


def build_parser():
    parser = argparse.ArgumentParser(description="Maximum-depth Android TV ADB mapper")
    parser.add_argument("mode", choices=("maximum", "full", "screen", "watch", "focus", "interactive"), nargs="?", default="maximum")
    parser.add_argument("--host", default=os.environ.get("ASCEND_TV_HOST", ""))
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--output", default=str(PROJECT_ROOT / "adb_maps"))
    parser.add_argument("--include-sensitive", action="store_true", help="Include settings, logs, notifications, accounts, network details, and other private diagnostics")
    parser.add_argument("--seconds", type=int, default=120, help="Watch duration")
    parser.add_argument("--interval", type=float, default=1.0, help="Watch polling interval")
    parser.add_argument("--frame-interval", type=float, default=0.5, help="Rapid screenshot target interval")
    parser.add_argument("--rounds", type=int, default=3, help="Directional focus scan rounds")
    parser.add_argument("--until-stopped", action="store_true", help="Keep recording until Enter or Ctrl+C")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    mapper = DeepMapper(args.host, args.port, Path(args.output).resolve(), args.include_sensitive)
    try:
        mapper.connect()
        mapper.capture_screen("initial")
        if args.until_stopped and args.mode in {"maximum", "full", "watch"}:
            mapper.start_stop_listener()
        if args.mode in {"full", "maximum"}:
            mapper.start_background_screen_watcher(args.interval)
            mapper.start_rapid_frame_watcher(args.frame_interval)
            try:
                mapper.run_curated()
                if args.mode == "maximum" and not mapper._user_stop.is_set():
                    mapper.dump_every_service()
                    if not mapper._user_stop.is_set():
                        mapper.dump_every_package()
                if args.until_stopped and not mapper._user_stop.is_set():
                    print("[CONTROL] Deep diagnostics finished; changed-screen recording is still running.")
                    mapper.wait_for_user_stop()
            finally:
                mapper.stop_background_screen_watcher()
        elif args.mode == "watch":
            mapper.start_rapid_frame_watcher(args.frame_interval)
            try:
                mapper.watch(args.seconds, args.interval, args.until_stopped)
            finally:
                mapper.stop_background_screen_watcher()
        elif args.mode == "focus":
            mapper.focus_scan(args.rounds)
        elif args.mode == "interactive":
            mapper.interactive()
        mapper.finalize()
        return 0
    except KeyboardInterrupt:
        print("\n[STOP] Mapper interrupted by user.")
        if mapper.run_dir:
            mapper.finalize()
        return 130
    except Exception as exc:
        print(f"[ERROR] {exc.__class__.__name__}: {exc}")
        return 1
    finally:
        mapper.close()


if __name__ == "__main__":
    raise SystemExit(main())
