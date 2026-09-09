import os
import queue
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "Ascend Vencord Installer"
PATCHSET_URL = "https://github.com/Davilarek/BetterVencordPatchset.git"
PNPM_VERSION = "10.32.1"

BASE_DIR = Path(__file__).resolve().parent
PATCHSET_DIR = BASE_DIR / "BetterVencordPatchset"
PLUGINS_FILE = BASE_DIR / "plugins.txt"
LOCAL_PLUGINS_DIR = BASE_DIR / "local_plugins"
BUNDLED_PLUGINS_DIR = BASE_DIR / "bundled_plugins"
PNPM_TOOLS_DIR = BASE_DIR / ".installer_tools"
PNPM_BIN_DIR = PNPM_TOOLS_DIR / "node_modules" / ".bin"


DISCORD_TARGETS = {
    "stable": {
        "label": "Discord Stable",
        "folder": "Discord",
        "process": "Discord.exe",
    },
    "ptb": {
        "label": "Discord PTB",
        "folder": "DiscordPTB",
        "process": "DiscordPTB.exe",
    },
    "canary": {
        "label": "Discord Canary",
        "folder": "DiscordCanary",
        "process": "DiscordCanary.exe",
    },
    "development": {
        "label": "Discord Development",
        "folder": "DiscordDevelopment",
        "process": "DiscordDevelopment.exe",
    },
}


def local_app_data() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")


def installer_env(env=None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    merged["PATH"] = str(PNPM_BIN_DIR) + os.pathsep + merged.get("PATH", "")
    return merged


def run_process(args, cwd=None, env=None):
    run_env = installer_env(env)
    command = shutil.which(args[0], path=run_env.get("PATH")) or args[0]
    args = [command, *args[1:]]
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=run_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
    )


def command_exists(command: str) -> bool:
    return shutil.which(command, path=installer_env().get("PATH")) is not None


def portable_pnpm_exists() -> bool:
    suffix = ".cmd" if os.name == "nt" else ""
    return (PNPM_BIN_DIR / f"pnpm{suffix}").exists() or (PNPM_BIN_DIR / "pnpm.exe").exists() or (PNPM_BIN_DIR / "pnpm").exists()


def repo_name_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1].removesuffix(".git")


def discord_app_dirs(install_path: Path) -> list[Path]:
    return sorted(
        (
            path for path in install_path.glob("app-*")
            if path.is_dir() and (path / "resources").is_dir()
        ),
        key=lambda path: path.name,
        reverse=True,
    )


