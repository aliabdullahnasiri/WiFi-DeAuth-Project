"""Load dotenv settings and expose environment variables through ``Config``."""

import os

from dotenv import load_dotenv

load_dotenv()


class Meta(type):
    """Resolve missing class attributes from the process environment."""

    def __getattr__(cls, name):
        """Return the named environment variable, or ``None`` when unset."""
        return os.getenv(name, None)

    def __getattribute__(cls, name):
        """Delegate existing attribute lookup to the standard metaclass."""
        return super().__getattribute__(name)


class Config(metaclass=Meta):
    """Environment-backed settings; values are unvalidated strings or ``None``."""


def main() -> None:
    """Do nothing; this module supplies configuration to other modules."""
    pass


if __name__ == "__main__":
    main()
