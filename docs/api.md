# API reference

[README](../README.md) · [Architecture](architecture.md) · [Development](development.md)

This reference describes the current implementation. Wireless helpers perform
real privileged operations; importing `func` or `target` also configures logging.

## Configuration and output

| Symbol | Contract |
| --- | --- |
| `config.Meta` | Metaclass that delegates ordinary lookup and resolves missing attributes using `os.getenv`. |
| `config.Config` | Access arbitrary environment settings as class attributes; results are strings or `None`, without validation. |
| `config.main()` | No-op placeholder. |
| `console.console` | Shared `rich.console.Console` instance. |
| `logger.logger` | Configured Loguru logger with color-aware messages, stdout, and a `.log` sink. |

## Utility functions (`func.py`)

| Function | Behavior and return value |
| --- | --- |
| `sleep(seconds, /, simple=False)` | Waits in 0.2-second increments with Rich progress; `simple=True` selects a spinner. Returns `None`; timing is approximate. |
| `check_interface(timeout=5)` | Decorator factory for functions whose first argument is an interface. Calls `sudo ip link show dev`; recursively retries on failure and otherwise returns the wrapped result. |
| `kill(name)` | Calls `sudo pkill -9 name`, discards status, and returns `None`. |
| `mdk3(interface, bssid, channel, mode=2, whitelist=None, blacklist=None)` | Stops matching processes, configures monitor mode and channel, and starts command threads according to mode thresholds. Returns `None`. List arguments must expose `.name`. |
| `change_interface_status(interface, status)` | Requests `up` or `down`; returns `0` when its text check considers the state satisfied, otherwise the command exit code. |
| `change_interface_type(interface, _type)` | Requests `managed` or `monitor`; returns `0` when already set, otherwise the mode-setting command's exit code. |
| `change_interface_channel(interface, channel)` | Ensures monitor mode and an up link, then returns the channel-setting command's exit code. |
| `get_networks(interface)` | Returns a BSSID-to-list mapping parsed from scan output. Empty results also publish an MQTT alert. See the data shape and parsing limitations in the architecture guide. |
| `notify(payload)` | Publishes one MQTT message; returns `0` on success or `1` on incomplete configuration or connection refusal. Uses anonymous publishing when both credentials are absent. Other errors propagate. |
| `main()` | No-op placeholder. |

The interface decorator applies to `mdk3`, all three interface-changing helpers,
and `get_networks`. Type hints do not provide runtime validation.

## `target.Target`

```python
Target(
    interface,
    bssid,
    /,
    whitelist=None,
    blacklist=None,
    mode=2,
    interval=30,
    debug=False,
)
```

The first two arguments are positional-only. Construction stores settings and
lowercases the BSSID; it does not scan or launch commands.

| Member | Behavior |
| --- | --- |
| `bssid` | Stored identifier. Subsequent assignment does not lowercase it. |
| `channel` | Last observed channel or `None`; assignment may notify a change. |
| `ssid` | Last observed name or `None`; assignment may notify and play sound. |
| `rsn` | Last parsed RSN mapping or `None`. |
| `power` | Signal text set by `find()`; initially absent. |
| `find()` | Scans and updates observations. Returns `1` for a detected target, `0` for absence; publishes in both cases. Errors propagate. |
| `attack()` | Indefinite scan/restart loop; returns only by interruption or error and has no cleanup handler. |
| `start()` | Placeholder returning `None`. |
| `play()` | Starts a sound thread when `Config.SOUND` is truthy; returns `None`. |
| `__repr__()` | Includes BSSID, SSID, channel, signal, and object identity. |
| `__setattr__()` | Delegates assignment to `object`. |
| `__getattribute__()` | Suppresses `AttributeError`, optionally logs it, and implicitly returns `None`. |

Because missing attributes are suppressed, `hasattr(target, name)` can return
`True` even for an absent attribute. Code using this class should not rely on
normal `AttributeError` semantics.

## Command entry point

`target.cli()` installs Rich tracebacks and invokes `target.main`. It is used by
both the installed `wifi-deauth` command and direct execution of `target.py`.
`target.main` is decorated with Click. It constructs `Target` and immediately
calls `attack()`. CLI defaults and option descriptions are listed in the
[README](../README.md#command-interface). The CLI's `--debug` branch itself is a
no-op; the value is forwarded to `Target`.
