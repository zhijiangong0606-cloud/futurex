import asyncio
import sys

from .app import run


def main() -> None:
    profile = "default"
    if len(sys.argv) > 1:
        profile = sys.argv[1]

    asyncio.run(run(profile=profile))


if __name__ == "__main__":
    main()
