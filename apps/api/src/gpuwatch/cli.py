"""Command line: ``gpuwatch <command>``."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from gpuwatch.core.config import get_settings


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        "gpuwatch.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        workers=args.workers,
        proxy_headers=True,
        # Only trust X-Forwarded-For from the load balancer's network (the VPC CIDR on AWS).
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        access_log=False,
        log_config=None,
        timeout_graceful_shutdown=30,
        # Longer than an agent's interval (5 s) and a load balancer's idle timeout (60 s on
        # an ALB): otherwise the server closes a kept-alive connection just as the next
        # batch is sent on it, and the client sees "Server disconnected".
        timeout_keep_alive=75,
    )


def _worker(_: argparse.Namespace) -> None:
    from gpuwatch.worker import main

    asyncio.run(main())


def _migrate(_: argparse.Namespace) -> None:
    from gpuwatch.migrations.runner import upgrade

    upgrade(get_settings().database_url)
    print("migrations applied")


def _revision(args: argparse.Namespace) -> None:
    from gpuwatch.migrations.runner import revision

    revision(get_settings().database_url, args.message)


async def _create_owner(email: str, name: str, password: str) -> None:
    from sqlalchemy import func, select

    from gpuwatch.core.db import Database
    from gpuwatch.core.security import hash_password, password_problems
    from gpuwatch.users.models import User

    if problems := password_problems(password):
        sys.exit("password needs " + ", ".join(problems))
    db = Database(get_settings().database_url, pool_size=1, max_overflow=0)
    try:
        async with db.sessionmaker() as session:
            existing = await session.scalar(
                select(User).where(func.lower(User.email) == email.lower())
            )
            if existing:
                existing.role = "owner"
                existing.password_hash = hash_password(password)
                existing.disabled = False
                existing.session_version += 1
                print(f"updated {email} (owner)")
            else:
                session.add(
                    User(
                        email=email.lower(),
                        name=name,
                        role="owner",
                        password_hash=hash_password(password),
                    )
                )
                print(f"created {email} (owner)")
            await session.commit()
    finally:
        await db.dispose()


def _owner(args: argparse.Namespace) -> None:
    password = os.environ.get("GPUWATCH_OWNER_PASSWORD") or getpass.getpass("Password: ")
    asyncio.run(_create_owner(args.email, args.name, password))


def _seed(args: argparse.Namespace) -> None:
    from gpuwatch.demo.seed import run

    asyncio.run(run(token_file=args.token_file))


def _openapi(_: argparse.Namespace) -> None:
    from gpuwatch.openapi import spec, to_yaml

    sys.stdout.write(to_yaml(spec()))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gpuwatch", description="Euron Open GPUWatch")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="run the API")
    p.add_argument("--host", default="0.0.0.0")  # noqa: S104 the container must listen on all interfaces
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "4430")))
    # One process per container by default: Prometheus counters and the in-process cache
    # stay exact. Scale with more tasks or replicas, not more workers per task.
    p.add_argument("--workers", type=int, default=int(os.environ.get("WEB_CONCURRENCY", "1")))
    p.set_defaults(fn=_serve)

    sub.add_parser(
        "worker", help="run rollups, alerts, notifications, insights and retention"
    ).set_defaults(fn=_worker)
    sub.add_parser("migrate", help="apply database migrations").set_defaults(fn=_migrate)
    p = sub.add_parser(
        "revision", help="autogenerate a new migration from the models (against a migrated DB)"
    )
    p.add_argument("-m", "--message", required=True)
    p.set_defaults(fn=_revision)
    sub.add_parser("openapi", help="print the OpenAPI document as YAML").set_defaults(fn=_openapi)

    p = sub.add_parser("create-owner", help="create or reset an owner account")
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="Owner")
    p.set_defaults(fn=_owner)

    p = sub.add_parser(
        "seed-demo",
        help="demo users, rates, rules and channels; writes an enrolment token for the "
        "simulated agents",
    )
    p.add_argument(
        "--token-file",
        default=os.environ.get("GPUWATCH_DEMO_TOKEN_FILE", "/demo/enrolment-token"),
        help="where the simulated agents read their enrolment token",
    )
    p.set_defaults(fn=_seed)

    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
