# Ascend Vencord Installer

This folder is the dedicated GUI installer for the Ascend Media RPC Discord client build.

Ascend Media RPC works with normal Discord RPC, but the activity layout is designed to look correct with this Ascend Vencord/Equicord build and the bundled `BetterStremioActivity` plugin. Stock Discord can still show activity, but names, spoofed targets, pause state, and rich visual formatting may not match the intended layout.

## Quick Start

1. Install requirements:
   - Git: https://git-scm.com/download/win
   - Node.js LTS: https://nodejs.org/
2. Run:

```bat
run.bat
```

or:

```bat
launch_installer.bat
```

3. In the GUI:
   - Click `Check Requirements`.
   - Click `Install / Repair pnpm` if pnpm is missing.
   - Select one or more Discord targets.
   - Click `Build + Inject`.
   - Restart Discord with `Ctrl+R`.

## Supported Discord Clients

The GUI can inject into:

- Discord Stable
- Discord PTB
- Discord Canary
- Discord Development
- A custom Discord install folder

Detected clients are selected automatically.

## Adding Your Own Plugins

There are two easy options:

1. Add git URLs to `plugins.txt`, one URL per line.
2. Put local plugin folders into `local_plugins/`.

The installer copies local plugins and clones/updates git plugins into:

```txt
BetterVencordPatchset\dist\Equicord\src\userplugins
```

The built-in `BetterStremioActivity` plugin is bundled in `bundled_plugins/betterStremioActivity` and synced automatically so Ascend Media RPC activity renders the intended way.

## Notes

- The installer closes Discord before injection by default to avoid locked files.
- It uses pnpm through Corepack when possible.
- It does not remove your local plugin source folders.
- If you need to debug a build, enable `Skip patchset git update` and rerun.