class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1060x760")
        self.minsize(920, 640)
        self.configure(bg="#101419")

        self.log_queue = queue.Queue()
        self.worker = None
        self.target_vars = {}
        self.custom_path = tk.StringVar(value="")
        self.status_text = tk.StringVar(value="Ready")
        self.progress = tk.IntVar(value=0)
        self.close_discord = tk.BooleanVar(value=True)
        self.skip_update = tk.BooleanVar(value=False)

        self._build_style()
        self._build_ui()
        self._detect_targets()
        self.after(100, self._drain_logs)

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#101419")
        style.configure("Card.TFrame", background="#161c23", relief="flat")
        style.configure("TLabel", background="#101419", foreground="#d7e3ef")
        style.configure("Card.TLabel", background="#161c23", foreground="#d7e3ef")
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"), foreground="#ffffff", background="#101419")
        style.configure("Subtle.TLabel", foreground="#8fa3b7", background="#101419")
        style.configure("CardSubtle.TLabel", foreground="#8fa3b7", background="#161c23")
        style.configure("TButton", padding=8)
        style.configure("Accent.TButton", padding=10, font=("Segoe UI", 10, "bold"))
        style.configure("TCheckbutton", background="#161c23", foreground="#d7e3ef")
        style.map("TCheckbutton", background=[("active", "#1d2630")], foreground=[("active", "#ffffff")])
        style.configure("Horizontal.TProgressbar", background="#35c2ff", troughcolor="#0c1015")

    def _build_ui(self):
        header = ttk.Frame(self, padding=(22, 18, 22, 10))
        header.pack(fill="x")
        ttk.Label(header, text="Ascend Vencord Installer", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Build the Ascend-ready Equicord/Vencord bundle, sync plugins, and inject into Stable, PTB, Canary, or Development.",
            style="Subtle.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        body = ttk.Frame(self, padding=(22, 8, 22, 22))
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body, style="Card.TFrame", padding=16)
        left.pack(side="left", fill="y", padx=(0, 14))

        ttk.Label(left, text="Discord Targets", style="Card.TLabel", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(left, text="Detected installs are selected automatically.", style="CardSubtle.TLabel").pack(anchor="w", pady=(0, 10))

        self.targets_frame = ttk.Frame(left, style="Card.TFrame")
        self.targets_frame.pack(fill="x")
        for key, meta in DISCORD_TARGETS.items():
            var = tk.BooleanVar(value=False)
            self.target_vars[key] = var
            ttk.Checkbutton(self.targets_frame, text=meta["label"], variable=var).pack(anchor="w", pady=4)

        ttk.Separator(left).pack(fill="x", pady=14)
        ttk.Label(left, text="Custom Discord Folder", style="Card.TLabel", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Entry(left, textvariable=self.custom_path, width=42).pack(fill="x", pady=(6, 6))
        ttk.Button(left, text="Browse...", command=self._browse_custom).pack(anchor="w")

        ttk.Separator(left).pack(fill="x", pady=14)
        ttk.Checkbutton(left, text="Close Discord before injection", variable=self.close_discord).pack(anchor="w", pady=3)
        ttk.Checkbutton(left, text="Skip patchset git update", variable=self.skip_update).pack(anchor="w", pady=3)

        ttk.Separator(left).pack(fill="x", pady=14)
        ttk.Label(left, text="Plugin Sources", style="Card.TLabel", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Button(left, text="Open plugins.txt", command=lambda: self._open_path(PLUGINS_FILE)).pack(fill="x", pady=(8, 4))
        ttk.Button(left, text="Open local_plugins folder", command=self._open_local_plugins).pack(fill="x", pady=4)

        ttk.Separator(left).pack(fill="x", pady=14)
        ttk.Button(left, text="Check Requirements", command=self._start_check).pack(fill="x", pady=4)
        ttk.Button(left, text="Install / Repair portable pnpm", command=self._start_pnpm_setup).pack(fill="x", pady=4)
        ttk.Button(left, text="Build + Inject", style="Accent.TButton", command=self._start_install).pack(fill="x", pady=(12, 4))

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        status = ttk.Frame(right, style="Card.TFrame", padding=14)
        status.pack(fill="x", pady=(0, 12))
        ttk.Label(status, textvariable=self.status_text, style="Card.TLabel", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Progressbar(status, variable=self.progress, maximum=100).pack(fill="x", pady=(10, 0))
        action_row = ttk.Frame(status, style="Card.TFrame")
        action_row.pack(fill="x", pady=(12, 0))
        ttk.Button(action_row, text="Check Requirements", command=self._start_check).pack(side="left", padx=(0, 8))
        ttk.Button(action_row, text="Install / Repair portable pnpm", command=self._start_pnpm_setup).pack(side="left", padx=(0, 8))
        ttk.Button(action_row, text="Build + Inject", style="Accent.TButton", command=self._start_install).pack(side="left")

        log_card = ttk.Frame(right, style="Card.TFrame", padding=12)
        log_card.pack(fill="both", expand=True)
        ttk.Label(log_card, text="Installer Log", style="Card.TLabel", font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 8))
        self.log = tk.Text(
            log_card,
            bg="#0a0f14",
            fg="#d7e3ef",
            insertbackground="#ffffff",
            relief="flat",
            wrap="word",
            font=("Cascadia Mono", 10),
        )
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("ok", foreground="#7CFFB2")
        self.log.tag_configure("warn", foreground="#FFD36E")
        self.log.tag_configure("err", foreground="#FF7A7A")
        self.log.tag_configure("info", foreground="#7DD3FC")

    def _detect_targets(self):
        base = local_app_data()
        for key, meta in DISCORD_TARGETS.items():
            path = base / meta["folder"]
            exists = path.exists()
            self.target_vars[key].set(exists)
            self._log(f"{meta['label']}: {'found' if exists else 'not found'} at {path}", "ok" if exists else "warn")

    def _browse_custom(self):
        folder = filedialog.askdirectory(title="Select Discord install folder")
        if folder:
            self.custom_path.set(folder)

    def _open_path(self, path: Path):
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        os.startfile(path)

    def _open_local_plugins(self):
        LOCAL_PLUGINS_DIR.mkdir(exist_ok=True)
        os.startfile(LOCAL_PLUGINS_DIR)

    def _start_check(self):
        self._run_thread(self.check_requirements)

    def _start_pnpm_setup(self):
        self._run_thread(self.setup_pnpm)

    def _start_install(self):
        self._run_thread(self.install)

    def _run_thread(self, func):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_TITLE, "An installer task is already running.")
            return
        self.worker = threading.Thread(target=func, daemon=True)
        self.worker.start()

    def _log(self, message, tag="info"):
        self.log_queue.put((message, tag))

    def _set_status(self, message, progress=None):
        self.log_queue.put(("__status__", message, progress))

    def _drain_logs(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item[0] == "__status__":
                    _, message, progress = item
                    self.status_text.set(message)
                    if progress is not None:
                        self.progress.set(progress)
                    continue
                message, tag = item
                self.log.insert("end", message + "\n", tag)
                self.log.see("end")
        except queue.Empty:
            pass
        self.after(100, self._drain_logs)

    def check_requirements(self):
        self._set_status("Checking requirements...", 5)
        ok = True
        for tool in ("git", "node"):
            exists = command_exists(tool)
            self._log(f"{tool}: {'found' if exists else 'missing'}", "ok" if exists else "err")
            ok = ok and exists

        if command_exists("node"):
            result = run_process(["node", "--version"])
            self._log(f"Node version: {result.stdout.strip()}", "info")

        pnpm_exists = portable_pnpm_exists()
        npm_exists = command_exists("npm")
        self._log(f"portable pnpm: {'found' if pnpm_exists else 'missing'} at {PNPM_BIN_DIR}", "ok" if pnpm_exists else "warn")
        self._log(f"npm: {'found' if npm_exists else 'missing'}", "ok" if npm_exists else "warn")
        if not pnpm_exists and not npm_exists:
            ok = False

        if ok:
            self._set_status("Requirements look good.", 100)
        else:
            self._set_status("Missing requirements. Install Git + Node.js, then run portable pnpm repair.", 100)

    def setup_pnpm(self):
        self._set_status("Installing / repairing portable pnpm...", 20)

        if os.name == "nt":
            import urllib.request
            PNPM_BIN_DIR.mkdir(parents=True, exist_ok=True)
            pnpm_exe = PNPM_BIN_DIR / "pnpm.exe"
            url = f"https://github.com/pnpm/pnpm/releases/download/v{PNPM_VERSION}/pnpm-win-x64.exe"
            
            try:
                self._log(f"Downloading pnpm {PNPM_VERSION} standalone binary...", "info")
                urllib.request.urlretrieve(url, pnpm_exe)
                self._log("Download complete.", "ok")
                
                version = run_process([str(pnpm_exe), "--version"])
                if version.returncode == 0:
                    self._log(f"portable pnpm is ready: {version.stdout.strip()}", "ok")
                    self._set_status("portable pnpm setup complete.", 100)
                    return
                else:
                    self._log("Standalone binary failed test, falling back to npm...", "warn")
            except Exception as e:
                self._log(f"Standalone download failed: {e}. Falling back to npm...", "warn")
                if pnpm_exe.exists():
                    try:
                        pnpm_exe.unlink()
                    except OSError:
                        pass

        if not command_exists("node"):
            self._log("Node.js is missing. Install it from https://nodejs.org/ or use winget install OpenJS.NodeJS.LTS", "err")
            self._set_status("Node.js missing.", 100)
            return

        if not command_exists("npm"):
            self._log("npm was not found. Reinstall Node.js with npm enabled.", "err")
            self._set_status("npm missing.", 100)
            return

        self._log(f"Installing pnpm {PNPM_VERSION} into {PNPM_TOOLS_DIR}.", "info")
        result = run_process(["npm", "install", "--prefix", str(PNPM_TOOLS_DIR), f"pnpm@{PNPM_VERSION}"])
        self._log(result.stdout.strip(), "ok" if result.returncode == 0 else "err")

        if portable_pnpm_exists():
            version = run_process(["pnpm", "--version"])
            self._log(f"portable pnpm is ready: {version.stdout.strip()}", "ok")
        else:
            self._log("portable pnpm setup failed. Check the npm output above.", "err")

        self._set_status("portable pnpm setup complete.", 100)

    def selected_targets(self):
        base = local_app_data()
        targets = []
        for key, var in self.target_vars.items():
            if var.get():
                meta = DISCORD_TARGETS[key]
                targets.append((meta["label"], base / meta["folder"], meta["process"]))
        custom = self.custom_path.get().strip()
        if custom:
            targets.append(("Custom Discord", Path(custom), None))
        return targets

    def install(self):
        try:
            self._set_status("Starting Ascend Vencord build...", 2)
            if not self._ensure_requirements_for_install():
                return
            self._close_discord_processes()
            self._sync_patchset()
            self._build_patchset()
            equicord = PATCHSET_DIR / "dist" / "Equicord"
            self._sync_plugins(equicord)
            self._build_equicord(equicord)
            self._inject(equicord)
            self._set_status("Complete. Restart Discord with Ctrl+R.", 100)
            self._log("Done. Enable BetterStremioActivity in Vencord/Equicord plugins for Ascend RPC visuals.", "ok")
        except Exception as exc:
            self._set_status("Installer failed.", 100)
            self._log(f"ERROR: {exc}", "err")

    def _ensure_requirements_for_install(self):
        missing = [tool for tool in ("git", "node") if not command_exists(tool)]
        if missing:
            self._log(f"Missing required tools: {', '.join(missing)}", "err")
            self._set_status("Install Git and Node.js first.", 100)
            return False
        if not portable_pnpm_exists():
            self._log("portable pnpm is missing; trying automatic setup.", "warn")
            self.setup_pnpm()
        if not portable_pnpm_exists():
            self._log("portable pnpm still was not found. Check the npm setup output above.", "err")
            self._set_status("pnpm missing.", 100)
            return False
        return True

    def _close_discord_processes(self):
        if not self.close_discord.get():
            return
        self._set_status("Closing Discord processes...", 8)
        for meta in DISCORD_TARGETS.values():
            subprocess.run(["taskkill", "/F", "/IM", meta["process"], "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _sync_patchset(self):
        self._set_status("Syncing BetterVencord patchset...", 18)
        if not (PATCHSET_DIR / ".git").exists():
            result = run_process(["git", "clone", "--recurse-submodules", PATCHSET_URL, str(PATCHSET_DIR)], cwd=BASE_DIR)
            self._log(result.stdout.strip(), "ok" if result.returncode == 0 else "err")
            if result.returncode != 0:
                raise RuntimeError("Failed to clone BetterVencordPatchset.")
            return

        if self.skip_update.get():
            self._log("Skipping patchset git update.", "warn")
            return

        for args in (["git", "fetch", "--all"], ["git", "pull", "--ff-only"], ["git", "submodule", "update", "--init", "--recursive"]):
            self._log("$ " + " ".join(args), "info")

    def _close_discord_processes(self):
        if not self.close_discord.get():
            return
        self._set_status("Closing Discord processes...", 8)
        for meta in DISCORD_TARGETS.values():
            subprocess.run(["taskkill", "/F", "/IM", meta["process"], "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _sync_patchset(self):
        self._set_status("Syncing BetterVencord patchset...", 18)
        if not (PATCHSET_DIR / ".git").exists():
            result = run_process(["git", "clone", "--recurse-submodules", PATCHSET_URL, str(PATCHSET_DIR)], cwd=BASE_DIR)
            self._log(result.stdout.strip(), "ok" if result.returncode == 0 else "err")
            if result.returncode != 0:
                raise RuntimeError("Failed to clone BetterVencordPatchset.")
            return

        if self.skip_update.get():
            self._log("Skipping patchset git update.", "warn")
            return

        for args in (["git", "fetch", "--all"], ["git", "pull", "--ff-only"], ["git", "submodule", "update", "--init", "--recursive"]):
            self._log("$ " + " ".join(args), "info")
            result = run_process(args, cwd=PATCHSET_DIR)
            self._log(result.stdout.strip() or "ok", "ok" if result.returncode == 0 else "err")
            if result.returncode != 0 and args[1] != "pull":
                raise RuntimeError("Patchset sync failed.")

    def _build_patchset(self):
        self._set_status("Building patched Equicord source...", 35)
        for args in (["pnpm", "install", "--config.confirmModulesPurge=false"], ["pnpm", "dlx", "tsx", "scripts/build.ts", "--equicord"]):
            self._log("$ " + " ".join(args), "info")
            result = run_process(args, cwd=PATCHSET_DIR)
            self._log(result.stdout.strip(), "ok" if result.returncode == 0 else "err")
            if result.returncode != 0:
                raise RuntimeError("Patchset build failed.")

    def _plugin_urls(self):
        if not PLUGINS_FILE.exists():
            PLUGINS_FILE.write_text("", encoding="utf-8")
        urls = []
        for line in PLUGINS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
        return urls

    def _sync_plugins(self, equicord: Path):
        self._set_status("Syncing user plugins...", 55)
        plugin_dir = equicord / "src" / "userplugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)

        if BUNDLED_PLUGINS_DIR.exists():
            for source_plugin in BUNDLED_PLUGINS_DIR.iterdir():
                if not source_plugin.is_dir():
                    continue
                shutil.copytree(source_plugin, plugin_dir / source_plugin.name, dirs_exist_ok=True)
                self._log(f"Synced bundled plugin: {source_plugin.name}", "ok")

        source_builtin = PATCHSET_DIR / "src" / "userplugins" / "betterStremioActivity"
        target_builtin = plugin_dir / "betterStremioActivity"
        if source_builtin.exists() and not target_builtin.exists():
            shutil.copytree(source_builtin, target_builtin)
            self._log("Synced BetterStremioActivity.", "ok")

        for plugin_url in self._plugin_urls():
            name = repo_name_from_url(plugin_url)
            target = plugin_dir / name
            if (target / ".git").exists():
                args = ["git", "pull", "--ff-only"]
                cwd = target
                label = f"Updating {name}"
            else:
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                args = ["git", "clone", plugin_url, name]
                cwd = plugin_dir
                label = f"Cloning {name}"
            self._log(label, "info")
            result = run_process(args, cwd=cwd)
            self._log(result.stdout.strip() or "ok", "ok" if result.returncode == 0 else "warn")

        if LOCAL_PLUGINS_DIR.exists():
            for folder in LOCAL_PLUGINS_DIR.iterdir():
                if folder.is_dir():
                    shutil.copytree(folder, plugin_dir / folder.name, dirs_exist_ok=True)
                    self._log(f"Copied local plugin: {folder.name}", "ok")

    def _build_equicord(self, equicord: Path):
        self._set_status("Compiling Equicord plugin bundle...", 75)
        env = os.environ.copy()
        env.setdefault("EQUICORD_HASH", "Ascend-Vencord-Build")
        env.setdefault("EQUICORD_REMOTE", "Ascend-Media-RPC/Ascend-Vencord")
        for args in (["pnpm", "install", "--config.confirmModulesPurge=false"], ["pnpm", "build"]):
            self._log("$ " + " ".join(args), "info")
            result = run_process(args, cwd=equicord, env=env)
            self._log(result.stdout.strip(), "ok" if result.returncode == 0 else "err")
            if result.returncode != 0:
                raise RuntimeError("Equicord build failed.")

    def _inject(self, equicord: Path):
        targets = self.selected_targets()
        if not targets:
            raise RuntimeError("No Discord targets selected.")
        self._set_status("Injecting selected Discord clients...", 90)
        for label, path, _process in targets:
            if not path.exists():
                self._log(f"{label} path missing, skipping: {path}", "warn")
                continue
            self._repair_existing_patch(label, path, equicord)
            args = ["pnpm", "inject", "--location", str(path)]
            self._log(f"Injecting {label}: {path}", "info")
            result = run_process(args, cwd=equicord)
            self._log(result.stdout.strip(), "ok" if result.returncode == 0 else "err")
            if result.returncode != 0:
                raise RuntimeError(f"Injection failed for {label}.")

    def _repair_existing_patch(self, label: str, install_path: Path, equicord: Path):
        expected_bundle = (equicord / "dist" / "desktop").resolve()
        expected_patcher = expected_bundle / "patcher.js"
        repaired = 0
        for app_dir in discord_app_dirs(install_path):
            resources = app_dir / "resources"
            app_asar = resources / "app.asar"
            backup_asar = resources / "_app.asar"
            index_js = app_asar / "index.js"
            if not backup_asar.is_file():
                continue

            try:
                if app_asar.is_dir() and index_js.is_file():
                    shim = index_js.read_text(encoding="utf-8", errors="replace")
                elif app_asar.is_file():
                    shim = app_asar.read_bytes().decode("utf-8", errors="replace")
                else:
                    continue
            except OSError as exc:
                self._log(f"{label}: could not inspect existing patch in {app_dir.name}: {exc}", "warn")
                continue

            if not any(marker in shim for marker in ("patcher.js", "dist\\\\desktop", "dist/desktop")):
                continue

            expected_markers = (
                str(expected_bundle),
                str(expected_bundle).replace("\\", "\\\\"),
                str(expected_patcher),
                str(expected_patcher).replace("\\", "\\\\"),
            )
            if any(marker in shim for marker in expected_markers):
                self._log(f"{label}: existing patch in {app_dir.name} already points at this build.", "info")
            else:
                self._log(f"{label}: repairing stale patch in {app_dir.name}.", "warn")

            try:
                if app_asar.is_dir():
                    shutil.rmtree(app_asar)
                else:
                    app_asar.unlink()
                backup_asar.replace(app_asar)
                repaired += 1
            except OSError as exc:
                raise RuntimeError(f"Could not repair existing patch for {label} in {app_dir.name}: {exc}") from exc

        if repaired:
            self._log(f"{label}: restored {repaired} patched app.asar backup(s) before injection.", "ok")


if __name__ == "__main__":
    app = InstallerApp()
    app.mainloop()
