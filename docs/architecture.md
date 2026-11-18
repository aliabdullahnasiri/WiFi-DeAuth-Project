# Architecture and operation

[README](../README.md) · [API reference](api.md) · [Development](development.md)

## Modules

| File | Responsibility |
| --- | --- |
| `target.py` | Click command, target observations, repeated scan/restart loop, sound alerts. |
| `func.py` | Privileged subprocess calls, scan parsing, progress waits, MQTT publishing. |
| `config.py` | Dotenv loading and environment-backed `Config` attributes. |
| `console.py` | Shared Rich terminal console. |
| `logger.py` | Loguru sinks for stdout and `.log`. |

## Execution flow

1. Importing the modules loads dotenv settings and configures logging.
2. Click reads options and creates a `Target`; construction lowercases the BSSID.
3. `Target.attack()` stops processes matching `mdk3` and calls `Target.find()`.
4. `get_networks()` switches the interface to managed mode, brings it up,
   runs an `iw` scan, filters output through `egrep`, and parses access points.
5. `find()` looks up the stored BSSID. If present, it updates channel, SSID,
   signal, and RSN observations and publishes a detection notification.
6. For a detected target, `mdk3()` stops matching processes again, selects
   monitor mode and the observed channel, and starts the configured subprocesses
   in threads. The loop waits the full interval before scanning again.
7. For an absent target, observations become `None`, a notification is sent,
   and the loop waits half the interval.

There is no background channel watcher: the full loop repeats each time, even
when the channel has not changed. Scan and command execution add to the wait,
so the interval is not an exact scan cadence.

## Observation data

A parsed scan normally produces this shape (illustrative data):

```python
{
    "02:00:00:00:00:01": [
        6,
        "Lab network",
        "-50.00 dBm",
        {
            "version": None,
            "group-cipher": "CCMP",
            "pairwise-ciphers": "CCMP",
            "authentication-suites": "PSK",
        },
    ],
}
```

SSID and signal may be `None`; the RSN value is `None` when no RSN block is
detected. Missing channel data is not padded with `None`, so the current parser
can return only three values. `Target.find()` expects four and then raises an
unpacking error. The scan filter does not retain the RSN version line, so
`version` generally remains `None`.

The parser preserves BSSID case, while the constructor lowercases the requested
BSSID. It does not validate the BSSID format or normalize every scan field.

## Notifications and logging

`notify()` publishes one message through Paho MQTT using `Config.TOPIC`,
`BROKER_IP`, `USERNAME`, and `PASSWORD`. It returns `0` on success and `1` for
`ConnectionRefusedError`; other exceptions propagate. Callers ignore its return
code. No empty-settings guard or notification-disable option exists.

Channel-change notifications require both old and new channels to be truthy
and different. SSID-change notifications and optional sound similarly require
two nonempty, different names. Losing the target clears those values, so a
change across a period of absence is not necessarily reported as a change.
An SSID change is logged as a suspected router reset; it is not proof of one.

Loguru removes its existing sinks and adds stdout plus `.log` in write mode at
module import. Each process therefore truncates the file. The file sink enables
color formatting. There is no log rotation, retention policy, or CLI verbosity
configuration. `target.cli()` installs Rich tracebacks for both the
`wifi-deauth` command and direct execution of `target.py`.

## Process and interface lifecycle

The subprocess threads are not retained or explicitly joined. Subprocess output
is captured but not reported by these workers. Most command exit statuses are
ignored by their callers. The code has no `try/finally` to restore interface
mode or terminate child processes on exit.

`check_interface()` retries recursively after a failed interface check. Persistent
failures can exhaust the call stack. Name-based `pkill -9` is host-wide for
matching processes, rather than limited to this application's children.
