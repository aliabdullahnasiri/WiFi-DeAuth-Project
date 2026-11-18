# Development

[README](../README.md) · [Architecture](architecture.md) · [API reference](api.md)

## Environment and dependencies

Setuptools packages the five top-level Python modules and registers the
`wifi-deauth` command. Run commands from the repository root so `uv` selects
this project's environment.
Python 3.11 is the minimum because `target.py` imports `typing.Self`.

```sh
uv sync --locked
uv run --locked wifi-deauth --help
```

`pyproject.toml` declares dependencies; `uv.lock` records their resolution.
`.venv/`, `.env`, bytecode, and `.log` are ignored by Git. Python dependencies
do not provide the external wireless commands or an operating system audio
backend.

The migration adds the previously undeclared `python-dotenv` import and retains
the original dependency pins except for `playsound`. Its 1.3.0 source build
failed during isolated installation with `OSError: could not get source code`;
the project pins 1.2.2, which provides the `playsound(path)` API used here.
Audio playback still requires verification on the intended host. Pygments
remains explicitly pinned from the original requirements, although the source
uses it indirectly through Rich.

Use `uv add <package>` and `uv remove <package>` to change dependencies. For an
intentional upgrade, use `uv lock --upgrade-package <package>`, then `uv sync
--locked`, verify the result, and commit the metadata and lockfile together.

## Checks without wireless activity

```sh
uv lock --check
uv sync --locked --check
uv run --locked python -m compileall -q config.py console.py func.py logger.py target.py
uv run --locked wifi-deauth --help
```

Compilation checks syntax. CLI help checks imports and Click registration, and
does not enter the scan loop. It still initializes `.log` through module
imports. These checks do not prove wireless, broker, or audio functionality.

There is currently no automated regression test suite. Future unit tests should
mock `subprocess.run`, MQTT publishing, sleeping, and audio playback. Useful
cases include malformed scan output, a target disappearing between scans,
channel and SSID transitions, and unavailable broker settings. Calling
`Target.attack()` directly enters an unbounded loop with real side effects.

## Troubleshooting existing behavior

| Symptom | Relevant implementation detail |
| --- | --- |
| Command not found | System utilities must be installed separately from Python dependencies. |
| Interface unavailable messages repeat | The decorator retries recursively; verify the interface and command permissions. |
| No access points found | Empty scans and command failures currently share the same result path. |
| Unpacking error in `find()` | A scan record without a parsed channel can contain fewer than four fields. |
| Notification errors stop execution | Only `ConnectionRefusedError` is caught by `notify()`; check broker configuration and inherited environment values. |
| No sound | `SOUND` must be nonempty and playback requires a usable host audio backend. |
| Old logs disappear | Importing `logger.py` opens `.log` in write mode. |

Changes to scan behavior, process ownership, shutdown handling, and validation
should be reviewed separately from documentation and dependency maintenance.
