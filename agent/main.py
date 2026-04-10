from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

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

    if args.attack == "duplicate_funding":
        from agent.graph import run_duplicate_funding_graph

        final_state = run_duplicate_funding_graph()
        payload = {
            "attack": "duplicate_funding",
            "result": final_state.get("result"),
        }
        artifacts_dir = _ROOT / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        out_path = artifacts_dir / "attacks.json"
        out_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return

    if args.attack is not None:
        print(f"Unknown attack: {args.attack!r}", file=sys.stderr)
        raise SystemExit(1)

    parser.print_help()

def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse CLI flags such as --attack duplicate_funding (§13.2)."""
    return _build_arg_parser().parse_args(argv)

if __name__ == "__main__":
    main()
