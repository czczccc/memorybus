"""Command line: memorybus init | add | search | list | export | token | serve."""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path

from .config import load_settings
from .db import create_pool, init_schema
from .embeddings import build_embedder
from .service import NAMESPACES, MemoryBusError, MemoryService


def _service() -> MemoryService:
    settings = load_settings()
    pool = create_pool(settings.database_url)
    init_schema(pool, settings.embedding_dimensions)
    return MemoryService(pool, build_embedder(settings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="memorybus")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create the database schema")

    add = sub.add_parser("add", help="Add a memory")
    add.add_argument("namespace", choices=NAMESPACES)
    add.add_argument("content")
    add.add_argument("--subject", default="")
    add.add_argument("--importance", type=float, default=0.5)
    add.add_argument("--new", action="store_true", help="Never supersede by subject")

    search = sub.add_parser("search", help="Search memories")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)

    ls = sub.add_parser("list", help="List memories")
    ls.add_argument("namespace", nargs="?", choices=NAMESPACES)
    ls.add_argument("--all", action="store_true", help="Include superseded")

    export = sub.add_parser("export", help="Export memory.json and memory.md")
    export.add_argument("--out", default="export")

    sub.add_parser("token", help="Generate a random API token for MEMORYBUS_API_TOKEN")

    serve = sub.add_parser("serve", help="Run the HTTP server (MCP + REST)")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)

    if args.command == "token":
        print(secrets.token_urlsafe(32))
        return 0
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "memorybus.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            proxy_headers=True,
            forwarded_allow_ips="*",
        )
        return 0

    service = _service()
    try:
        if args.command == "init":
            print("Schema ready.")
        elif args.command == "add":
            result = service.upsert(
                args.namespace,
                args.content,
                subject=args.subject,
                importance=args.importance,
                mode="new" if args.new else "auto",
                provider="cli",
            )
            print(f"{result.action}: {result.memory['id']}")
            for old in result.superseded:
                print(f"  superseded {old['id']}: {old['content']}")
        elif args.command == "search":
            for m in service.search(args.query, limit=args.limit, provider="cli"):
                print(f"{m['score']:.3f}  [{m['namespace']}] {m['subject'] or '-'}: {m['content']}")
        elif args.command == "list":
            for m in service.list(args.namespace, include_inactive=args.all, provider="cli"):
                print(
                    f"{m['id']}  [{m['namespace']}/{m['status']}] {m['subject'] or '-'}: "
                    f"{m['content']}"
                )
        elif args.command == "export":
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            (out / "memory.json").write_text(
                json.dumps(service.export_json(), ensure_ascii=False, indent=2)
            )
            (out / "memory.md").write_text(service.export_markdown())
            print(f"Wrote {out / 'memory.json'} and {out / 'memory.md'}")
    except MemoryBusError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
