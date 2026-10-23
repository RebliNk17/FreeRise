import argparse
import getpass
import sys
from collections.abc import Callable

from freerise import auth
from freerise.db import SessionLocal


def _create_user(args: argparse.Namespace) -> None:
    pw = getpass.getpass("Password: ")
    if pw != getpass.getpass("Confirm password: "):
        sys.exit("Passwords do not match")
    with SessionLocal.begin() as s:
        _, uri = auth.create_user(s, args.username, pw)
    print(f"Add to your authenticator app (shown once):\n{uri}")


def _worker(args: argparse.Namespace) -> None:
    import asyncio

    from freerise.sync.scheduler import main as worker_main

    asyncio.run(worker_main())


# Registry: name -> (argument setup, handler). Later tasks add entries here.
COMMANDS: dict[str, tuple[Callable[[argparse.ArgumentParser], None], Callable]] = {
    "create-user": (lambda p: p.add_argument("username"), _create_user),
    "worker": (lambda p: None, _worker),
}


def _register_categorize() -> None:
    from freerise.categorize.cli import COMMANDS as CAT
    from freerise.demo import COMMANDS as DEMO

    COMMANDS.update(CAT)
    COMMANDS.update(DEMO)


_register_categorize()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="freerise")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, (setup, handler) in COMMANDS.items():
        p = sub.add_parser(name)
        setup(p)
        p.set_defaults(handler=handler)
    args = parser.parse_args(argv)
    args.handler(args)
