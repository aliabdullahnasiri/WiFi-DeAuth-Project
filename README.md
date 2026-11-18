# WiFi DeAuth Project

A Linux Python application that repeatedly scans for a wireless access point by
BSSID, observes its channel, and orchestrates `mdk3` processes. When a later scan
finds the access point on another channel, the next launch uses that channel.
MQTT messages report observations, and an optional sound announces SSID changes.

Use only with permission in an isolated wireless test environment. The current
deauthentication command does **not** filter by the supplied BSSID: that value
selects the access point to track and is passed to authentication mode. List
files control the deauthentication command's scope.

## Current behavior

Each cycle stops processes matching `mdk3`, switches the interface to managed
mode, scans, and looks up the configured BSSID. If found, the program switches
to monitor mode, selects the detected channel, launches the configured modes,
and waits. If absent, it clears observations and waits half the interval.

Channel tracking is periodic, not continuous. Scanning interrupts the running
processes, and a channel change is discovered on a subsequent scan. Detection
depends on the adapter, driver, scan output, and access point visibility; the
project does not guarantee disruption of every wireless network.

## Requirements

- Linux and Python 3.11 or newer (`typing.Self` requires 3.11).
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for Python
  dependency and environment management.
- System commands used by the code: `sudo`, `ip`, `iw`, `egrep`, `pkill`, and
  `mdk3`. These are supplied by the operating system, not by `uv`.
- For wireless operation, an adapter and driver supporting the required managed
  and monitor modes, and permission to run the privileged commands.
- A reachable MQTT broker and valid settings. Notifications are called during
  normal operation and currently have no disable switch.
- If sound is configured, a working audio backend for `playsound` on the host.

## Setup with uv

From the repository root:

```sh
uv sync --locked
cp .env.example .env
uv run --locked wifi-deauth --help
```

Edit `.env` for your broker and optional sound file. The help command displays
the interface without scanning, changing network settings, or launching `mdk3`.
Importing the application does initialize logging and truncates `.log`.

This repository has already been initialized using `uv init`. Dependencies live
in `pyproject.toml`, and `uv.lock` records the resolved versions. The old
`requirements.txt` workflow has been replaced; virtual environment activation
is unnecessary when using `uv run`.

For dependency maintenance, use `uv add <package>` or `uv remove <package>`.
Commit both `pyproject.toml` and `uv.lock` after a dependency change.

## Configuration

`config.py` calls `load_dotenv()` at import time. Existing environment variables
take precedence over `.env`; missing values become `None`, with no validation.

| Variable | Purpose |
| --- | --- |
| `BROKER_IP` | MQTT broker hostname or address. |
| `TOPIC` | MQTT topic for observations and change notifications. |
| `USERNAME` | MQTT username; also check whether your shell already sets this name. |
| `PASSWORD` | MQTT password. |
| `SOUND` | Optional audio file path; an empty value disables sound. |

The current publisher does not expose broker port or TLS settings. `.env` is
ignored by Git; `.env.example` contains placeholders only.

## Command interface

`uv run wifi-deauth` starts the project command, which requires `INTERFACE` and
`--bssid`. It loads configuration, logging, scanning, and notifications through
the existing modules; those modules do not need to be started separately.
Use `uv run --locked wifi-deauth --help` to inspect all options.

The command syntax for an authorized lab session is:

```text
uv run --locked wifi-deauth INTERFACE --bssid BSSID [OPTIONS]
```

Replace `INTERFACE` and `BSSID` with your lab interface and access point
identifier. The original `uv run --locked python target.py` entry point remains
available with the same arguments.

| Option | Default | Existing behavior |
| --- | --- | --- |
| `--bssid` | Required | Access point identifier used for scan lookup. |
| `--whitelist` | Unset | File passed to the deauthentication subprocess's whitelist option. |
| `--blacklist` | Unset | File passed to the deauthentication subprocess's blacklist option. |
| `--mode` | `2` | Above zero launches deauthentication mode; above one also launches authentication mode. |
| `--interval` | `60` | Wait in seconds after a successful scan and launch; half this when absent. |
| `--debug` | Off | Logs missing attribute access on `Target`; does not configure a global log level. |

Mode and interval are unrestricted integers. A mode of zero or less still stops
processes and changes interface settings; it is **not** a dry-run mode.
`Target(...)` uses a 30-second interval by default, while the CLI uses 60.

## Limitations

- Process termination uses `sudo pkill -9` by name and can affect other `mdk3`
  sessions on the host.
- There is no shutdown cleanup for launched processes or interface state.
  Interrupting Python does not guarantee that its child processes have stopped.
- Missing interfaces are retried recursively without a limit.
- Scan parsing depends on the text produced by `iw`; missing channel fields
  can cause unpacking errors, and scan failures can appear as empty results.
- MQTT errors other than a refused connection propagate and may stop the loop.
- `Target.start()` is a placeholder; the CLI calls `Target.attack()` directly.

See [architecture and operation](docs/architecture.md), the
[API reference](docs/api.md), and the [development guide](docs/development.md).

## License

This project is distributed under the [MIT License](LICENSE).
