from __future__ import annotations

import argparse
import json
import os
import sys

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m agent.main")
    parser.add_argument(
        "--attack",
        type=str,
        default=None,
        metavar="NAME",
        help="Run a single attack by name (e.g. duplicate_funding).",
    )
    return parser

def main(argv: list[str] | None = None) -> None:
    """
    CLI entry point for the QA agent (§3).

    Orchestrates the reliability charter; release artifacts reflect INV-01–INV-20 findings.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.attack is None:
        parser.print_help()
        return

    if "MOVEDOCS_API_BASE" not in os.environ:
        print("error: MOVEDOCS_API_BASE is not set", file=sys.stderr)
        raise SystemExit(1)

    from agent.clients.funding_client import FundingClient
    from agent.graph import KNOWN_ATTACKS, run_named_attack

    if args.attack not in KNOWN_ATTACKS:
        print(f"Unknown attack: {args.attack!r}", file=sys.stderr)
        raise SystemExit(1)

    client = FundingClient()
    final_state = run_named_attack(client, args.attack)
    result = final_state["result"]
    rule = result["rule"]
    status = result["status"]
    reasoning = result["reasoning"]

    print(f"{rule} | {args.attack} | {status} | {json.dumps(reasoning, ensure_ascii=False)}")

    if status == "BREACHED":
        raise SystemExit(1)
    raise SystemExit(0)

def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse CLI flags such as --attack duplicate_funding (§13.2)."""
    return _build_arg_parser().parse_args(argv)

if __name__ == "__main__":
    main()
